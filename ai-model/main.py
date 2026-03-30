import os
import time
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# OpenTelemetry 패키지
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 1. 로깅 포맷에 TraceID 자동 주입
LoggingInstrumentor().instrument(set_logging_format=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Hippufu Persona AI Server")

# 2. FastAPI 앱에 OTel 미들웨어 부착 (traceparent 헤더 자동 파싱)
FastAPIInstrumentor.instrument_app(app)

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
    current_span = trace.get_current_span()
    trace_id = current_span.get_span_context().trace_id
    trace_id_hex = f"{trace_id:032x}" if trace_id else "No-Trace-ID"
    
    logger.info(f"[{SERVER_ID}] 히뿌푸 채팅 요청 수신! TraceID: {trace_id_hex}")
    
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
    current_span = trace.get_current_span()
    trace_id = current_span.get_span_context().trace_id
    trace_id_hex = f"{trace_id:032x}" if trace_id else "No-Trace-ID"
    
    logger.info(f"[{SERVER_ID}] 요약 요청 수신. 3초간 처리 중... TraceID: {trace_id_hex}")
    time.sleep(3) # Heavy AI Model Simulation
    
    text = payload.get("text", "No text provided")
    
    logger.info(f"[{SERVER_ID}] 요약 처리 완료. TraceID: {trace_id_hex}")
    return {
        "server_id": SERVER_ID,
        "summary": f"[요약 완료] {text[:10]}...",
        "processing_time": "3s",
        "trace_id": trace_id_hex
    }