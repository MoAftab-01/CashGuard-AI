# Shared analytics dependencies justify one image for dashboard/API commands.
FROM python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HOME=/home/cashguard MLFLOW_DISABLE_TELEMETRY=true
WORKDIR /app
COPY requirements-runtime.lock.txt ./
RUN python -m pip install --no-cache-dir -r requirements-runtime.lock.txt \
    && groupadd --gid 10001 cashguard \
    && useradd --uid 10001 --gid 10001 --create-home cashguard
RUN mkdir -p /app/var && chown cashguard:cashguard /app/var

FROM dependencies AS runtime
COPY --chown=cashguard:cashguard app.py config.py pyproject.toml ./
COPY --chown=cashguard:cashguard src ./src
COPY --chown=cashguard:cashguard api ./api
COPY --chown=cashguard:cashguard .streamlit/config.toml ./.streamlit/config.toml
COPY --chown=cashguard:cashguard data/synthetic_transactions.csv ./data/synthetic_transactions.csv
USER cashguard
EXPOSE 8501 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=3)"
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]

FROM dependencies AS tracking
COPY requirements-mlops.lock.txt ./
RUN python -m pip install --no-cache-dir -r requirements-mlops.lock.txt
USER cashguard
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health',timeout=3)"
CMD ["python", "-m", "mlflow", "server", "--host", "0.0.0.0", "--port", "5000", "--workers", "1", "--backend-store-uri", "sqlite:////app/var/mlflow.db", "--artifacts-destination", "/app/var/artifacts", "--allowed-hosts", "localhost:*,127.0.0.1:*,mlflow:5000"]
