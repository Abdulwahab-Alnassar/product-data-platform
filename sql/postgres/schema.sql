CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY CHECK (TRIM(product_id) <> ''),
    product_name TEXT NOT NULL,
    category TEXT,

    discounted_price NUMERIC
        CHECK (
            discounted_price IS NULL
            OR discounted_price >= 0
        ),

    actual_price NUMERIC
        CHECK (
            actual_price IS NULL
            OR actual_price >= 0
        ),

    discount_percentage NUMERIC
        CHECK (
            discount_percentage IS NULL
            OR discount_percentage BETWEEN 0 AND 100
        ),

    rating NUMERIC
        CHECK (
            rating IS NULL
            OR rating BETWEEN 0 AND 5
        ),

    rating_count BIGINT
        CHECK (
            rating_count IS NULL
            OR rating_count >= 0
        ),

    about_product TEXT,
    review_id TEXT,
    review_title TEXT,
    review_content TEXT,
    img_link TEXT,
    product_link TEXT
);

CREATE INDEX IF NOT EXISTS idx_products_category
ON products(category);

CREATE INDEX IF NOT EXISTS idx_products_rating
ON products(rating);

CREATE INDEX IF NOT EXISTS idx_products_rating_count
ON products(rating_count);
