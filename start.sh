#!/bin/sh
exec uvicorn main:app_fastapi --host 0.0.0.0 --port ${PORT:-5000}
