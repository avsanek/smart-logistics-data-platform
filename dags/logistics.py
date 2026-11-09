"""Daily refresh of a fixed assignment snapshot; model cache prevents retraining unchanged data."""
from datetime import timedelta
import subprocess
import sys

import pendulum
from airflow import DAG
from airflow.models.param import Param
from airflow.operators.python import PythonOperator

from etl.db import ROOT, artifact_dir, event
from etl.pipeline import source_init, etl, dwh_marts
from etl.clickhouse import sync
from ml.pipeline import training, scoring


def process_window(params, dag_run=None, **_):
    config=dag_run.conf if dag_run else {}
    etl(config.get('start_date',params['start_date']),config.get('end_date',params['end_date']))


def verify():
    subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
                    '--junitxml='+str(artifact_dir()/'pytest.xml'),str(ROOT/'tests')],check=True)
    event('PIPELINE_SUCCESS')


with DAG(
    dag_id='smart_logistics',description='raw → core → mart → CatBoost → ClickHouse → verification',
    start_date=pendulum.datetime(2026,10,25,tz='UTC'),schedule='@daily',catchup=False,
    is_paused_upon_creation=False,max_active_runs=1,max_active_tasks=1,
    default_args={'retries':2,'retry_delay':timedelta(seconds=30),'execution_timeout':timedelta(minutes=40)},
    params={'start_date':Param('1900-01-01',type='string',format='date'),
            'end_date':Param('2100-01-01',type='string',format='date')},
    tags=['logistics','assignment'],
) as dag:
    tasks=[]
    for name,fn in [('source_init',source_init),('etl',process_window),('dwh_marts',dwh_marts),
                    ('ml_training',training),('batch_scoring',scoring),('clickhouse_sync',sync),('verification',verify)]:
        tasks.append(PythonOperator(task_id=name,python_callable=fn))
    for first,second in zip(tasks,tasks[1:]):
        first >> second
