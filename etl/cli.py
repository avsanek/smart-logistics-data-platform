"""Container entrypoint. Exceptions propagate to the caller and produce nonzero exit codes."""
import argparse
import subprocess
import sys

from etl.db import ROOT, event
from etl.pipeline import dwh_marts, etl, source_init
from ml.pipeline import scoring, training
from etl.clickhouse import sync


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('stage',choices=['run','source_init','etl','dwh_marts','ml_training','batch_scoring','clickhouse_sync','test'])
    parser.add_argument('--start-date',default='1900-01-01')
    parser.add_argument('--end-date',default='2100-01-01')
    args = parser.parse_args()
    stages = {
        'source_init':source_init,'etl':lambda: etl(args.start_date,args.end_date),
        'dwh_marts':dwh_marts,'ml_training':training,'batch_scoring':scoring,'clickhouse_sync':sync,
        'test':lambda: subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
                                      str(ROOT/'tests')],check=True),
    }
    if args.stage=='run':
        for name,fn in stages.items():
            event('stage_start',stage=name)
            fn()
        event('PIPELINE_SUCCESS')
    else:
        stages[args.stage]()


if __name__=='__main__':
    main()
