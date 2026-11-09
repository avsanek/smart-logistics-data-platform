-- Full atomic refresh: all months of long-lived prices are updated after a backfill.
-- DISTINCT eliminates duplicate dates in a calendar month and duplicate child body types.
CREATE TEMP TABLE corridor_new ON COMMIT DROP AS
WITH evidence AS (
 SELECT DISTINCT date_trunc('month',d.price_date)::date AS month,
 p.id,p.loading_city_gcid,p.unloading_city_gcid,b.body_group,p.weight_category,
 p.price_rub,p.distance,p.organization_id,p.price_type
 FROM core.prices p JOIN core.price_months d ON d.price_id=p.id
 JOIN core.price_body_groups b ON b.price_id=p.id
 WHERE p.is_fact AND p.price_type IN(1,2,3,4,5,9) AND NOT p.complex
 AND NOT p.outlier_mark AND p.price_rub>0 AND p.distance>0
 AND d.price_date<=DATE '2026-10-26'
), aggregate_cells AS (
 SELECT month,loading_city_gcid,unloading_city_gcid,body_group,weight_category,
 percentile_cont(.25) WITHIN GROUP(ORDER BY price_rub) AS p25_trip,
 percentile_cont(.5) WITHIN GROUP(ORDER BY price_rub) AS median_trip,
 percentile_cont(.75) WITHIN GROUP(ORDER BY price_rub) AS p75_trip,
 avg(price_rub) AS avg_trip,
 percentile_cont(.25) WITHIN GROUP(ORDER BY price_rub/distance) AS p25_km,
 percentile_cont(.5) WITHIN GROUP(ORDER BY price_rub/distance) AS median_km,
 percentile_cont(.75) WITHIN GROUP(ORDER BY price_rub/distance) AS p75_km,
 count(*) AS trips_count,
 count(DISTINCT organization_id) FILTER(WHERE price_type IN(3,9)) AS carriers_count,
 stddev_samp(price_rub)/nullif(avg(price_rub),0) AS cv_rate
 FROM evidence GROUP BY 1,2,3,4,5
)
SELECT a.*,
 100*(a.median_trip/nullif(m.median_trip,0)-1) AS mom_pct,
 100*(a.median_trip/nullif(y.median_trip,0)-1) AS yoy_pct,
 CASE WHEN a.trips_count>=30 AND a.carriers_count>=5
 -- Freshness is measured from the date representing this calendar month.
 AND DATE '2026-10-26'-a.month<=30
 THEN 'HIGH' WHEN a.trips_count>=10 THEN 'MEDIUM' ELSE 'LOW_DATA' END AS reliability_level
FROM aggregate_cells a
LEFT JOIN aggregate_cells m ON m.month=(a.month-interval '1 month')::date
 AND (m.loading_city_gcid,m.unloading_city_gcid,m.body_group,m.weight_category)=
 (a.loading_city_gcid,a.unloading_city_gcid,a.body_group,a.weight_category)
LEFT JOIN aggregate_cells y ON y.month=(a.month-interval '1 year')::date
 AND (y.loading_city_gcid,y.unloading_city_gcid,y.body_group,y.weight_category)=
 (a.loading_city_gcid,a.unloading_city_gcid,a.body_group,a.weight_category);
CREATE TABLE IF NOT EXISTS mart.mart_market_corridor (LIKE corridor_new INCLUDING ALL);
CREATE UNIQUE INDEX IF NOT EXISTS corridor_grain ON mart.mart_market_corridor
 (month,loading_city_gcid,unloading_city_gcid,body_group,weight_category);
DELETE FROM mart.mart_market_corridor;
INSERT INTO mart.mart_market_corridor SELECT * FROM corridor_new;
ANALYZE mart.mart_market_corridor;
