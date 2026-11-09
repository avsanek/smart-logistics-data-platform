"""Explicit feature allowlist. No learned preprocessing or historical price aggregates."""
import numpy as np
import pandas as pd

CATEGORICAL = [
    'loading_city_gcid','unloading_city_gcid','origin_region','destination_region',
    'body_group','weight_category','volume_category',
]
NUMERIC = [
    'origin_latitude','origin_longitude','destination_latitude','destination_longitude',
    'distance','total_weight','total_volume',
]
CALENDAR = ['year','month','day_of_week','day_of_year',
            'month_sin','month_cos','day_of_week_sin','day_of_week_cos','day_of_year_sin','day_of_year_cos']
FEATURES = CATEGORICAL + NUMERIC + CALENDAR


def features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame[CATEGORICAL+NUMERIC].copy()
    for col in CATEGORICAL:
        result[col] = result[col].fillna('Не указан').astype(str)
    for col in NUMERIC:
        result[col] = pd.to_numeric(result[col], errors='coerce')
    dt = pd.to_datetime(frame['loading_date'])
    result['year'] = dt.dt.year
    result['month'] = dt.dt.month
    result['day_of_week'] = dt.dt.dayofweek
    result['day_of_year'] = dt.dt.dayofyear
    for col,period in [('month',12),('day_of_week',7),('day_of_year',365.25)]:
        result[col+'_sin'] = np.sin(2*np.pi*result[col]/period)
        result[col+'_cos'] = np.cos(2*np.pi*result[col]/period)
    return result[FEATURES]


def split_masks(frame: pd.DataFrame):
    dt = pd.to_datetime(frame['loading_date'])
    return ((dt >= '2026-07-26') & (dt < '2026-10-05'),
            (dt >= '2026-10-05') & (dt <= '2026-10-26'), dt > '2026-10-26')
