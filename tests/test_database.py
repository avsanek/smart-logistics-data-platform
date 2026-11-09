"""Assertions against real PostgreSQL data, not only successful task exit codes."""
import numpy as np
import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

from etl.pipeline import dwh_marts, etl, source_init
from ml.pipeline import scoring, training


@pytest.fixture
def conn():
    connection=psycopg2.connect(connect_timeout=10)
    connection.autocommit=True
    yield connection
    connection.close()


def scalar(conn,sql,params=None):
    with conn.cursor() as cur:
        cur.execute(sql,params)
        return cur.fetchone()[0]


def test_source_core_and_quarantine_partition(conn):
    assert scalar(conn,'SELECT count(*) FROM raw.prices')==300000
    assert scalar(conn,'SELECT count(*) FROM core.prices')>290000
    assert scalar(conn,'SELECT count(*) FROM core.dq_quarantine_prices')>0
    assert scalar(conn,'''SELECT count(*) FROM raw.prices r LEFT JOIN core.prices c ON c.id=r.id
        LEFT JOIN core.dq_quarantine_prices q ON q.price_id=r.id
        WHERE (c.id IS NULL AND q.price_id IS NULL) OR (c.id IS NOT NULL AND q.price_id IS NOT NULL)''')==0
    assert scalar(conn,'''SELECT count(*) FROM core.cities c WHERE c.source_id <>
        (SELECT min(id) FROM raw.cities r WHERE r.gc_id=c.gc_id)''')==0


def test_exchange_rates_and_source_flags(conn):
    assert scalar(conn,'''SELECT count(*) FROM core.prices c JOIN raw.prices r ON r.id=c.id
        WHERE c.outlier_mark<>r.outlier_mark OR c.is_fact<>r.is_fact''')==0
    assert scalar(conn,'''SELECT count(*) FROM core.prices c JOIN raw.prices r ON r.id=c.id
        WHERE abs(c.price_rub-r.price*CASE WHEN r.currency_code='643' THEN 1 ELSE
        (SELECT e.value FROM raw.exchange_rates e WHERE e.num_code=r.currency_code
        AND e.setting_date=r.nearest_rate_date ORDER BY id LIMIT 1) END)>0.00001
        OR (r.currency_code<>'643' AND (r.nearest_rate_date IS NULL OR c.rate_date<>r.nearest_rate_date))''')==0
    assert scalar(conn,'''SELECT count(*) FROM raw.prices r WHERE r.currency_code IN('840','978')
        AND NOT EXISTS(SELECT 1 FROM raw.exchange_rates e
        WHERE e.num_code=r.currency_code AND e.setting_date=r.nearest_rate_date)
        AND NOT EXISTS(SELECT 1 FROM core.dq_quarantine_prices q WHERE q.price_id=r.id
        AND 'MISSING_EXACT_RATE'=ANY(q.reason_codes))''')==0


def test_bridges_and_grain(conn):
    for table,cols in [('core.price_body_groups','price_id,body_group'),
                       ('core.price_months','price_id,price_date'),
                       ('mart.mart_market_corridor','month,loading_city_gcid,unloading_city_gcid,body_group,weight_category')]:
        assert scalar(conn,f'SELECT count(*) FROM (SELECT {cols} FROM {table} GROUP BY {cols} HAVING count(*)>1) x')==0
    assert scalar(conn,"SELECT count(*) FROM mart.mart_market_corridor WHERE month>DATE '2026-10-01'")==0
    assert scalar(conn,'''SELECT count(*) FROM mart.mart_market_corridor WHERE
        NOT (p25_trip<=median_trip AND median_trip<=p75_trip AND p25_km<=median_km AND median_km<=p75_km)
        OR trips_count<carriers_count OR (trips_count=1 AND cv_rate IS NOT NULL)''')==0


def test_corridor_independently_with_numpy(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT * FROM mart.mart_market_corridor ORDER BY trips_count DESC LIMIT 1')
        cell=cur.fetchone()
        cur.execute('''SELECT DISTINCT p.id,p.price_rub,p.distance,p.organization_id,p.price_type
            FROM core.prices p JOIN core.price_months d ON d.price_id=p.id
            JOIN core.price_body_groups b ON b.price_id=p.id
            WHERE date_trunc('month',d.price_date)::date=%s AND d.price_date<=DATE '2026-10-26'
            AND p.loading_city_gcid=%s AND p.unloading_city_gcid=%s
            AND b.body_group=%s AND p.weight_category=%s AND p.is_fact
            AND p.price_type IN(1,2,3,4,5,9) AND NOT p.complex AND NOT p.outlier_mark''',
            tuple(cell[k] for k in ['month','loading_city_gcid','unloading_city_gcid','body_group','weight_category']))
        rows=cur.fetchall()
    prices=np.array([r['price_rub'] for r in rows]); km=prices/np.array([r['distance'] for r in rows])
    assert cell['trips_count']==len(rows)
    assert cell['carriers_count']==len({r['organization_id'] for r in rows
        if r['price_type'] in (3,9) and r['organization_id'] is not None})
    for suffix,values in [('trip',prices),('km',km)]:
        for prefix,q in [('p25',.25),('median',.5),('p75',.75)]:
            assert cell[prefix+'_'+suffix]==pytest.approx(np.quantile(values,q))
    assert cell['avg_trip']==pytest.approx(np.mean(prices))
    assert cell['cv_rate']==pytest.approx(np.std(prices,ddof=1)/np.mean(prices))


def test_calendar_comparisons_and_reliability(conn):
    assert scalar(conn,'''SELECT count(*) FROM mart.mart_market_corridor a
        LEFT JOIN mart.mart_market_corridor p ON p.month=(a.month-interval '1 month')::date
        AND (p.loading_city_gcid,p.unloading_city_gcid,p.body_group,p.weight_category)=
        (a.loading_city_gcid,a.unloading_city_gcid,a.body_group,a.weight_category)
        LEFT JOIN mart.mart_market_corridor y ON y.month=(a.month-interval '1 year')::date
        AND (y.loading_city_gcid,y.unloading_city_gcid,y.body_group,y.weight_category)=
        (a.loading_city_gcid,a.unloading_city_gcid,a.body_group,a.weight_category)
        WHERE a.mom_pct IS DISTINCT FROM 100*(a.median_trip/nullif(p.median_trip,0)-1)
        OR a.yoy_pct IS DISTINCT FROM 100*(a.median_trip/nullif(y.median_trip,0)-1)
        OR a.reliability_level<>CASE WHEN a.trips_count>=30 AND a.carriers_count>=5
        AND DATE '2026-10-26'-a.month<=30
        THEN 'HIGH' WHEN a.trips_count>=10 THEN 'MEDIUM' ELSE 'LOW_DATA' END''')==0


def test_prediction_metrics_and_future_nulls(conn):
    assert scalar(conn,'SELECT count(*) FROM mart.ml_price_predictions')>5000
    assert scalar(conn,"SELECT count(*) FROM mart.ml_price_predictions WHERE loading_date>DATE '2026-10-26'")>1000
    assert scalar(conn,"SELECT count(*) FROM mart.ml_price_predictions WHERE loading_date>DATE '2026-10-26'")==scalar(
        conn,"SELECT count(*) FROM core.prices WHERE loading_date>DATE '2026-10-26'")
    assert scalar(conn,'''SELECT count(*) FROM mart.ml_price_predictions WHERE loading_date>DATE '2026-10-26'
        AND (actual_price_rub IS NOT NULL OR abs_error_rub IS NOT NULL OR ape_pct IS NOT NULL)''')==0
    with conn.cursor() as cur:
        cur.execute('SELECT actual_price_rub,predicted_price_rub FROM mart.ml_price_predictions WHERE actual_price_rub IS NOT NULL')
        values=np.array(cur.fetchall())
        cur.execute('SELECT metrics FROM mart.ml_runs ORDER BY created_at DESC LIMIT 1')
        metrics=cur.fetchone()[0]
    errors=values[:,0]-values[:,1]
    assert metrics['mae_rub']==pytest.approx(np.mean(abs(errors)))
    assert metrics['rmse_rub']==pytest.approx(np.sqrt(np.mean(errors**2)))
    assert metrics['mape_pct']==pytest.approx(np.mean(abs(errors/values[:,0]))*100)
    assert metrics['r2']==pytest.approx(1-np.sum(errors**2)/np.sum((values[:,0]-values[:,0].mean())**2))
    assert metrics['test_rows']==len(values)


def fingerprint(conn):
    result={}
    for table,key,exclude in [('core.prices','id',[]),('core.dq_quarantine_prices','price_id',[]),
       ('core.price_body_groups','price_id,body_group',[]),('core.price_months','price_id,price_date',[]),
       ('mart.mart_market_corridor','month,loading_city_gcid,unloading_city_gcid,body_group,weight_category',[]),
       ('mart.ml_price_predictions','price_id',['scored_at'])]:
        expr='to_jsonb(t)'+''.join(f"-'{c}'" for c in exclude)
        result[table]=scalar(conn,f"SELECT md5(string_agg(md5(({expr})::text),'' ORDER BY {key})) FROM {table} t")
    return result


def test_full_rerun_and_partial_backfill_are_idempotent(conn):
    before=fingerprint(conn)
    source_init(); etl(); dwh_marts(); training(); scoring()
    assert fingerprint(conn)==before
    etl('2026-10-05','2026-10-10'); dwh_marts(); scoring()
    assert fingerprint(conn)==before


def test_database_edge_cases_and_correction(conn):
    # Temporary source fixtures are outside the synthetic snapshot; always cleaned.
    try:
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO raw.prices(id,loading_date,loading_city_gcid,unloading_city_gcid,
                distance,total_weight,total_volume,price,currency_code,nearest_rate_date,body_type)
                VALUES(-1,'2040-01-01',1001,1001,10,9.95,120,2000,'643',NULL,57),
                (-2,'2040-01-01',1001,1003,10,10,120,10,'840','2026-10-24',46),
                (-3,'2040-01-01',1001,1003,10,10,120,10,'840',NULL,56),
                (-4,'2040-01-01',99999,1003,10,10,120,2000,'643',NULL,56)''')
            cur.execute("INSERT INTO raw.price_dates(price_id,price_date) VALUES(-1,'2040-01-01'),(-2,'2040-01-01')")
            cur.execute('INSERT INTO raw.price_body_types(price_id,body_type_id) VALUES(-1,57),(-1,61)')
        etl('2040-01-01','2040-01-01')
        assert scalar(conn,'SELECT count(*) FROM core.prices WHERE id<0')==2
        assert scalar(conn,"SELECT weight_category FROM core.prices WHERE id=-1")=='FTL'
        assert scalar(conn,"SELECT body_group FROM core.price_body_groups WHERE price_id=-1")=='Тент'
        assert scalar(conn,"SELECT count(*) FROM core.price_body_groups WHERE price_id=-1")==1
        assert scalar(conn,'SELECT count(*) FROM core.dq_quarantine_prices WHERE price_id<0')==2
        with conn.cursor() as cur:
            cur.execute('UPDATE raw.prices SET price=0 WHERE id=-1')
        etl('2040-01-01','2040-01-01')
        assert scalar(conn,'SELECT count(*) FROM core.prices WHERE id=-1')==0
        assert scalar(conn,'SELECT count(*) FROM core.dq_quarantine_prices WHERE price_id=-1')==1
    finally:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM raw.prices WHERE id<0')
        etl('2040-01-01','2040-01-01')
