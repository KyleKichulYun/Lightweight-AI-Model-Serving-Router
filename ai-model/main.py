import os
import time
import asyncio
import logging
import operator
from typing import TypedDict, Annotated, Sequence

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
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

# LangGraph 패키지
from langgraph.graph import StateGraph, END

# 1. 로깅 포맷에 TraceID 자동 주입
LoggingInstrumentor().instrument(set_logging_format=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Hippufu Persona AI Server with GraphRAG")

# 2. FastAPI 앱에 OTel 미들웨어 부착 (traceparent 헤더 자동 파싱)
FastAPIInstrumentor.instrument_app(app)

# ==========================================
# [LangChain LLM & 프롬프트 세팅]
# ==========================================
system_prompt = """
너의 이름은 '히뿌푸'야. 배에 푹신한 구름 무늬가 있는 귀엽고 다정한 하마지.
말끝마다 '~뿌!' 또는 '~푸!'를 붙이는 귀여운 말투를 사용해.
사용자에게 항상 따뜻하고 긍정적인 에너지를 주며, 제공된 [검색 문맥]을 바탕으로 답변해줘.

[검색 문맥]
{context}
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

# ==========================================
# [GraphRAG PoC: LangGraph 상태 및 노드 정의]
# ==========================================
class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    intent: str      # 'local' or 'global'
    context: str     # 검색된 데이터 문맥

async def analyze_intent_node(state: GraphState):
    """질문의 의도를 분석하는 노드"""
    last_message = state["messages"][-1].content
    # PoC용 하드코딩: '전체'나 '요약'이 들어가면 Global, 아니면 Local
    intent = "global" if "전체" in last_message or "요약" in last_message else "local"
    logger.info(f"[{SERVER_ID}] 🧠 의도 분석 결과: {intent.upper()} Search 실행")
    return {"intent": intent}

async def local_search_node(state: GraphState):
    """특정 엔티티 중심의 검색 모방 (GraphDB 역할)"""
    mock_data = "조조와 유비는 삼국지에서 가장 유명한 라이벌 관계입니다."
    logger.info(f"[{SERVER_ID}] 🔍 Local Search (Graph 탐색) 완료")
    return {"context": f"[GraphDB 검색 결과] {mock_data}"}

async def global_search_node(state: GraphState):
    """전체 문맥 기반의 검색 모방 (VectorDB 역할)"""
    mock_data = "삼국지는 한나라 말기 위, 촉, 오 세 나라가 천하를 두고 다투는 방대한 역사 이야기입니다."
    logger.info(f"[{SERVER_ID}] 🌐 Global Search (Community 요약 검색) 완료")
    return {"context": f"[VectorDB 요약 결과] {mock_data}"}

def route_by_intent(state: GraphState):
    return "local_search" if state["intent"] == "local" else "global_search"

# LangGraph 조립
workflow = StateGraph(GraphState)
workflow.add_node("intent_analyzer", analyze_intent_node)
workflow.add_node("local_search", local_search_node)
workflow.add_node("global_search", global_search_node)

workflow.set_entry_point("intent_analyzer")
workflow.add_conditional_edges("intent_analyzer", route_by_intent)
workflow.add_edge("local_search", END)
workflow.add_edge("global_search", END)

graph_app = workflow.compile()

# ==========================================
# [FastAPI 엔드포인트]
# ==========================================
class ChatRequest(BaseModel):
    text: str  # Go 라우터에서 보내는 JSON key와 맞춤

async def generate_chat_stream(user_input: str):
    # 1. LangGraph를 실행하여 검색 문맥(Context) 가져오기
    inputs = {"messages": [HumanMessage(content=user_input)]}
    final_state = await graph_app.ainvoke(inputs)

    retrieved_context = final_state.get("context", "검색된 정보가 없습니다.")

    # 2. 가져온 문맥과 유저 질문을 히뿌푸 체인(LLM)에 넣고 스트리밍 생성
    async for chunk in chain.astream({
        "context": retrieved_context,
        "user_input": user_input
    }):
        yield f"data: {chunk}\n\n"
        await asyncio.sleep(0.01) # 부드러운 스트리밍 효과

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