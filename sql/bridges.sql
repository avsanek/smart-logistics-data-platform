INSERT INTO core.price_body_groups(price_id,body_group)
SELECT DISTINCT p.id,core.body_group(CASE WHEN coalesce(pb.body_type_id,p.body_type) IS NULL
 THEN NULL ELSE coalesce(b.std_id,-1) END)
FROM core.prices p
LEFT JOIN raw.price_body_types pb ON pb.price_id=p.id
LEFT JOIN raw.body_types b ON b.id=CASE WHEN pb.id IS NOT NULL THEN pb.body_type_id ELSE p.body_type END
WHERE p.loading_date BETWEEN %(start_date)s AND %(end_date)s;
INSERT INTO core.price_months(price_id,price_date)
SELECT DISTINCT d.price_id,d.price_date FROM raw.price_dates d
JOIN core.prices p ON p.id=d.price_id
WHERE p.loading_date BETWEEN %(start_date)s AND %(end_date)s;
