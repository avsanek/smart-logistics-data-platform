"""Atomic, idempotent replica of the PostgreSQL corridor using ClickHouse HTTP."""
import base64
import json
import os
import urllib.parse
import urllib.request

from etl.db import event, transaction

KEYS = ['month','loading_city_gcid','unloading_city_gcid','body_group','weight_category']
METRICS = ['p25_trip','median_trip','p75_trip','avg_trip','p25_km','median_km','p75_km',
           'trips_count','carriers_count','cv_rate','mom_pct','yoy_pct','reliability_level']


def enabled() -> bool:
    return bool(os.environ.get('CLICKHOUSE_URL'))


def request(query: str, body: bytes | None = None) -> str:
    url = os.environ['CLICKHOUSE_URL']+'/?'+urllib.parse.urlencode({'query':query})
    auth = base64.b64encode((os.environ.get('CLICKHOUSE_USER','logistics')+':'+
                            os.environ.get('CLICKHOUSE_PASSWORD','local_demo_only')).encode()).decode()
    req = urllib.request.Request(url,data=body if body is not None else b'',
                                 headers={'Authorization':'Basic '+auth})
    with urllib.request.urlopen(req,timeout=120) as response:
        return response.read().decode()


def sync() -> None:
    if not enabled():
        event('clickhouse_disabled')
        return
    # Shared PostgreSQL advisory lock prevents concurrent publishers swapping the same staging table.
    with transaction() as conn:
        request('CREATE DATABASE IF NOT EXISTS mart ENGINE=Atomic')
        definition = '''(month Date,loading_city_gcid Int32,unloading_city_gcid Int32,
            body_group String,weight_category String,p25_trip Float64,median_trip Float64,
            p75_trip Float64,avg_trip Float64,p25_km Float64,median_km Float64,p75_km Float64,
            trips_count UInt64,carriers_count UInt64,cv_rate Nullable(Float64),
            mom_pct Nullable(Float64),yoy_pct Nullable(Float64),reliability_level String)
            ENGINE=MergeTree ORDER BY(month,loading_city_gcid,unloading_city_gcid,body_group,weight_category)'''
        for table in ['market_corridor','market_corridor_staging']:
            request('CREATE TABLE IF NOT EXISTS mart.'+table+definition)
        request('TRUNCATE TABLE mart.market_corridor_staging')
        total = 0
        with conn.cursor(name='clickhouse_export') as cur:
            cur.execute('SELECT '+','.join(KEYS+METRICS)+' FROM mart.mart_market_corridor ORDER BY '+','.join(KEYS))
            while rows := cur.fetchmany(10000):
                data = '\n'.join(json.dumps(dict(zip(KEYS+METRICS,row)),default=str,ensure_ascii=False)
                                 for row in rows).encode()
                request('INSERT INTO mart.market_corridor_staging FORMAT JSONEachRow',data)
                total += len(rows)
        actual = int(request('SELECT count() FROM mart.market_corridor_staging'))
        if actual != total:
            raise ValueError(f'ClickHouse count mismatch: {actual} != {total}')
        request('EXCHANGE TABLES mart.market_corridor AND mart.market_corridor_staging')
    event('clickhouse_complete',rows=total)
