FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 QUANTCORE_DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY quantcore ./quantcore
COPY configs ./configs
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
RUN pip install --no-cache-dir '.[realdata]' -c requirements.lock && useradd -u 10001 -m quantcore && mkdir /data && chown quantcore /data
USER quantcore
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
