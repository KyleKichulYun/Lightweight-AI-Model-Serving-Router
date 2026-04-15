import os
import json
import networkx as nx

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# ==========================================
# 1. 그래프 로드 및 커뮤니티 탐지 (Louvain 알고리즘)
# ==========================================
def detect_communities(gml_path: str = "hippufu_graph.gml"):
    print("🕸️ [1/4] 지식 그래프 로드 및 커뮤니티 탐지 중...")
    G = nx.read_gml(gml_path)

    # 방향성 그래프(DiGraph)를 무방향성(Graph)으로 변환해야 커뮤니티 탐지가 더 잘 됩니다.
    undirected_G = G.to_undirected()

    # NetworkX 내장 Louvain 알고리즘 사용 (Leiden의 경량화 대안)
    communities = nx.community.louvain_communities(undirected_G)
    print(f"✅ 총 {len(communities)}개의 커뮤니티(클러스터)가 발견되었습니다.")
    return G, communities

# ==========================================
# 2. 커뮤니티별 요약 (LLM Map-Reduce 모방)
# ==========================================
def summarize_communities(G, communities):
    print("🧠 [2/4] LLM을 이용한 커뮤니티별 계층적 요약 생성 중...")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """
        너는 데이터 요약 전문가야. 아래 제공된 지식 그래프의 일부(특정 커뮤니티) 데이터를 읽고, 
        이 그룹의 핵심 주제와 주요 관계를 3~4문장으로 명확하게 요약해줘.
        """),
        ("human", "{community_data}")
    ])

    chain = prompt | llm
    documents = []

    for idx, comm_nodes in enumerate(communities):
        # 1. 해당 커뮤니티에 속한 노드들 간의 엣지(관계)만 추출
        subgraph = G.subgraph(comm_nodes)
        edge_descriptions = []
        for u, v, data in subgraph.edges(data=True):
            edge_descriptions.append(f"- {u}는(은) {v}에 대해 '{data['relation']}' 관계입니다.")

        community_text = "\n".join(edge_descriptions)

        # 엣지가 없는 고립된 노드 커뮤니티 처리
        if not community_text:
            community_text = f"- 포함된 엔티티: {', '.join(comm_nodes)} (명확한 내부 관계 없음)"

        print(f"\n[커뮤니티 {idx+1} 원본 데이터]\n{community_text}")

        # 2. LLM 요약 요청
        summary_response = chain.invoke({"community_data": community_text})
        summary_text = summary_response.content
        print(f"👉 [커뮤니티 {idx+1} 요약 결과]\n{summary_text}")

        # 3. Vector DB에 넣을 Document 객체 생성 (메타데이터 포함)
        doc = Document(
            page_content=summary_text,
            metadata={
                "community_id": idx + 1,
                "nodes": list(comm_nodes)
            }
        )
        documents.append(doc)

    return documents

# ==========================================
# 3. Vector Embedding 및 인덱싱 (FAISS)
# ==========================================
def build_vector_index(documents, index_path="hippufu_faiss_index"):
    print("\n🗂️ [3/4] 요약본 임베딩(Vectorization) 중...")
    # OpenAI의 최신 경량/고성능 임베딩 모델 사용
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    # FAISS 인메모리 벡터 저장소 생성
    vectorstore = FAISS.from_documents(documents, embeddings)

    print(f"💾 [4/4] 벡터 인덱스를 로컬('{index_path}')에 저장합니다.")
    vectorstore.save_local(index_path)
    print("🎉 Global Search 데이터 파이프라인 구축 완료!")

if __name__ == "__main__":
    try:
        graph, comms = detect_communities("hippufu_graph.gml")
        docs = summarize_communities(graph, comms)
        build_vector_index(docs)
    except Exception as e:
        print(f"❌ 에러 발생: {e}")