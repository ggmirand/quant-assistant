FROM python:3.11-slim

# Lightweight system deps (avoid heavy compilers on WSL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements from THIS context (./backend)
COPY requirements.txt /app/requirements.txt

# Use prebuilt wheels to avoid compiling numpy/pandas
ENV PIP_NO_CACHE_DIR=1
RUN pip install --upgrade pip && \
    pip install --only-binary=:all: -r /app/requirements.txt

# Copy the backend app source from THIS context (./backend)
COPY . /app

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

