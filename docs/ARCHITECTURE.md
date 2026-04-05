# 🏛️ System Architecture: Lightweight AI Serving & GraphRAG

본 문서는 트래픽을 제어하는 고성능 **L7 라우터(Go)**와 복잡한 문맥 추론을 담당하는 **GraphRAG 오케스트레이션(Python)**으로 구성된 AI 서빙 시스템의 전체 아키텍처 및 주요 설계 결정을 설명합니다.

## 1. 아키텍처 다이어그램 (Architecture Diagram)

```mermaid
graph TD
    %% 사용자 및 진입점
    Client([👤 Client / User])
    
    %% Go Router Layer
    subgraph GoRouter ["API Gateway & L7 Router (Go)"]
        direction TB
        TTFT[⏱️ TTFT Metrics Interceptor]
        Guard[🛡️ Guardrail Middleware]
        LB[⚖️ Load Balancer]
        
        TTFT --> Guard
        Guard --> LB
    end

    %% Python AI Layer
    subgraph PythonAI ["AI Orchestration Layer (Python + LangGraph)"]
        direction TB
        RouterNode{LangGraph Router}
        
        subgraph Indexing ["데이터 색인 (Indexing)"]
            Chunk[1. Chunking & Entity Extraction]
            Comm[2. Community Detection]
            Chunk --> Comm
        end
        
        subgraph Querying ["데이터 추론 (Query)"]
            Local[🔍 Local Search <br>특정 엔티티 중심]
            Global[🌐 Global Search <br>전체 문맥 요약]
        end
        
        RouterNode -->|구체적 질문| Local
        RouterNode -->|광범위한 질문| Global
    end

    %% Storage Layer
    subgraph Storage ["Databases"]
        direction LR
        GraphDB[(🕸️ Graph DB <br>Neo4j / NetworkX)]
        VectorDB[(📊 Vector DB <br>Qdrant / FAISS)]
    end

    %% 연결 (Edges)
    Client -->|HTTP/SSE POST| TTFT
    LB -->|Safe Traffic Only| RouterNode
    
    %% 색인 및 쿼리 파이프라인 연결
    Indexing --> GraphDB
    Indexing --> VectorDB
    Local <--> GraphDB
    Global <--> VectorDB