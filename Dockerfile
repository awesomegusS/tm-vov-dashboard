FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=100

COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel && \
    pip install --timeout 100 --no-cache-dir -r requirements.txt

COPY . .

# This image is intended for Prefect deployments/agents. The default command
# simply prints help so you can override it when starting a container or using
# the image in Prefect Cloud.
CMD ["python", "deployments.py", "--help"]
