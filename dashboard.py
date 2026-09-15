"""Local, read-only product analytics dashboard."""
import os
import streamlit as st
from src.query_data import load_analytics, filter_products, export_csv

st.set_page_config(page_title='Product Data Platform', page_icon='📊', layout='wide')
st.title('Product Data Platform')
st.caption('Product analytics • Prices in Indian rupees (INR) • Read-only local demo')
backend = os.environ.get('DASHBOARD_BACKEND', 'sqlite')
st.sidebar.caption(f'Database: {backend}')
st.sidebar.button('Refresh data')
try:
    data = load_analytics(backend, os.environ.get('SQLITE_PATH'))
except Exception:
    st.error('Database unavailable. Run the pipeline first and check your database configuration.')
    st.stop()
search = st.sidebar.text_input('Search product name or ID')
categories = st.sidebar.multiselect('Categories', sorted(data.main_category.dropna().unique()))
rating = st.sidebar.slider('Minimum rating', 0.0, 5.0, 0.0, 0.5)
include_unrated = st.sidebar.checkbox('Include unrated products', value=True)
filtered = filter_products(data, search, categories, rating, include_unrated)
a, b, c = st.columns(3)
a.metric('Products', len(filtered))
mean = filtered.rating.mean()
median = filtered.discounted_price.median()
b.metric('Average rating', 'N/A' if filtered.rating.dropna().empty else f'{mean:.2f} / 5')
c.metric('Median price (INR)', 'N/A' if filtered.discounted_price.dropna().empty else f'{median:,.2f}')
if filtered.empty:
    st.info('No products match these filters.')
else:
    st.subheader('Products by category')
    st.bar_chart(filtered.main_category.value_counts())
st.subheader('Product details')
st.dataframe(filtered, hide_index=True)
st.download_button('Download filtered CSV', export_csv(filtered), 'products.csv', 'text/csv')
st.caption('Missing values are not zero. This dataset is a snapshot, not live Amazon prices. No sales/revenue claims are inferred.')
