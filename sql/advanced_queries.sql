-- 1. Product counts by rating level.
SELECT rating_level, COUNT(*) AS product_count
FROM product_analytics
GROUP BY rating_level
ORDER BY product_count DESC, rating_level;

-- 2. Top three rating ranks in each main category, including ties.
SELECT main_category, product_id, product_name, rating, rating_rank
FROM category_product_rankings
WHERE rating_rank <= 3
ORDER BY main_category, rating_rank, product_id;

-- 3. Average price and savings in INR by main category.
SELECT main_category, COUNT(*) AS product_count,
       ROUND(AVG(discounted_price), 2) AS average_price_inr,
       ROUND(AVG(savings_inr), 2) AS average_savings_inr
FROM product_analytics
GROUP BY main_category
ORDER BY product_count DESC, main_category;

-- 4. Missing numeric data for follow-up.
SELECT product_id, product_name, missing_numeric_fields
FROM product_analytics
WHERE missing_numeric_fields > 0
ORDER BY missing_numeric_fields DESC, product_id;

-- 5. Price consistency in previously stored products.
SELECT product_id, actual_price, discounted_price
FROM product_analytics
WHERE discounted_price > actual_price
ORDER BY product_id;
