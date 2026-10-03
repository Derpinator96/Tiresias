-- QuickMart schema (architecture doc, "Demo database: QuickMart").
-- Primary keys and foreign keys only. Postgres does not index foreign key columns on its
-- own, so the only indexes are the primary key indexes, and the slow queries stay slow.
DROP TABLE IF EXISTS returns, sales, customers, products, stores, regions CASCADE;

CREATE TABLE regions (
    region_id   integer PRIMARY KEY,
    region_name text    NOT NULL
);

CREATE TABLE stores (
    store_id  integer PRIMARY KEY,
    region_id integer NOT NULL REFERENCES regions (region_id),
    city      text    NOT NULL,
    opened_on date    NOT NULL
);

CREATE TABLE customers (
    customer_id integer PRIMARY KEY,
    email       text    NOT NULL,
    full_name   text    NOT NULL,
    phone       text,
    city        text    NOT NULL,
    signup_date date    NOT NULL,
    segment     text    NOT NULL
);

CREATE TABLE products (
    product_id integer       PRIMARY KEY,
    name       text          NOT NULL,
    category   text          NOT NULL,
    brand      text          NOT NULL,
    unit_price numeric(10,2) NOT NULL
);

CREATE TABLE sales (
    order_id         bigint        PRIMARY KEY,
    customer_id      integer       NOT NULL REFERENCES customers (customer_id),
    product_id       integer       NOT NULL REFERENCES products (product_id),
    store_id         integer       NOT NULL REFERENCES stores (store_id),
    region_id        integer       NOT NULL REFERENCES regions (region_id),
    transaction_date date          NOT NULL,
    quantity         integer       NOT NULL,
    amount           numeric(12,2) NOT NULL,
    payment_method   text          NOT NULL
);

CREATE TABLE returns (
    return_id   integer PRIMARY KEY,
    order_id    bigint  NOT NULL REFERENCES sales (order_id),
    return_date date    NOT NULL,
    reason      text    NOT NULL
);
