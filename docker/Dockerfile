FROM python:3.12-slim
WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user (BUG-034)
RUN groupadd -r trader && useradd -r -g trader -d /app -s /bin/false trader

COPY . .

# Ensure data directory exists and is writable
RUN mkdir -p /app/data /app/logs && chown -R trader:trader /app

USER trader

ENV APP_HOST=0.0.0.0 APP_PORT=5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health')" || exit 1

CMD ["python", "-m", "app", "--live"]
