# Playwright + Python (Chromium 내장)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 의존성 설치
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 브라우저 설치 보장
RUN playwright install --with-deps chromium

COPY . /app

EXPOSE 10000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]
