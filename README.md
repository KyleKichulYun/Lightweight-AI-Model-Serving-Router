```markdown
# 🚀 Lightweight AI Model Serving Router & Autoscaler

A custom Kubernetes-native MLOps infrastructure project. This project demonstrates a lightweight, high-performance API Gateway (Router) built in **Go**, combined with a **Custom Kubernetes Operator** that autoscales Python-based AI model containers based on custom business metrics (Active In-flight Requests).

## 💡 Architecture Overview

```text
[Client / Load Tester] 
        │
        ▼ (NodePort: 30080 / Port-Forward: 8080)
┌──────────────────────────────────────────┐
│             Go L7 Router                 │ ── (Metrics API: /metrics) ──┐
│ (Thread-safe Round-Robin Load Balancer)  │                              │
└──────────────────────────────────────────┘                              │
        │             │             │                                     │
        ▼             ▼             ▼                                     ▼
┌────────────┐┌────────────┐┌────────────┐                     ┌────────────────────┐
│  AI Model  ││  AI Model  ││  AI Model  │ ◀── (Scale Out) ─── │ Custom K8s Operator│
│  (Python)  ││  (Python)  ││  (Python)  │                     │ (ModelAutoscaler)  │
└────────────┘└────────────┘└────────────┘                     └────────────────────┘
```

## 🛠️ Tech Stack
- **Backend/Router:** Go (1.26+), `net/http/httputil`, `sync/atomic`
- **AI Model (Dummy):** Python 3.11, FastAPI, Uvicorn (Simulates GPU blocking)
- **Infrastructure:** Kubernetes (Kind), Docker, Multi-stage Builds
- **Orchestration/Operator:** Kubebuilder, K8s Custom Resource Definitions (CRD), `client-go`

## 🎯 Milestones & Features

### ✅ Milestone 1: Heavy AI Model Simulation (Python)
- Developed a lightweight FastAPI container that deliberately simulates GPU bottlenecking (`time.sleep(3)` blocking the worker thread).
- Configured dynamic environment variables (`SERVER_ID`) via K8s Downward API to identify serving pods.

### ✅ Milestone 2: Go-based L7 API Gateway
- Implemented a custom Reverse Proxy in Go.
- Utilized `sync/atomic` for thread-safe, high-concurrency Round-Robin traffic distribution.
- Optimized container size using Go multi-stage builds (`golang:alpine` -> `alpine`), resulting in a minimal binary image.

### ✅ Milestone 3: Kubernetes MSA Deployment
- Migrated from local Docker to a local Kubernetes cluster using `Kind`.
- Configured declarative YAML manifests for `Deployment` and internal L4 `Service` routing.
- Exposed the Go Router via `NodePort` for external ingress traffic.

### ✅ Milestone 4: Custom K8s Autoscaling Operator (WIP)
- Bypassed standard HPA (CPU/Mem) to implement custom business-metric autoscaling.
- The Go Router exposes a `/metrics` endpoint tracking **Active In-flight Requests**.
- Built a K8s Custom Operator using `kubebuilder` that polls the metric and dynamically scales the Python Model Deployment via the K8s API.

---

## 🚀 Quick Start (Local Kubernetes Environment)

### 1. Prerequisites
- Docker & Docker Desktop
- [Kind (Kubernetes in Docker)](https://kind.sigs.k8s.io/)
- `kubectl` & `make`

### 2. Cluster Setup & Build
```bash
# Create Kind cluster
kind create cluster --name ai-cluster

# Build images
docker build -t dummy-ai-model:latest -f Dockerfile .
cd router && docker build -t go-router:latest . && cd ..

# Load images into Kind
kind load docker-image dummy-ai-model:latest --name ai-cluster
kind load docker-image go-router:latest --name ai-cluster
```

### 3. Deploy Infrastructure
```bash
# Deploy Python Models & Go Router
kubectl apply -f k8s/dummy-model.yaml
kubectl apply -f k8s/router.yaml

# Port-forward the Router for testing
kubectl port-forward svc/go-router-svc 8080:8080
```

### 4. Test Traffic
```bash
curl -X POST http://localhost:8080/api/summarize \
     -H "Content-Type: application/json" \
     -d '{"text": "Hello, Custom K8s Router!"}'
```

### 5. Run Custom Operator (Autoscaler)
```bash
# Install CRD to cluster
cd operator
make install

# Apply autoscaling rules
kubectl apply -f ../k8s/autoscaler.yaml

# Run the operator locally to watch metrics and scale
make run
```
```
