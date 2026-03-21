# main.py
import os
import time
import asyncio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

app = FastAPI(title="Hippufu Persona AI Server")

system_prompt = """
너의 이름은 '히뿌푸'야. 배에 푹신한 구름 무늬가 있는 귀엽고 다정한 하마지.
말끝마다 '~뿌!' 또는 '~푸!'를 붙이는 귀여운 말투를 사용해.
사용자에게 항상 따뜻하고 긍정적인 에너지를 줘야 해.
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{user_input}")
])

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7,
    streaming=True
)

chain = prompt | llm | StrOutputParser()

# 라우터가 어떤 컨테이너로 트래픽을 보냈는지 확인하기 위한 환경변수
SERVER_ID = os.getenv("SERVER_ID", "Unknown-Server")

class ChatRequest(BaseModel):
    text: str

async def generate_chat_stream(user_input: str):
    async for chunk in chain.astream({"user_input": user_input}):
        yield f"data: {chunk}\n\n"
        await asyncio.sleep(0.01)
    yield "data: [DONE]\n\n"

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    return StreamingResponse(
        generate_chat_stream(request.text),
        media_type="text/event-stream"
    )

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