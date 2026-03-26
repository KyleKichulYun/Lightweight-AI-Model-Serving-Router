``markdown
# 🚀 Lightweight AI Model Serving Router & Autoscaler

A custom Kubernetes-native MLOps infrastructure project. This project demonstrates a lightweight, high-performance API Gateway (Router) built in **Go**, combined with a **Custom Kubernetes Operator** that autoscales Python-based AI model containers. It features production-grade routing via **NGINX Ingress**, real-time **SSE (Server-Sent Events) streaming** via LangChain and OpenAI, and seamless SecretOps using **Doppler**.

## 💡 Architecture Overview

```text
[Client / Load Tester] 
        │
        ▼ (api.kyles-ai.local / HTTP: 80)
┌──────────────────────────────────────────┐
│         NGINX Ingress Controller         │
└──────────────────────────────────────────┘
        │
        ▼ (L7 Routing)
┌──────────────────────────────────────────┐
│               Go L7 Router               │ ── (Metrics API: /metrics) ──┐
│ (Thread-safe Round-Robin Load Balancer)  │                              │
└──────────────────────────────────────────┘                              │
        │             │             │                                     │
        ▼             ▼             ▼                                     ▼
┌────────────┐┌────────────┐┌────────────┐                     ┌────────────────────┐
│ LangChain  ││ LangChain  ││ LangChain  │ ◀── (Scale Out) ─── │ Custom K8s Operator│
│  LLM Pod   ││  LLM Pod   ││  LLM Pod   │                     │ (ModelAutoscaler)  │
└────────────┘└────────────┘└────────────┘                     └────────────────────┘
        │             │             │                                     ▲
        ▼             ▼             ▼                                     │
┌──────────────────────────────────────────┐                   ┌────────────────────┐
│         OpenAI API (GPT-4 / 3.5)         │                   │  Doppler Operator  │
│         (SSE Streaming Response)         │ ◀── (Injects) ─── │  (Secret Manager)  │
└──────────────────────────────────────────┘                   └────────────────────┘
```

## 🛠️ Tech Stack
- **Backend/Router:** Go (1.26+), `net/http/httputil`, `sync/atomic`
- **AI Model:** Python 3.11, FastAPI, Uvicorn, LangChain, OpenAI API
- **Infrastructure:** Kubernetes (Kind), NGINX Ingress, Docker, Multi-stage Builds
- **Orchestration/Operator:** Kubebuilder, K8s Custom Resource Definitions (CRD), `client-go`
- **SecretOps:** Doppler Kubernetes Operator

## 🎯 Milestones & Features

### ✅ Milestone 1: Real LLM Integration & SSE Streaming (Python)
- Upgraded from a dummy blocking model to a real AI integration using **LangChain** and **OpenAI API**.
- Implemented **Server-Sent Events (SSE)** via FastAPI to stream token-by-token responses back to the client in real-time, matching standard AI chatbot experiences.

### ✅ Milestone 2: Go-based L7 API Gateway
- Implemented a custom Reverse Proxy in Go.
- Utilized `sync/atomic` for thread-safe, high-concurrency Round-Robin traffic distribution.
- Optimized container size using Go multi-stage builds (`golang:alpine` -> `alpine`), resulting in a minimal binary image.

### ✅ Milestone 3: Kubernetes MSA & Ingress Routing
- Migrated from local Docker to a local Kubernetes cluster using `Kind`.
- Replaced basic NodePort with **NGINX Ingress Controller** for production-like local domain routing (`api.kyles-ai.local`).

### ✅ Milestone 4: SecretOps with Doppler
- Eliminated hardcoded secrets in YAML manifests.
- Integrated the **Doppler Kubernetes Operator** to securely fetch and inject `OPENAI_API_KEY` directly into the AI Model pods at runtime.

### 🚧 Milestone 5: Custom K8s Autoscaling Operator (WIP)
- Bypassing standard HPA (CPU/Mem) to implement custom business-metric autoscaling.
- The Go Router exposes a `/metrics` endpoint tracking **Active In-flight Requests**.
- Building a K8s Custom Operator using `kubebuilder` that polls the metric and dynamically scales the Python Model Deployment via the K8s API.

---

## 🚀 Quick Start (Local Kubernetes Environment)

### 1. Prerequisites
- Docker & Docker Desktop
- [Kind (Kubernetes in Docker)](https://kind.sigs.k8s.io/)
- `kubectl` & `make`
- [Doppler Account & Service Token](https://doppler.com)

### 2. Local Domain Setup
Add the local domain to your `/etc/hosts` file:
```bash
sudo nano /etc/hosts
# Add the following line:
127.0.0.1 api.kyles-ai.local
```

### 3. Cluster Setup & Ingress Controller
```bash
# Create Kind cluster with Ingress support
kind create cluster --name ai-cluster --config k8s/kind-config.yaml

# Install NGINX Ingress Controller
kubectl apply -f [https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml](https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml)

# Build and Load images into Kind
docker build -t dummy-ai-model:latest -f Dockerfile .
cd router && docker build -t go-router:latest . && cd ..
kind load docker-image dummy-ai-model:latest --name ai-cluster
kind load docker-image go-router:latest --name ai-cluster
```

### 4. SecretOps Setup (Doppler)
Inject your Doppler Service Token into the cluster so the operator can fetch the `OPENAI_API_KEY`.
```bash
kubectl create secret generic doppler-token-secret \
  --namespace default \
  --from-literal=serviceToken="dp.st.your_doppler_service_token_here"
```

### 5. Deploy Infrastructure
```bash
# Deploy Doppler configuration, Python Models, Go Router, and Ingress
kubectl apply -f k8s/doppler.yaml
kubectl apply -f k8s/dummy-model.yaml
kubectl apply -f k8s/router.yaml
kubectl apply -f k8s/ingress.yaml
```

### 6. Test Traffic (Real-time SSE Streaming)
Use `curl` with the `-N` (no buffer) flag to see the real-time token streaming.
```bash
curl -N -X POST [http://api.kyles-ai.local/api/chat](http://api.kyles-ai.local/api/chat) \
     -H "Content-Type: application/json" \
     -d '{"text": "Hello, Custom K8s Router! Are you alive?"}'
```

### 7. Run Custom Operator (Autoscaler)
```bash
# Install CRD to cluster
cd operator
make install

# Apply autoscaling rules
kubectl apply -f ../k8s/autoscaler.yaml

# Run the operator locally to watch metrics and scale
make run
```
