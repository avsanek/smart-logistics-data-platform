import numpy as np
import pandas as pd
from ml.features import CATEGORICAL, FEATURES, NUMERIC, features, split_masks


def test_split_boundary():
    data=pd.DataFrame({'loading_date':['2026-07-25','2026-07-26','2026-10-04',
                                      '2026-10-05','2026-10-26','2026-10-27']})
    train,test,future=split_masks(data)
    assert train.tolist()==[False,True,True,False,False,False]
    assert test.tolist()==[False,False,False,True,True,False]
    assert future.tolist()==[False,False,False,False,False,True]
    assert not (train&test).any()


def test_feature_allowlist_ignores_target_and_forbidden_columns():
    data=pd.DataFrame({**{c:['x','y'] for c in CATEGORICAL},
                       **{c:[1.,2.] for c in NUMERIC},'loading_date':['2026-10-05','2026-10-26']})
    before=features(data)
    for col in ['price','price_rub','price_with_vat','outlier_mark','price_group_id',
                'price_group_stats','price_km','profit']:
        data[col]=[999999.,-99.]
    pd.testing.assert_frame_equal(before,features(data))
    assert list(before.columns)==FEATURES
    for name in ['month','day_of_week','day_of_year']:
        np.testing.assert_allclose(before[name+'_sin']**2+before[name+'_cos']**2,1.)
