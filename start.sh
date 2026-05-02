#!/bin/sh
apk add --no-cache wkhtmltopdf
exec uvicorn main:app_fastapi --host 0.0.0.0 --port $PORT
