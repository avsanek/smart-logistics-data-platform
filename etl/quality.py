"""Source validation rules; no target-derived features or outlier recomputation."""
import math
from decimal import Decimal, ROUND_HALF_UP


def weight_category(weight: float) -> str:
    rounded = Decimal(str(weight)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    for threshold, label in [('30','G20T'),('10','FTL'),('5','10T'),('2.5','5T'),('0.5','L5T')]:
        if rounded >= Decimal(threshold):
            return label
    return 'OTH'


def volume_category(volume: float) -> str:
    return 'FTL' if 0 < volume <= 120 else 'OTH'


def validate(row: dict) -> list[str]:
    reasons = []
    for field, code, strictly_positive in [
        ('price','INVALID_PRICE',True),('distance','INVALID_DISTANCE',True),
        ('total_weight','INVALID_WEIGHT',False),('total_volume','INVALID_VOLUME',False),
    ]:
        value = row.get(field)
        if value is None or not math.isfinite(value) or (value <= 0 if strictly_positive else value < 0):
            reasons.append(code)
    if row['currency_code'] == '643' and row['price'] <= 1000:
        reasons.append('RUB_PRICE_LE_1000')
    if not row['loading_city_exists']:
        reasons.append('UNKNOWN_LOADING_CITY')
    if not row['unloading_city_exists']:
        reasons.append('UNKNOWN_UNLOADING_CITY')
    if row['currency_code'] not in ('643','840','978'):
        reasons.append('UNSUPPORTED_CURRENCY')
    elif row['currency_code'] != '643' and (
        row['rate_value'] is None or not math.isfinite(row['rate_value']) or row['rate_value'] <= 0
    ):
        reasons.append('MISSING_EXACT_RATE')
    return reasons
