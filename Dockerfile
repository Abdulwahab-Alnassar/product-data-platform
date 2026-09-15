FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home app
COPY src ./src
COPY sql ./sql
COPY data/sample ./data/sample
COPY dashboard.py .
RUN mkdir -p data/processed logs && chown -R app:app /app
USER app
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "dashboard.py", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false"]
