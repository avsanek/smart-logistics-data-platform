INSERT INTO bootstrap(version) VALUES(1);
CREATE INDEX prices_loading_date_idx ON prices(loading_date);
CREATE INDEX price_dates_date_idx ON price_dates(price_date, price_id);
