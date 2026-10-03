-- QuickMart foreign keys (architecture doc, "Demo database: QuickMart"), added by
-- db/generate.py after every table is loaded. ADD CONSTRAINT validates every existing row.
ALTER TABLE stores  ADD FOREIGN KEY (region_id)   REFERENCES regions (region_id);
ALTER TABLE sales   ADD FOREIGN KEY (customer_id) REFERENCES customers (customer_id);
ALTER TABLE sales   ADD FOREIGN KEY (product_id)  REFERENCES products (product_id);
ALTER TABLE sales   ADD FOREIGN KEY (store_id)    REFERENCES stores (store_id);
ALTER TABLE sales   ADD FOREIGN KEY (region_id)   REFERENCES regions (region_id);
ALTER TABLE returns ADD FOREIGN KEY (order_id)    REFERENCES sales (order_id);
