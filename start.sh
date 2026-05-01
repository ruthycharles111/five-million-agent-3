#!/bin/sh
echo "Installing wkhtmltopdf..."
apk add --no-cache wkhtmltopdf
echo "Starting uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-5000}
