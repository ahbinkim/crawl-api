# ✅ Playwright + Chromium 내장 베이스
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# API 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --root-user-action=ignore

# ✅ 혹시 모를 상황 대비: playwright를 다시 설치 + chromium 준비
RUN pip install --no-cache-dir playwright==1.45.0 --root-user-action=ignore \
 && playwright install --with-deps chromium

# 앱 소스
COPY . .

ENV PYTHONUNBUFFERED=1

# 서버 실행
CMD ["bash", "-lc", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
