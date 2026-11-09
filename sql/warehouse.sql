CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE TABLE IF NOT EXISTS raw.bootstrap(version integer PRIMARY KEY, initialized_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS core.cities(
 gc_id integer PRIMARY KEY, source_id bigint NOT NULL, name text NOT NULL,
 region text NOT NULL, latitude double precision, longitude double precision
);
CREATE TABLE IF NOT EXISTS core.prices(
 id bigint PRIMARY KEY, loading_date date NOT NULL,
 loading_city_gcid integer NOT NULL REFERENCES core.cities(gc_id),
 unloading_city_gcid integer NOT NULL REFERENCES core.cities(gc_id),
 distance double precision NOT NULL CHECK(distance>0),
 total_weight double precision NOT NULL CHECK(total_weight>=0),
 total_volume double precision NOT NULL CHECK(total_volume>=0),
 price_rub double precision NOT NULL CHECK(price_rub>0),
 currency_code text NOT NULL, rate_date date, rate_value double precision NOT NULL,
 weight_category text NOT NULL, volume_category text NOT NULL,
 body_type integer, organization_id integer, price_type integer NOT NULL,
 is_fact boolean NOT NULL, complex boolean NOT NULL, outlier_mark boolean NOT NULL
);
CREATE INDEX IF NOT EXISTS core_prices_loading ON core.prices(loading_date);
CREATE TABLE IF NOT EXISTS core.price_body_groups(
 price_id bigint REFERENCES core.prices(id) ON DELETE CASCADE,
 body_group text NOT NULL, PRIMARY KEY(price_id,body_group)
);
CREATE TABLE IF NOT EXISTS core.price_months(
 price_id bigint REFERENCES core.prices(id) ON DELETE CASCADE,
 price_date date NOT NULL, PRIMARY KEY(price_id,price_date)
);
CREATE INDEX IF NOT EXISTS core_months_date ON core.price_months(price_date,price_id);
CREATE TABLE IF NOT EXISTS core.dq_quarantine_prices(
 price_id bigint PRIMARY KEY, loading_date date NOT NULL, reason_codes text[] NOT NULL,
 source_record jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS mart.ml_price_predictions(
 price_id bigint PRIMARY KEY, loading_date date NOT NULL, loading_city_gcid integer NOT NULL,
 unloading_city_gcid integer NOT NULL, body_group text NOT NULL,
 actual_price_rub double precision, predicted_price_rub double precision NOT NULL,
 abs_error_rub double precision, ape_pct double precision, model_name text NOT NULL,
 scored_at timestamptz NOT NULL DEFAULT now(),
 CHECK(loading_date <= DATE '2026-10-26' OR
 (actual_price_rub IS NULL AND abs_error_rub IS NULL AND ape_pct IS NULL))
);
CREATE TABLE IF NOT EXISTS mart.ml_runs(
 model_name text PRIMARY KEY, metrics jsonb NOT NULL, created_at timestamptz DEFAULT now()
);
CREATE OR REPLACE FUNCTION core.body_group(std_id integer) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
 SELECT CASE std_id WHEN 56 THEN 'Тент' WHEN 4 THEN 'Рефрижератор'
 WHEN 2 THEN 'Изотерм' WHEN 15 THEN 'Борт' WHEN NULL THEN 'Не указан'
 ELSE CASE WHEN std_id IS NULL THEN 'Не указан' ELSE 'Прочие' END END
$$;
