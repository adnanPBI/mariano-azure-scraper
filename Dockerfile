# Pin Chromium and the Playwright Python client to matching versions.
FROM mcr.microsoft.com/playwright/python:v1.56.0-noble
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SCRAPER_STORAGE=azure
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir .
COPY config ./config
RUN useradd --create-home --uid 10001 worker && chown -R worker:worker /app
USER worker
CMD ["marianos-scrape","run","--settings","blob:config/stores.yaml","--categories","config/Marianos_Category_URLs.csv"]