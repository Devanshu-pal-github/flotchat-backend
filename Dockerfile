# FloatChat backend - FastAPI + Uvicorn
# Multi-stage: build (deps) -> runtime

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for netCDF4
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libnetcdf-dev \
    libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

COPY flotchat-backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY flotchat-backend/app /app/app
COPY flotchat-backend/floatchat.db /app/floatchat.db

EXPOSE 8000

# Start Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
