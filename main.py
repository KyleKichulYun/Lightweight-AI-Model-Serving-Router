# main.py
from fastapi import FastAPI
import time
import os

app = FastAPI()

# 라우터가 어떤 컨테이너로 트래픽을 보냈는지 확인하기 위한 환경변수
SERVER_ID = os.getenv("SERVER_ID", "Unknown-Server")

@app.get("/health")
def health_check():
    """Go 라우터가 컨테이너의 상태를 체크할 헬스체크 엔드포인트"""
    return {"status": "ok", "server_id": SERVER_ID}

@app.post("/api/summarize")
def summarize(payload: dict):
    """
    GPU 연산을 흉내 내는 병목 엔드포인트.
    의도적으로 동기(Sync) 함수로 작성하여 워커 스레드를 3초간 블로킹합니다.
    """
    print(f"[{SERVER_ID}] 요청 수신. 3초간 처리 중...")
    time.sleep(3) # Heavy AI Model Simulation
    
    text = payload.get("text", "No text provided")
    
    return {
        "server_id": SERVER_ID,
        "summary": f"[요약 완료] {text[:10]}...",
        "processing_time": "3s"
    }