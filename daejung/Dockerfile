FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Install only API dependencies (playwright & chromium come from the base image)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --root-user-action=ignore

COPY . .

ENV PYTHONUNBUFFERED=1

# Run FastAPI with uvicorn, using Render's PORT
CMD ["bash", "-lc", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
