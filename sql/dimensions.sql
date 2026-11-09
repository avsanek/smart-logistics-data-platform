INSERT INTO core.cities(gc_id, source_id, name, region, latitude, longitude)
SELECT DISTINCT ON(gc_id) gc_id,id,name,
 CASE WHEN strpos(full_name_local,',')>0 THEN
 COALESCE(NULLIF(btrim(substr(full_name_local, strpos(full_name_local,',')+1)),''),'Не указан') ELSE 'Не указан' END,
 latitude,longitude FROM raw.cities ORDER BY gc_id,id
ON CONFLICT(gc_id) DO UPDATE SET source_id=excluded.source_id,name=excluded.name,
 region=excluded.region,latitude=excluded.latitude,longitude=excluded.longitude;
