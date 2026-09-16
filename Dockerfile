FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home app
COPY src ./src
COPY sql ./sql
COPY data/sample ./data/sample
COPY dashboard.py .
COPY examples ./examples
COPY evaluation ./evaluation
RUN mkdir -p data/processed logs artifacts/category && chown -R app:app /app
USER app
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "dashboard.py", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false"]
