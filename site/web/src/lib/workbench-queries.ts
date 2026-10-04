// Suggested "normal" queries for the workbench: fast lookups against QuickMart, each timed through
// /v1/private/query on 2026-10-04 at 10 to 45 ms (under the 100 ms slow threshold). The slow
// suggestions are not listed here: they come live from pg-prod's slow log (/api/workbench/suggestions).
export const NORMAL_QUERIES = [
  { id: "n_regions", label: "List the regions", sql: "SELECT region_id, region_name FROM regions ORDER BY region_id" },
  { id: "n_stores", label: "Stores in region 3", sql: "SELECT store_id, city, opened_on FROM stores WHERE region_id = 3 ORDER BY store_id" },
  { id: "n_products", label: "Most expensive products in one category", sql: "SELECT product_id, name, brand, unit_price FROM products WHERE category = (SELECT category FROM products ORDER BY product_id LIMIT 1) ORDER BY unit_price DESC LIMIT 20" },
  { id: "n_order", label: "Look up one order", sql: "SELECT order_id, transaction_date, quantity, amount FROM sales WHERE order_id = 1234567" },
  { id: "n_customer", label: "Look up one customer", sql: "SELECT customer_id, full_name, city, segment FROM customers WHERE customer_id = 4242" },
  { id: "n_segments", label: "Customers per segment", sql: "SELECT segment, COUNT(*) AS customers FROM customers GROUP BY segment ORDER BY customers DESC" },
];
