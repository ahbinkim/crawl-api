# Playwright + Chromium 내장 이미지 (권장)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스
COPY . .

ENV PYTHONUNBUFFERED=1

# Render의 $PORT 사용
CMD ["bash", "-lc", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
