-- 1. Total number of products
SELECT COUNT(*) AS total_products
FROM products;


-- 2. Average product rating
SELECT ROUND(AVG(rating), 2) AS average_rating
FROM products
WHERE rating IS NOT NULL;


-- 3. Highest-rated popular products
SELECT
    product_id,
    product_name,
    rating,
    rating_count
FROM products
WHERE rating_count >= 1000
ORDER BY rating DESC, rating_count DESC
LIMIT 10;


-- 4. Products with the largest discounts
SELECT
    product_name,
    actual_price,
    discounted_price,
    discount_percentage
FROM products
WHERE discount_percentage IS NOT NULL
ORDER BY discount_percentage DESC
LIMIT 10;


-- 5. Average price and rating by category
SELECT
    category,
    COUNT(*) AS product_count,
    ROUND(AVG(discounted_price), 2) AS average_price,
    ROUND(AVG(rating), 2) AS average_rating
FROM products
WHERE category IS NOT NULL
GROUP BY category
ORDER BY product_count DESC
LIMIT 10;