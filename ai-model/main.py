import os
import time
import asyncio
import logging
import operator
import networkx as nx

from typing import TypedDict, Annotated, Sequence

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field # Field 임포트 추가

# OpenTelemetry 패키지
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

from langchain_openai import ChatOpenAI, OpenAIEmbeddings # Embeddings 임포트 추가
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_community.vectorstores import FAISS # FAISS 임포트 추가

# LangGraph 패키지
from langgraph.graph import StateGraph, END

import model_service_pb2 as pb

# ==========================================
# 1. 로깅 및 서버 ID 초기화
# ==========================================
LoggingInstrumentor().instrument(set_logging_format=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVER_ID = os.getenv("SERVER_ID", "Unknown-Server")

# ==========================================
# 2. [GraphDB 및 VectorDB 메모리 로드]
# ==========================================
try:
    hippufu_graph = nx.read_gml("hippufu_graph.gml")
    logger.info(f"[{SERVER_ID}] 🕸️ 지식 그래프 로드 완료! (노드: {hippufu_graph.number_of_nodes()}개)")
except Exception as e:
    logger.warning(f"[{SERVER_ID}] ⚠️ 그래프 파일을 찾을 수 없습니다: {e}")
    hippufu_graph = nx.DiGraph()

try:
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    hippufu_faiss = FAISS.load_local("hippufu_faiss_index", embeddings, allow_dangerous_deserialization=True)
    logger.info(f"[{SERVER_ID}] 🗂️ FAISS Vector DB 로드 완료!")
except Exception as e:
    logger.warning(f"[{SERVER_ID}] ⚠️ FAISS 인덱스를 찾을 수 없습니다: {e}")
    hippufu_faiss = None

# ==========================================
# 3. FastAPI 앱 생성 및 OTel 부착
# ==========================================
app = FastAPI(title="Hippufu Persona AI Server with GraphRAG")

# FastAPI 앱에 OTel 미들웨어 부착 (traceparent 헤더 자동 파싱)
FastAPIInstrumentor.instrument_app(app)

# ==========================================
# 4. [LangChain LLM & 프롬프트 세팅]
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

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, streaming=True)
chain = prompt | llm | StrOutputParser()

# ==========================================
# 5. [GraphRAG: LangGraph 상태 및 라우팅 로직]
# ==========================================
class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    intent: str      # 'local', 'global', 'hybrid'
    context: str

# 의도 분류를 위한 Pydantic 스키마
class IntentClassification(BaseModel):
    intent: str = Field(description="질문의 의도. 특정 인물/사물의 사실과 관계면 'local', 전체 스토리나 요약/맥락이면 'global', 둘 다 섞여 있거나 애매하면 'hybrid'로 분류.")

async def analyze_intent_node(state: GraphState):
    """LLM을 이용한 지능형 의도 분석 라우터"""
    user_message = state["messages"][-1].content
    logger.info(f"[{SERVER_ID}] 🧠 의도 분석 LLM 가동 중...")

    classifier_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(IntentClassification)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "너는 질문의 의도를 분석하는 최고 수준의 검색 라우터야."),
        ("human", "{question}")
    ])

    result = await classifier_llm.ainvoke(prompt.format_messages(question=user_message))
    intent = result.intent

    logger.info(f"[{SERVER_ID}] 🎯 판별된 의도: {intent.upper()} Search")
    return {"intent": intent}

async def local_search_node(state: GraphState):
    """GraphDB 탐색"""
    user_message = state["messages"][-1].content
    found_context = []

    # PoC용 초간단 룰베이스 엔티티 매칭
    # (실무에서는 이 부분도 LLM/NER 모델로 엔티티를 뽑아내서 검색합니다)
    for node in hippufu_graph.nodes:
        if node in user_message:
            # 질문에 포함된 엔티티가 그래프에 있다면, 해당 엔티티와 연결된(1-depth) 모든 관계를 싹 긁어옵니다.
            # 1. 정방향 엣지 (내가 향하는 관계)
            for source, target, data in hippufu_graph.edges(node, data=True):
                found_context.append(f"{source}는(은) {target}에 대해 '{data['relation']}' 관계입니다.")

            # 2. 역방향 엣지 (나를 향하는 관계)
            for source, target, data in hippufu_graph.in_edges(node, data=True):
                found_context.append(f"{source}는(은) {target}에 대해 '{data['relation']}' 관계입니다.")

    context_str = "\n".join(list(set(found_context))) if found_context else "관련된 그래프 지식이 없습니다."
    return {"context": f"[GraphDB 검색 결과]\n{context_str}"}

async def global_search_node(state: GraphState):
    """VectorDB 탐색"""
    user_message = state["messages"][-1].content
    if hippufu_faiss is None:
        return {"context": "[VectorDB 검색 실패] 인덱스가 없습니다."}

    # 유저의 질문과 가장 유사한 커뮤니티 요약본 2개를 가져옵니다.
    docs = hippufu_faiss.similarity_search(user_message, k=2)

    context_str = "\n\n".join([f"[커뮤니티 {doc.metadata.get('community_id')} 요약]\n{doc.page_content}" for doc in docs])

    logger.info(f"[{SERVER_ID}] 🌐 추출된 Vector 문맥: {context_str}")
    return {"context": f"[VectorDB 전체 요약 검색 결과]\n{context_str}"}

async def hybrid_search_node(state: GraphState):
    """GraphDB와 VectorDB를 동시에 찌르는 하이브리드 탐색"""
    logger.info(f"[{SERVER_ID}] 🧬 Hybrid Search (Graph + Vector 동시 탐색) 시작")
    local_result, global_result = await asyncio.gather(
        local_search_node(state),
        global_search_node(state)
    )
    combined_context = f"{local_result['context']}\n\n{global_result['context']}"
    logger.info(f"[{SERVER_ID}] 🧬 Hybrid Search 완료!")
    return {"context": combined_context}

def route_by_intent(state: GraphState):
    intent = state["intent"]
    if intent == "local": return "local_search"
    elif intent == "global": return "global_search"
    else: return "hybrid_search"

# ==========================================
# 6. [LangGraph 조립]
# ==========================================
workflow = StateGraph(GraphState)
workflow.add_node("intent_analyzer", analyze_intent_node)
workflow.add_node("local_search", local_search_node)
workflow.add_node("global_search", global_search_node)
workflow.add_node("hybrid_search", hybrid_search_node)

workflow.set_entry_point("intent_analyzer")
workflow.add_conditional_edges("intent_analyzer", route_by_intent)
workflow.add_edge("local_search", END)
workflow.add_edge("global_search", END)
workflow.add_edge("hybrid_search", END)

graph_app = workflow.compile()

# ==========================================
# 7. [FastAPI 엔드포인트]
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
async def chat_endpoint(request: Request):
    current_span = trace.get_current_span()
    trace_id = current_span.get_span_context().trace_id
    trace_id_hex = f"{trace_id:032x}" if trace_id else "No-Trace-ID"

    logger.info(f"[{SERVER_ID}] 히뿌푸 채팅 요청 수신! TraceID: {trace_id_hex}")

    # [KYL-107] JSON 대신 Raw Body(Protobuf 바이너리)를 직접 읽음
    body_bytes = await request.body() # type: ignore

    # Protobuf 객체로 역직렬화
    chat_request = pb.ChatRequest() # type: ignore
    try:
        chat_request.ParseFromString(body_bytes)
        logger.info(f"[{SERVER_ID}] Protobuf 메시지 파싱 성공! ModelID: {chat_request.model_id}, Prompt: {chat_request.prompt[:30]}... TraceID: {trace_id_hex}")
    except Exception as e:
        logger.error(f"[{SERVER_ID}] Protobuf 메시지 파싱 실패: {e} TraceID: {trace_id_hex}")
        return {"error": "Invalid Protobuf format"}
    
    # 추철된 prompt 사용
    user_input = chat_request.prompt
    logger.info(f"[{SERVER_ID}] 히뿌푸 바이너리 요청 수신! Prompt: {user_input} | TraceID: {trace_id_hex}")

    # 스트리밍 응답 (SSE는 텍스트 기반이므로 기존 로직 유지)
    return StreamingResponse(
        generate_chat_stream(user_input),
        media_type="text/event-stream"
    )

@app.get("/health")
def health_check():
    """Go 라우터가 컨테이너의 상태를 체크할 헬스체크 엔드포인트"""
    return {"status": "ok", "server_id": SERVER_ID}

@app.post("/api/summarize")
async def summarize(request: Request):
    """
    GPU 연산을 흉내 내는 병목 엔드포인트.
    의도적으로 동기(Sync) 함수로 작성하여 워커 스레드를 3초간 블로킹합니다.
    """
    current_span = trace.get_current_span()
    trace_id = current_span.get_span_context().trace_id
    trace_id_hex = f"{trace_id:032x}" if trace_id else "No-Trace-ID"

    body_bytes = await request.body()
    req = pb.ChatRequest() # type: ignore
    req.ParseFromString(body_bytes)
    
    logger.info(f"[{SERVER_ID}] 요약 요청 수신. 3초간 처리 중... TraceID: {trace_id_hex}")
    time.sleep(3) # Heavy AI Model Simulation
    
    text = req.prompt
    logger.info(f"[{SERVER_ID}] 요약 처리 완료. TraceID: {trace_id_hex}")

    res = pb.ChatResponse() # type: ignore
    res.server_id = SERVER_ID
    res.summary = f"[요약 완료] {text[:10]}..."
    res.processing_time = "3s"
    res.trace_id = trace_id_hex
    
    return Response(
        content=res.SerializeToString(),
        media_type="application/x-protobuf"
    )
