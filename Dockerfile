# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 캐시 레이어 최적화를 위해 requirements 먼저 복사
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000

# uvicorn 워커 수를 1개로 제한하여 병목을 극대화 (선택 사항)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]