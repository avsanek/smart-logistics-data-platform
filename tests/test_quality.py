import pytest
from etl.quality import validate, volume_category, weight_category


@pytest.mark.parametrize('weight,expected',[(0,'OTH'),(.44,'OTH'),(.45,'L5T'),(.5,'L5T'),
 (2.44,'L5T'),(2.45,'5T'),(2.5,'5T'),(4.95,'10T'),(5,'10T'),(9.95,'FTL'),
 (10,'FTL'),(29.95,'G20T'),(30,'G20T'),(40,'G20T')])
def test_weight_rounding_and_boundaries(weight,expected):
    assert weight_category(weight)==expected


@pytest.mark.parametrize('volume,expected',[(0,'OTH'),(.01,'FTL'),(120,'FTL'),(120.01,'OTH')])
def test_volume_boundaries(volume,expected):
    assert volume_category(volume)==expected


def valid_row():
    return dict(price=2000.,distance=10.,total_weight=0.,total_volume=0.,currency_code='643',
                rate_value=1.,loading_city_exists=True,unloading_city_exists=True)


@pytest.mark.parametrize('changes,reason',[
 ({'price':0},'INVALID_PRICE'),({'price':1000},'RUB_PRICE_LE_1000'),
 ({'distance':0},'INVALID_DISTANCE'),({'distance':float('nan')},'INVALID_DISTANCE'),
 ({'total_weight':-1},'INVALID_WEIGHT'),({'total_volume':-1},'INVALID_VOLUME'),
 ({'loading_city_exists':False},'UNKNOWN_LOADING_CITY'),
 ({'unloading_city_exists':False},'UNKNOWN_UNLOADING_CITY'),
 ({'currency_code':'840','rate_value':None},'MISSING_EXACT_RATE'),
 ({'currency_code':'978','rate_value':0},'MISSING_EXACT_RATE'),
 ({'currency_code':'999'},'UNSUPPORTED_CURRENCY')])
def test_validation(changes,reason):
    row=valid_row(); row.update(changes)
    assert reason in validate(row)


def test_foreign_price_below_1000_and_zero_weight_valid():
    row=valid_row(); row.update(price=10.,currency_code='840',rate_value=90.)
    assert validate(row)==[]
