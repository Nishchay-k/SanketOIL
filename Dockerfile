FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./frontend
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    APP_ENV=production
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system sanket \
    && useradd --system --gid sanket --home-dir /app sanket
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY alembic.ini /app/alembic.ini
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
COPY data/sample /app/data/sample
RUN mkdir -p /app/data/documents \
    && chown -R sanket:sanket /app
USER sanket
EXPOSE 8000
CMD ["python", "-m", "backend.app.main"]
