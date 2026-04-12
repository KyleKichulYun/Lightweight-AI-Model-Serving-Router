# ==========================================
# 파이썬 AI 모델 서빙용 Dockerfile
# ==========================================
# 데비안 기반의 가벼운 slim 이미지 사용
FROM python:3.11-slim

# 타임존 설정 및 필수 OS 패키지 설치
ENV TZ=Asia/Seoul \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 불필요한 캐시를 지워 이미지 용량을 줄이는 최적화 패턴
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. 종속성 패키지 먼저 복사 및 설치 (도커 레이어 캐싱 극대화)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 2. 소스코드 및 필수 데이터(GraphDB, FAISS) 복사
COPY . .

EXPOSE 8000

# uvicorn 워커 수를 1개로 제한하여 병목을 극대화 (스케일아웃 테스트용)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]