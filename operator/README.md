```markdown
# Lightweight AI Model Autoscaler Operator

> A Kubernetes Custom Operator designed to provide intelligent, traffic-aware autoscaling and seamless observability for the Lightweight AI Model Serving Router.

## Description

Traditional Horizontal Pod Autoscalers (HPA) often struggle with the unique burst traffic patterns of LLMs and AI model serving, especially when relying solely on CPU or Memory metrics. This project solves that by introducing a custom Kubernetes Operator tailored for AI inference workloads.

Through the `ModelAutoscaler` Custom Resource Definition (CRD), this operator directly polls custom Prometheus metrics (e.g., `active_requests`) from a Go-based lightweight API router. By reacting to the actual queue depth and active connections rather than lagging hardware metrics, it achieves precise and immediate Scale-Outs during high traffic spikes, and efficient Scale-Ins during idle periods. 

Furthermore, this infrastructure is built with first-class **Observability**. Integrated natively with the Grafana + Loki + Promtail stack, it centralizes distributed logs from both the Go router and the underlying Python AI pods, making end-to-end tracing and debugging exceptionally fast and intuitive.

## Getting Started

### Prerequisites
- go version v1.24.6+
- docker version 17.03+.
- kubectl version v1.11.3+.
- Access to a Kubernetes v1.11.3+ cluster.

### To Deploy on the cluster
**Build and push your image to the location specified by `IMG`:**

```sh
make docker-build docker-push IMG=<some-registry>/operator:tag
```

**NOTE:** This image ought to be published in the personal registry you specified.
And it is required to have access to pull the image from the working environment.
Make sure you have the proper permission to the registry if the above commands don’t work.

**Install the CRDs into the cluster:**

```sh
make install
```

**Deploy the Manager to the cluster with the image specified by `IMG`:**

```sh
make deploy IMG=<some-registry>/operator:tag
```

> **NOTE**: If you encounter RBAC errors, you may need to grant yourself cluster-admin
privileges or be logged in as admin.

**Create instances of your solution**
You can apply the samples (examples) from the config/sample:

```sh
kubectl apply -k config/samples/
```

>**NOTE**: Ensure that the samples has default values to test it out.

### To Uninstall
**Delete the instances (CRs) from the cluster:**

```sh
kubectl delete -k config/samples/
```

**Delete the APIs(CRDs) from the cluster:**

```sh
make uninstall
```

**UnDeploy the controller from the cluster:**

```sh
make undeploy
```

## Project Distribution

Following the options to release and provide this solution to the users.

### By providing a bundle with all YAML files

1. Build the installer for the image built and published in the registry:

```sh
make build-installer IMG=<some-registry>/operator:tag
```

2. Using the installer

Users can just run `kubectl apply -f <URL for YAML BUNDLE>` to install
the project, i.e.:

```sh
kubectl apply -f [https://raw.githubusercontent.com/](https://raw.githubusercontent.com/)<org>/operator/<tag or branch>/dist/install.yaml
```

### By providing a Helm Chart

1. Build the chart using the optional helm plugin

```sh
kubebuilder edit --plugins=helm/v2-alpha
```

2. See that a chart was generated under `dist/chart`, and users
can obtain this solution from there.

## Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

**NOTE:** Run `make help` for more information on all potential `make` targets. More information can be found via the [Kubebuilder Documentation](https://book.kubebuilder.io/introduction.html).

## License

Copyright 2026.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

---

## 🚀 Recent Updates & Milestones

### [KYL-71] Custom K8s Operator: AI Model Autoscaler
* **Custom Resource Definition (CRD):** `ModelAutoscaler` (`serving.kyle.io`) 기반의 사용자 정의 리소스 구현.
* **Traffic-Aware Scaling:** Go 라우터의 Prometheus 엔드포인트(`active_requests`)를 실시간으로 폴링하여 부하를 감지하는 로직 구현.
* **Dynamic Scale In/Out:** 동시 요청 수에 비례하여 AI 파드를 유연하게 조절. (E2E 테스트 완료: 15개 동시 요청 시 파드 `1 -> 8` 스케일 아웃 및 작업 완료 후 `1`로 안정적 스케일 인)

### [KYL-74] Observability: Centralized Logging System
* **Loki & Promtail 연동:** Helm을 이용해 K8s 클러스터 내 `observability` 네임스페이스에 가벼운 로그 수집 파이프라인 구축.
* **Grafana 통합 로깅:** 파드 내부로 들어갈 필요 없이, Grafana 대시보드 내에서 LogQL(예: `{app="dummy-ai-model"}`)을 통해 라우터 및 AI 서빙 파드의 에러/실시간 로그를 통합 추적 및 모니터링 가능한 환경 완성.
```

