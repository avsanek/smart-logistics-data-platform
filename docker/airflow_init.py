"""Initialize metadata and a local demo account; never recreate the source."""
import os
import subprocess
import psycopg2

conn=psycopg2.connect(connect_timeout=15)
conn.autocommit=True
try:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname='airflow'")
        if not cur.fetchone():
            cur.execute('CREATE DATABASE airflow')
finally:
    conn.close()

subprocess.run(['airflow','db','migrate'],check=True)
from airflow.www.app import create_app

app=create_app()
with app.app_context():
    sm=app.appbuilder.sm
    if sm.find_user(username='admin') is None:
        user=sm.add_user(username='admin',first_name='Local',last_name='Demo',email='admin@example.invalid',
                         role=sm.find_role('Admin'),password=os.environ.get('AIRFLOW_ADMIN_PASSWORD','local_demo_only'))
        if not user:
            raise RuntimeError('Could not create Airflow admin')
print('AIRFLOW_INIT_SUCCESS',flush=True)
