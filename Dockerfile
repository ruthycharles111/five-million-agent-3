FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install wkhtmltopdf and its dependencies, plus Chromium dependencies for wkhtmltoimage
RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libatspi2.0-0 libx11-6 libxext6 \
    libxcb1 libexpat1 fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY . .

CMD uvicorn main:app_fastapi --host 0.0.0.0 --port $PORT
