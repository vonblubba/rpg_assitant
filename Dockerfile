FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# Pre-warm the unstructured hi-res layout model at build time so ingestion
# never needs network access at runtime.
RUN python -c "from unstructured_inference.models.base import get_model; get_model('yolox')"

COPY . .

RUN chmod +x entrypoint.sh

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
