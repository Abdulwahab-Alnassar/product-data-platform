"""Local, read-only product analytics dashboard."""

import streamlit as st
from src.query_data import load_analytics, filter_products, export_csv
from src.config import Settings
from src.catalog import Catalog
from src.predict import CategoryModel
from src.search import SearchService
from src.qa import answer
from src.monitor import monitor
from src.privacy import redact

st.set_page_config(page_title="Product Data Platform", page_icon="📊", layout="wide")
st.title("Product Data Platform")
st.caption("Product analytics • Prices in Indian rupees (INR) • Read-only local demo")
settings = Settings.from_env()
backend = settings.backend
st.sidebar.caption(f"Database: {backend}")
st.sidebar.button("Refresh data")
try:
    data = load_analytics(backend, settings.database_path)
    data["product_name"] = data["product_name"].map(redact)
except Exception:
    st.error(
        "Database unavailable. Run the pipeline first and check your database configuration."
    )
    st.stop()
search = st.sidebar.text_input("Search product name or ID")
categories = st.sidebar.multiselect(
    "Categories", sorted(data.main_category.dropna().unique())
)
rating = st.sidebar.slider("Minimum rating", 0.0, 5.0, 0.0, 0.5)
include_unrated = st.sidebar.checkbox("Include unrated products", value=True)
filtered = filter_products(data, search, categories, rating, include_unrated)
a, b, c = st.columns(3)
a.metric("Products", len(filtered))
mean = filtered.rating.mean()
median = filtered.discounted_price.median()
b.metric(
    "Average rating", "N/A" if filtered.rating.dropna().empty else f"{mean:.2f} / 5"
)
c.metric(
    "Median price (INR)",
    "N/A" if filtered.discounted_price.dropna().empty else f"{median:,.2f}",
)
if filtered.empty:
    st.info("No products match these filters.")
else:
    st.subheader("Products by category")
    st.bar_chart(filtered.main_category.value_counts())
st.subheader("Product details")
st.dataframe(filtered, hide_index=True)
st.download_button(
    "Download filtered CSV", export_csv(filtered), "products.csv", "text/csv"
)
st.caption(
    "Missing values are not zero. This dataset is a snapshot, not live Amazon prices. No sales/revenue claims are inferred."
)

st.divider()
prediction_tab, search_tab, question_tab, health_tab = st.tabs(
    ["Category prediction", "Hybrid search", "Product Q&A", "Data health"]
)

with prediction_tab:
    st.caption(
        "Predict the main category from a product name. The demo model only knows its training categories."
    )
    name = st.text_input("Product name to classify")
    if st.button("Predict category"):
        try:
            prediction = CategoryModel(settings.model_path).predict(name)
            if prediction["abstained"]:
                st.info(prediction["reason"])
            else:
                st.success(prediction["category"])
                st.caption(
                    f"Model probability: {prediction['probability']:.1%}; this is not calibrated confidence."
                )
        except (OSError, ValueError, KeyError):
            st.info("Train the model first, then enter a nonempty product name.")

with search_tab:
    query = st.text_input("Search catalog by meaning, words, or product ID")
    in_stock = st.checkbox("Only products with known stock")
    if st.button("Find products"):
        try:
            matches = SearchService(Catalog(settings)).search(query, in_stock=in_stock)
            if matches:
                st.dataframe(matches, hide_index=True)
            else:
                st.info(
                    "No matching products. Unknown stock is excluded when the stock filter is on."
                )
        except Exception:
            st.error(
                "Search unavailable. Enter a query and run the updated pipeline to initialize change tracking."
            )

with question_tab:
    question = st.text_input("Ask about a product; include its name or ID")
    use_local_model = st.checkbox("Use a configured local language model", value=False)
    if st.button("Answer from catalog"):
        try:
            result = answer(
                question,
                SearchService(Catalog(settings)),
                "ollama" if use_local_model else "facts",
                settings,
            )
            st.text(result["answer"])
            if result.get("notice"):
                st.caption(result["notice"])
            with st.expander("Supporting catalog records"):
                st.json(result["sources"])
        except Exception:
            st.error(
                "Could not read catalog evidence. Check the input and database setup."
            )

with health_tab:
    st.caption("Distribution changes are a review signal, not proof of model failure.")
    if st.button("Check data health"):
        try:
            model = (
                CategoryModel(settings.model_path)
                if settings.model_path.is_file()
                else None
            )
            report = monitor(Catalog(settings), model)
            for message in report["alerts"]:
                st.warning(message)
            st.json(report)
        except Exception:
            st.error(
                "Health report unavailable. Run the updated pipeline and check the model artifact."
            )
