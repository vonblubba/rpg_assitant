#!/bin/sh
set -e
python -c "from app import models; from app.db import init_db; init_db()"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
