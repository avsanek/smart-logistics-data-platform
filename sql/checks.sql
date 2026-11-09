-- docker compose exec -T postgres psql -U logistics -d logistics -f /.../checks.sql
-- Alternatively paste these queries in a SQL client (localhost:55432).
SELECT 'raw' AS layer,count(*) FROM raw.prices UNION ALL
SELECT 'core',count(*) FROM core.prices UNION ALL
SELECT 'quarantine',count(*) FROM core.dq_quarantine_prices UNION ALL
SELECT 'corridor',count(*) FROM mart.mart_market_corridor UNION ALL
SELECT 'predictions',count(*) FROM mart.ml_price_predictions;

SELECT reason,count(*) FROM core.dq_quarantine_prices,
LATERAL unnest(reason_codes) AS reason GROUP BY reason ORDER BY count(*) DESC;

SELECT currency_code,count(*),sum(price_rub) FROM core.prices GROUP BY currency_code;
SELECT * FROM mart.mart_market_corridor ORDER BY trips_count DESC LIMIT 20;

-- One route, all indicators and exact calendar comparison values:
SELECT a.month,l.name AS loading_city,u.name AS unloading_city,a.body_group,a.weight_category,
a.p25_trip,a.median_trip,a.p75_trip,a.avg_trip,a.p25_km,a.median_km,a.p75_km,
a.trips_count,a.carriers_count,a.cv_rate,a.mom_pct,a.yoy_pct,a.reliability_level
FROM mart.mart_market_corridor a
JOIN core.cities l ON l.gc_id=a.loading_city_gcid JOIN core.cities u ON u.gc_id=a.unloading_city_gcid
WHERE a.loading_city_gcid=1001 AND a.unloading_city_gcid=1003 AND a.body_group='Тент'
AND a.weight_category='FTL' ORDER BY a.month;

-- Independently recalculate a cell. DISTINCT is required for dates and child body types.
WITH facts AS (
 SELECT DISTINCT p.id,p.price_rub,p.distance,p.organization_id,p.price_type
 FROM core.prices p JOIN core.price_months d ON d.price_id=p.id
 JOIN core.price_body_groups b ON b.price_id=p.id
 WHERE d.price_date>='2026-10-01' AND d.price_date<='2026-10-26'
 AND p.loading_city_gcid=1001 AND p.unloading_city_gcid=1003
 AND b.body_group='Тент' AND p.weight_category='FTL'
 AND p.is_fact AND p.price_type IN(1,2,3,4,5,9) AND NOT p.complex AND NOT p.outlier_mark
)
SELECT percentile_cont(ARRAY[.25,.5,.75]) WITHIN GROUP(ORDER BY price_rub) AS trip_quartiles,
percentile_cont(ARRAY[.25,.5,.75]) WITHIN GROUP(ORDER BY price_rub/distance) AS km_quartiles,
avg(price_rub),count(*) AS trips_count,
count(DISTINCT organization_id) FILTER(WHERE price_type IN(3,9)) AS carriers_count,
stddev_samp(price_rub)/nullif(avg(price_rub),0) AS cv_rate FROM facts;

SELECT model_name,metrics FROM mart.ml_runs;
SELECT loading_date,count(*),avg(ape_pct) AS mape_pct,avg(abs_error_rub) AS mae_rub
FROM mart.ml_price_predictions GROUP BY loading_date ORDER BY loading_date;

DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM mart.ml_price_predictions WHERE loading_date>'2026-10-26'
 AND (actual_price_rub IS NOT NULL OR abs_error_rub IS NOT NULL OR ape_pct IS NOT NULL))
 THEN RAISE EXCEPTION 'Future target leakage'; END IF;
 IF (SELECT count(*) FROM raw.prices)<>(SELECT count(*) FROM core.prices)
 +(SELECT count(*) FROM core.dq_quarantine_prices) THEN RAISE EXCEPTION 'Unaccounted source rows'; END IF;
 IF EXISTS(SELECT 1 FROM mart.mart_market_corridor WHERE month>'2026-10-01')
 THEN RAISE EXCEPTION 'Future month in corridor'; END IF;
END $$;
