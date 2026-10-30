# Mock of a WordPress site running Polylang Pro (REST API) for FOX MLO development.
FROM python:3.12-slim-bookworm

WORKDIR /srv
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data

EXPOSE 8090
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
