"""CPU CatBoost with a fixed time split, content-addressed model and atomic scoring."""
import hashlib
import json
import os

import numpy as np
import pandas as pd
import catboost
import sklearn
from catboost import CatBoostRegressor
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score

from etl.db import artifact_dir, copy_rows, event, transaction
from ml.features import CATEGORICAL, FEATURES, features, split_masks


def dataset(conn) -> pd.DataFrame:
    # Exactly one row per deal. Body set is sorted, independent of source insertion order.
    query = '''SELECT p.*, l.region AS origin_region,u.region AS destination_region,
        l.latitude AS origin_latitude,l.longitude AS origin_longitude,
        u.latitude AS destination_latitude,u.longitude AS destination_longitude,
        b.body_group FROM core.prices p JOIN core.cities l ON l.gc_id=p.loading_city_gcid
        JOIN core.cities u ON u.gc_id=p.unloading_city_gcid
        JOIN (SELECT price_id,string_agg(body_group,' + ' ORDER BY body_group) AS body_group
        FROM core.price_body_groups GROUP BY price_id) b ON b.price_id=p.id
        WHERE p.loading_date>=DATE '2026-07-26'
        AND ((p.is_fact AND p.price_type IN(1,2,3,4,5,9) AND NOT p.outlier_mark AND NOT p.complex)
              OR p.loading_date>DATE '2026-10-26') ORDER BY p.loading_date,p.id'''
    with conn.cursor() as cur:
        cur.execute(query)
        return pd.DataFrame(cur.fetchall(),columns=[d.name for d in cur.description])


def training() -> None:
    with transaction() as conn:
        frame = dataset(conn)
        train_mask,test_mask,_ = split_masks(frame)
        train,test = frame.loc[train_mask],frame.loc[test_mask]
        if len(train)<100 or len(test)<2:
            raise ValueError(f'Insufficient training/test rows: {len(train)}/{len(test)}')
        x_train,x_test = features(train),features(test)
        params = dict(iterations=550,depth=7,learning_rate=.06,loss_function='RMSE',
                      random_seed=20261026,thread_count=int(os.environ.get('MODEL_THREADS','2')),
                      allow_writing_files=False,verbose=False,has_time=True)
        versions = {'catboost':catboost.__version__,'numpy':np.__version__,
                    'pandas':pd.__version__,'scikit_learn':sklearn.__version__}
        digest = hashlib.sha256(pd.util.hash_pandas_object(
            pd.concat([x_train,train[['price_rub']]],axis=1),index=False).values.tobytes()
            + json.dumps({'parameters':params,'versions':versions},sort_keys=True).encode()).hexdigest()[:16]
        name = 'catboost_'+digest
        model_path = artifact_dir()/(name+'.cbm')
        model = CatBoostRegressor(**params)
        cached = model_path.exists()
        if cached:
            model.load_model(str(model_path))
        else:
            # Test is never passed as eval_set: no tuning or early stopping on holdout.
            model.fit(x_train,train['price_rub'],cat_features=CATEGORICAL)
            temp_path = model_path.with_suffix('.tmp')
            model.save_model(str(temp_path))
            temp_path.replace(model_path)
        predicted = model.predict(x_test)
        actual = test['price_rub']
        metrics = {
            'model_name':name,'train_rows':len(train),'test_rows':len(test),
            'train_start':str(train.loading_date.min()),'train_end':str(train.loading_date.max()),
            'test_start':str(test.loading_date.min()),'test_end':str(test.loading_date.max()),
            'r2':float(r2_score(actual,predicted)),
            'mape_pct':float(mean_absolute_percentage_error(actual,predicted)*100),
            'rmse_rub':float(np.sqrt(mean_squared_error(actual,predicted))),
            'mae_rub':float(mean_absolute_error(actual,predicted)),
            'features':FEATURES,'parameters':params,'versions':versions,
        }
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO mart.ml_runs(model_name,metrics) VALUES(%s,%s)
                ON CONFLICT(model_name) DO UPDATE SET metrics=excluded.metrics''',(name,json.dumps(metrics)))
        # This small manifest is published only after the model has been written successfully.
        (artifact_dir()/'model.json.tmp').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
        (artifact_dir()/'model.json.tmp').replace(artifact_dir()/'model.json')
    event('training_complete',cached=cached,**metrics)


def scoring() -> None:
    manifest = json.loads((artifact_dir()/'model.json').read_text(encoding='utf-8'))
    name = manifest['model_name']
    model = CatBoostRegressor()
    model.load_model(str(artifact_dir()/(name+'.cbm')))
    with transaction() as conn:
        frame = dataset(conn)
        _,test_mask,future_mask = split_masks(frame)
        batch = frame.loc[test_mask|future_mask].copy()
        predicted = model.predict(features(batch))
        future = pd.to_datetime(batch.loading_date) > '2026-10-26'
        rows = []
        for i,(_,row) in enumerate(batch.iterrows()):
            actual = None if future.iloc[i] else float(row.price_rub)
            err = None if actual is None else abs(actual-float(predicted[i]))
            rows.append((int(row.id),row.loading_date,int(row.loading_city_gcid),int(row.unloading_city_gcid),
                         row.body_group,actual,float(predicted[i]),err,
                         None if actual is None else err/actual*100,name))
        with conn.cursor() as cur:
            cur.execute('DELETE FROM mart.ml_price_predictions')
        columns = ['price_id','loading_date','loading_city_gcid','unloading_city_gcid','body_group',
                   'actual_price_rub','predicted_price_rub','abs_error_rub','ape_pct','model_name']
        for start in range(0,len(rows),10000):
            copy_rows(conn,'mart.ml_price_predictions',columns,rows[start:start+10000])
    event('scoring_complete',rows=len(rows),future_rows=int(future.sum()),model_name=name)
