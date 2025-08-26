# Use official Playwright Python image (includes browsers & deps)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

WORKDIR /app

# System locales (optional but nice for ko-KR)
RUN apt-get update -y && apt-get install -y --no-install-recommends locales &&     sed -i '/ko_KR.UTF-8/s/^# //g' /etc/locale.gen &&     locale-gen &&     rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Ensure Chromium is installed (redundant for this base, but safe)
RUN playwright install --with-deps chromium

COPY . /app

EXPOSE 10000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]
