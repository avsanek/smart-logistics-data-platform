import json
import psycopg2
import pytest
from etl.clickhouse import KEYS, METRICS, enabled, request, sync


@pytest.mark.skipif(not enabled(),reason='ClickHouse deliberately disabled for PostgreSQL-only execution')
def test_clickhouse_every_row_and_idempotence():
    with psycopg2.connect(connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT '+','.join(KEYS+METRICS)+' FROM mart.mart_market_corridor ORDER BY '+','.join(KEYS))
            expected=cur.fetchall()
    query='SELECT '+','.join(KEYS+METRICS)+' FROM mart.market_corridor ORDER BY '+','.join(KEYS)+' FORMAT JSONEachRow'
    before=request(query)
    actual=[json.loads(line) for line in before.splitlines()]
    assert len(actual)==len(expected)>0
    for row,other in zip(expected,actual):
        for name,value in zip(KEYS+METRICS,row):
            if name=='month':
                assert str(value)==other[name]
            elif isinstance(value,float):
                assert value==pytest.approx(other[name],rel=1e-12,abs=1e-8)
            else:
                assert value==other[name]
    sync()
    assert request(query)==before
