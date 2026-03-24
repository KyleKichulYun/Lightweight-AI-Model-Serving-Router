package main

import (
	"fmt"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"sync/atomic"
)

// 서빙을 담당할 백엔드(Python 더미 AI) 서버들의 주소
var backendServers = []string{
	// K8s 내부에서는 Service 이름이 곧 도메인이 됩니다.
	"http://dummy-ai-model-svc:80",
}

// 스레드 세이프(Thread-safe)한 라운드 로빈 카운터
var requestCounter uint64

// [추가] 현재 처리 중인(In-flight) 활성 요청 수를 추적하기 위한 변수
var activeRequests int64

// getNextServer는 라운드 로빈 방식으로 다음 호출할 서버의 URL을 반환합니다.
// [추가] 경로별 누적 요청 수를 추적할 카운터 (Grafana 대시보드용)
var chatRequests uint64
var summarizeRequests uint64

func getNextServer() string {
	// atomic을 사용하여 동시성(Goroutine) 환경에서 안전하게 인덱스 증가
	nextIndex := atomic.AddUint64(&requestCounter, 1)
	return backendServers[nextIndex%uint64(len(backendServers))]
}

// loadBalancerHandler는 들어오는 트래픽을 백엔드로 포워딩합니다.
func loadBalancerHandler(w http.ResponseWriter, r *http.Request) {
	// [추가] 요청이 들어오면 활성 요청 수 1 증가, 끝나면(defer) 1 감소
	atomic.AddInt64(&activeRequests, 1)
	defer atomic.AddInt64(&activeRequests, -1)

	// [추가] URL 경로별로 트래픽 누적 카운트 증가
	if r.URL.Path == "/api/chat" {
		atomic.AddUint64(&chatRequests, 1)
	} else if r.URL.Path == "/api/summarize" {
		atomic.AddUint64(&summarizeRequests, 1)
	}

	targetURL := getNextServer()
	parsedURL, _ := url.Parse(targetURL)

	fmt.Printf("[Go Router] 트래픽 포워딩 ➡️ %s (경로: %s)\n", targetURL, r.URL.Path)

	// Go의 내장 리버스 프록시 객체 생성
	proxy := httputil.NewSingleHostReverseProxy(parsedURL)

	// 대상 서버가 호스트 기반 라우팅을 할 수 있도록 헤더 조작
	r.Host = parsedURL.Host

	// 프록시 실행 (요청 전달 및 응답 반환)
	proxy.ServeHTTP(w, r)
}

// [추가] Operator가 주기적으로 찔러볼 메트릭 엔드포인트
func metricsHandler(w http.ResponseWriter, r *http.Request) {
	currentActive := atomic.LoadInt64(&activeRequests)
	chatTotal := atomic.LoadUint64(&chatRequests)
	summarizeTotal := atomic.LoadUint64(&summarizeRequests)

	// [핵심] Prometheus가 긁어갈 수 있는 Plain Text 포맷으로 헤더 및 내용 출력
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")

	// 1. 활성 요청 수 게이지 (Gauge)
	fmt.Fprintf(w, "# HELP active_requests Number of currently active requests\n")
	fmt.Fprintf(w, "# TYPE active_requests gauge\n")
	fmt.Fprintf(w, "active_requests %d\n", currentActive)

	// 2. 총 요청 수 카운터 (Counter) - 어제 Grafana에서 쿼리했던 바로 그 이름!
	fmt.Fprintf(w, "# HELP http_requests_total Total number of HTTP requests\n")
	fmt.Fprintf(w, "# TYPE http_requests_total counter\n")
	fmt.Fprintf(w, "http_requests_total{path=\"/api/chat\"} %d\n", chatTotal)
	fmt.Fprintf(w, "http_requests_total{path=\"/api/summarize\"} %d\n", summarizeTotal)
}

func main() {
	// 특정 엔드포인트(또는 루트 "/")를 로드밸런서에 매핑
	http.HandleFunc("/api/summarize", loadBalancerHandler)
	http.HandleFunc("/api/chat", loadBalancerHandler)
	// [추가] 메트릭 라우팅 등록
	http.HandleFunc("/metrics", metricsHandler)

	port := ":8080"
	fmt.Printf("🚀 Go 기반 AI 모델 서빙 라우터 시작 (포트 %s)\n", port)
	fmt.Printf("🎯 타겟 서버: %v\n", backendServers)

	if err := http.ListenAndServe(port, nil); err != nil {
		log.Fatalf("라우터 서버 실행 실패: %v", err)
	}
}
