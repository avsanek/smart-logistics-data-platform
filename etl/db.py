"""Shared PostgreSQL transactions, COPY and structured logging."""
import csv
import io
import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
AS_OF = '2026-10-26'
LOCK_ID = 2026102601
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
LOG = logging.getLogger('logistics')


def event(name: str, **fields) -> None:
    LOG.info(json.dumps({'event': name, **fields}, ensure_ascii=False, default=str))


@contextmanager
def transaction():
    conn = psycopg2.connect(connect_timeout=15, application_name='logistics_pipeline')
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute('SET LOCAL lock_timeout = \'60s\'')
                cur.execute('SET LOCAL statement_timeout = \'30min\'')
                cur.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
            yield conn
    finally:
        conn.close()


def sql_file(conn, name: str, params=None) -> None:
    with conn.cursor() as cur:
        cur.execute((ROOT / 'sql' / name).read_text(encoding='utf-8-sig'), params)


def copy_rows(conn, table: str, columns: list[str], rows: Iterable) -> None:
    """One COPY per chunk, with CSV NULL distinct from an empty string."""
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator='\n')
    for row in rows:
        writer.writerow(['\\N' if v is None else v for v in row])
    stream.seek(0)
    with conn.cursor() as cur:
        cur.copy_expert(f"COPY {table} ({','.join(columns)}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')", stream)


def artifact_dir() -> Path:
    path = Path(os.environ.get('ARTIFACT_DIR', '/app/artifacts'))
    path.mkdir(parents=True, exist_ok=True)
    return path
