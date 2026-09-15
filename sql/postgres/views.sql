-- Prices are in the source dataset's currency: Indian rupees (INR).
CREATE OR REPLACE VIEW product_analytics AS
SELECT
    product_id,
    product_name,
    category,
    CASE
        WHEN category IS NULL OR TRIM(category) = '' THEN 'Uncategorized'
        WHEN POSITION('|' IN category) > 0 THEN SPLIT_PART(category, '|', 1)
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
    (actual_price IS NULL)::int
        + (discounted_price IS NULL)::int
        + (discount_percentage IS NULL)::int
        + (rating IS NULL)::int
        + (rating_count IS NULL)::int AS missing_numeric_fields
FROM products;

CREATE OR REPLACE VIEW category_product_rankings AS
SELECT
    product_analytics.*,
    CASE WHEN rating IS NOT NULL THEN
        DENSE_RANK() OVER (
            PARTITION BY main_category
            ORDER BY rating DESC NULLS LAST
        )
    END AS rating_rank
FROM product_analytics;

