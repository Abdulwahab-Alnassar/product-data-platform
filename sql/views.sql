-- Prices are in the source dataset's currency: Indian rupees (INR).
CREATE VIEW IF NOT EXISTS product_analytics AS
SELECT
    product_id,
    product_name,
    category,
    CASE
        WHEN category IS NULL OR TRIM(category) = '' THEN 'Uncategorized'
        WHEN INSTR(category, '|') > 0
            THEN SUBSTR(category, 1, INSTR(category, '|') - 1)
        ELSE category
    END AS main_category,
    actual_price,
    discounted_price,
    discount_percentage,
    ROUND(actual_price - discounted_price, 2) AS savings_inr,
    rating,
    rating_count,
    CASE
        WHEN rating IS NULL THEN 'Unknown'
        WHEN rating >= 4.5 THEN 'Excellent'
        WHEN rating >= 4.0 THEN 'Good'
        WHEN rating >= 3.0 THEN 'Average'
        ELSE 'Low'
    END AS rating_level,
    (actual_price IS NULL)
        + (discounted_price IS NULL)
        + (discount_percentage IS NULL)
        + (rating IS NULL)
        + (rating_count IS NULL) AS missing_numeric_fields
FROM products;

CREATE VIEW IF NOT EXISTS category_product_rankings AS
SELECT
    product_analytics.*,
    CASE WHEN rating IS NOT NULL THEN
        DENSE_RANK() OVER (
            PARTITION BY main_category
            ORDER BY rating DESC
        )
    END AS rating_rank
FROM product_analytics;
