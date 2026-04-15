import networkx as nx
import matplotlib.pyplot as plt
from pydantic import BaseModel, Field
from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# ==========================================
# 1. 추출할 데이터 구조 정의 (Pydantic)
# ==========================================
class Edge(BaseModel):
    source: str = Field(description="첫 번째 엔티티 (예: 히뿌푸)")
    target: str = Field(description="두 번째 엔티티 (예: 크로키드)")
    relation: str = Field(description="두 엔티티 간의 관계 (예: 가장 친한 친구)")

class GraphKnowledge(BaseModel):
    edges: List[Edge] = Field(description="텍스트에서 추출된 모든 엔티티 관계 목록")

# ==========================================
# 2. LLM 및 프롬프트 세팅
# ==========================================
# OpenAI 모델에 구조화된 출력(JSON)을 강제합니다.
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(GraphKnowledge)

prompt = ChatPromptTemplate.from_messages([
    ("system", """
    너는 최고 수준의 데이터 분석가야. 주어진 텍스트를 읽고 핵심 엔티티(인물, 장소, 사물 등)와 
    그들 간의 관계를 추출하여 지식 그래프 데이터를 만들어야 해.
    최대한 구체적이고 간결한 단어로 엔티티를 추출해줘.
    """),
    ("human", "{text}")
])

extractor_chain = prompt | llm

# ==========================================
# 3. 테스트용 데이터 (히뿌푸 유니버스)
# ==========================================
sample_text = """
히뿌푸는 무지개 언덕에 사는 하마 정령이다. 히뿌푸의 가장 친한 친구는 뾰족구두를 신은 악어 '크로키드'이다. 
크로키드는 '시간의 시계'를 관리하며, 이 시계는 무지개 언덕의 낮과 밤을 바꾼다. 
한편, 그림자 숲에 사는 '어둠벌레'는 시간의 시계를 훔치려 호시탐탐 기회를 노리고 있어 히뿌푸와 대립하고 있다.
"""

def build_and_save_graph(text: str, output_file: str = "hippufu_graph.gml"):
    print("🧠 [1/3] LLM을 통해 텍스트에서 지식 그래프(엔티티/관계) 추출 중...")
    extracted_data: GraphKnowledge = extractor_chain.invoke({"text": text})

    print("\n✨ [추출된 관계 목록]")
    for edge in extracted_data.edges:
        print(f" - ({edge.source}) --[{edge.relation}]--> ({edge.target})")

    print("\n🕸️ [2/3] NetworkX 그래프 생성 중...")
    g = nx.DiGraph() # 방향성이 있는 그래프 생성

    for edge in extracted_data.edges:
        g.add_edge(edge.source, edge.target, relation=edge.relation)

    print(f"💾 [3/3] 그래프 데이터를 '{output_file}' 파일로 저장합니다.")
    nx.write_gml(g, output_file)

    # (보너스) 추출된 그래프 시각화
    plt.figure(figsize=(10, 6))
    pos = nx.spring_layout(g, seed=42)

    # 노드 그리기
    nx.draw(g, pos, with_labels=True, node_color='lightblue',
            node_size=3000, font_size=12, font_weight='bold', font_family='AppleGothic')

    # 엣지 라벨(관계) 그리기
    edge_labels = nx.get_edge_attributes(g, 'relation')
    nx.draw_networkx_edge_labels(g, pos, edge_labels=edge_labels, font_family='AppleGothic')

    plt.title("Hippufu Universe Knowledge Graph")
    plt.savefig("graph_visualization.png")
    print("📸 그래프 시각화 이미지가 'graph_visualization.png'로 저장되었습니다.")

if __name__ == "__main__":
    build_and_save_graph(sample_text)