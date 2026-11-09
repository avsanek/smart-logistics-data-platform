"""Python ETL with bounded memory and atomic replacement of a loading-date window."""
import json
import os
import subprocess
from collections import Counter
from datetime import date

from psycopg2.extras import RealDictCursor

from etl.db import ROOT, copy_rows, event, sql_file, transaction
from etl.quality import validate, volume_category, weight_category

FACT_COLUMNS = [
    'id','loading_date','loading_city_gcid','unloading_city_gcid','distance',
    'total_weight','total_volume','price_rub','currency_code','rate_date','rate_value',
    'weight_category','volume_category','body_type','organization_id','price_type',
    'is_fact','complex','outlier_mark',
]


def source_init() -> None:
    with transaction() as conn:
        sql_file(conn, 'warehouse.sql')
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT version FROM raw.bootstrap WHERE version=1')
            initialized = cur.fetchone() is not None
        if not initialized:
            env = {**os.environ, 'PGOPTIONS': '-c search_path=raw,public'}
            subprocess.run([
                'psql','-X','--no-password','--single-transaction','-v','ON_ERROR_STOP=1',
                '-v','n_prices=300000','-f',str(ROOT/'sql/schema.sql'),
                '-f',str(ROOT/'sql/synthetic.sql'),'-f',str(ROOT/'sql/source-complete.sql'),
            ], env=env, check=True)
        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM raw.prices')
            count = cur.fetchone()[0]
    event('source_ready', rows=count, generated=not initialized)


def etl(start_date: str = '1900-01-01', end_date: str = '2100-01-01') -> None:
    if date.fromisoformat(start_date) > date.fromisoformat(end_date):
        raise ValueError('start_date must be <= end_date')
    params = {'start_date':start_date, 'end_date':end_date}
    stats: Counter = Counter()
    with transaction() as conn:
        sql_file(conn,'dimensions.sql')
        with conn.cursor() as cur:
            # Also remove old ids whose loading_date has moved outside the processed window.
            cur.execute('''DELETE FROM core.prices c WHERE c.loading_date BETWEEN %(start_date)s AND %(end_date)s
                OR EXISTS (SELECT 1 FROM raw.prices r WHERE r.id=c.id
                AND r.loading_date BETWEEN %(start_date)s AND %(end_date)s)''', params)
            cur.execute('''DELETE FROM core.dq_quarantine_prices c WHERE c.loading_date BETWEEN %(start_date)s AND %(end_date)s
                OR EXISTS (SELECT 1 FROM raw.prices r WHERE r.id=c.price_id
                AND r.loading_date BETWEEN %(start_date)s AND %(end_date)s)''', params)
        with conn.cursor(name='source_stream', cursor_factory=RealDictCursor) as reader:
            reader.itersize = 10000
            reader.execute('''WITH rates AS (
                SELECT DISTINCT ON(num_code,setting_date) num_code,setting_date,value
                FROM raw.exchange_rates ORDER BY num_code,setting_date,id
            ) SELECT p.*, c1.gc_id IS NOT NULL AS loading_city_exists,
                c2.gc_id IS NOT NULL AS unloading_city_exists,
                CASE WHEN p.currency_code='643' THEN 1.0 ELSE r.value END AS rate_value
                FROM raw.prices p LEFT JOIN core.cities c1 ON c1.gc_id=p.loading_city_gcid
                LEFT JOIN core.cities c2 ON c2.gc_id=p.unloading_city_gcid
                LEFT JOIN rates r ON r.num_code=p.currency_code AND r.setting_date=p.nearest_rate_date
                WHERE p.loading_date BETWEEN %(start_date)s AND %(end_date)s ORDER BY p.id''', params)
            while batch := reader.fetchmany(10000):
                valid, quarantine = [], []
                for row in batch:
                    stats['read'] += 1
                    reasons = validate(row)
                    if reasons:
                        stats['quarantined'] += 1
                        stats.update(reasons)
                        quarantine.append((row['id'],row['loading_date'],
                            '{'+','.join(reasons)+'}',json.dumps(dict(row),default=str,ensure_ascii=False)))
                    else:
                        stats['accepted'] += 1
                        row['price_rub'] = row['price'] * row['rate_value']
                        row['rate_date'] = row['nearest_rate_date'] if row['currency_code'] != '643' else None
                        row['weight_category'] = row['weight_category'] or weight_category(row['total_weight'])
                        row['volume_category'] = row['volume_category'] or volume_category(row['total_volume'])
                        valid.append(tuple(row[c] for c in FACT_COLUMNS))
                copy_rows(conn,'core.prices',FACT_COLUMNS,valid)
                copy_rows(conn,'core.dq_quarantine_prices',
                    ['price_id','loading_date','reason_codes','source_record'],quarantine)
        sql_file(conn,'bridges.sql',params)
    event('etl_complete',start_date=start_date,end_date=end_date,**stats)


def dwh_marts() -> None:
    with transaction() as conn:
        sql_file(conn,'marts.sql')
        with conn.cursor() as cur:
            cur.execute('SELECT count(*),sum(trips_count) FROM mart.mart_market_corridor')
            rows, memberships = cur.fetchone()
    event('marts_complete',rows=rows,trip_memberships=memberships)
