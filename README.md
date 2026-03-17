# Lightweight-AI-Model-Serving-Router
사용 기술: Golang, Kubernetes, Docker, Python(FastAPI)  구현 목표:  Python으로 띄운 허접한 AI 모델(예: 텍스트 요약 모델) 컨테이너 여러 개를 준비.  Go 언어로 'API Gateway / 라우터'를 직접 개발. (트래픽이 들어오면 여유 있는 컨테이너로 분산시켜주는 로직)  더 나아가, 트래픽이 몰리면 K8s API를 Go로 직접 호출하여 AI 컨테이너를 스케일아웃(Auto-scaling)하는 커스텀 컨트롤러(Operator) 개발.
