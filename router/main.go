package main

import (
	"fmt"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"sync/atomic"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace" // trace 패키지 누락된 부분 추가
)

// 서빙을 담당할 백엔드(Python 더미 AI) 서버들의 주소
var backendServers = []string{
	// K8s 내부에서는 Service 이름이 곧 도메인이 됩니다.
	"http://dummy-ai-model-svc:80",
}

// 스레드 세이프(Thread-safe)한 라운드 로빈 카운터
var requestCounter uint64

// 현재 처리 중인(In-flight) 활성 요청 수
var activeRequests int64

// getNextServer는 라운드 로빈 방식으로 다음 호출할 서버의 URL을 반환합니다.
// 경로별 누적 요청 수를 추적할 카운터 (Grafana 대시보드용)
var chatRequests uint64
var summarizeRequests uint64

// TTFT 측정을 위한 전역 변수
var ttftSumMs uint64 // TTFT 합계 (밀리초)
var ttftCount uint64 // TTFT 측정 횟수

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

	// --- [Tracing 핵심 구간] ---
	// 1. 헤더 추출
	ctx := otel.GetTextMapPropagator().Extract(r.Context(), propagation.HeaderCarrier(r.Header))

	// 2. 새로운 Span & Context 생성
	tracer := otel.Tracer("go-router")
	newCtx, span := tracer.Start(ctx, "Go Router Forwarding")
	defer span.End()

	// 3. Request 객체의 Context 교체
	r = r.WithContext(newCtx)

	// 4. 교체된 Context를 바탕으로 대상 서버에 보낼 헤더(traceparent) 덮어쓰기
	otel.GetTextMapPropagator().Inject(newCtx, propagation.HeaderCarrier(r.Header))

	fmt.Printf("[Go Router] 트래픽 포워딩 ➡️ %s (경로: %s) | TraceID: %s\n", targetURL, r.URL.Path, span.SpanContext().TraceID().String())
	// ---------------------------

	// Go의 내장 리버스 프록시 객체 생성
	proxy := httputil.NewSingleHostReverseProxy(parsedURL)

	// 대상 서버가 호스트 기반 라우팅을 할 수 있도록 헤더 조작
	r.Host = parsedURL.Host

	// 🔥 [수정 1] 프록시 실행 시, 채팅 API라면 우리가 만든 TTFT 인터셉터로 감싸서 넘깁니다!
	if r.URL.Path == "/api/chat" {
		tw := &ttftResponseWriter{
			ResponseWriter: w,
			startTime:      time.Now(),
		}
		proxy.ServeHTTP(tw, r)
	} else {
		proxy.ServeHTTP(w, r)
	}
}

// Prometheus 메트릭 엔드포인트
func metricsHandler(w http.ResponseWriter, r *http.Request) {
	currentActive := atomic.LoadInt64(&activeRequests)
	chatTotal := atomic.LoadUint64(&chatRequests)
	summarizeTotal := atomic.LoadUint64(&summarizeRequests)

	// 🔥 [수정 2] 메모리에 저장된 TTFT 변수들 읽어오기
	currentTtftSum := atomic.LoadUint64(&ttftSumMs)
	currentTtftCount := atomic.LoadUint64(&ttftCount)

	// [핵심] Prometheus가 긁어갈 수 있는 Plain Text 포맷으로 헤더 및 내용 출력
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")

	// 1. 활성 요청 수 게이지 (Gauge)
	fmt.Fprintf(w, "# HELP active_requests Number of currently active requests\n")
	fmt.Fprintf(w, "# TYPE active_requests gauge\n")
	fmt.Fprintf(w, "active_requests %d\n", currentActive)

	// 2. 총 요청 수 카운터 (Counter)
	fmt.Fprintf(w, "# HELP http_requests_total Total number of HTTP requests\n")
	fmt.Fprintf(w, "# TYPE http_requests_total counter\n")
	fmt.Fprintf(w, "http_requests_total{path=\"/api/chat\"} %d\n", chatTotal)
	fmt.Fprintf(w, "http_requests_total{path=\"/api/summarize\"} %d\n", summarizeTotal)

	// 🔥 [수정 2] Prometheus가 긁어갈 수 있도록 텍스트로 출력
	fmt.Fprintf(w, "# HELP ai_ttft_sum_milliseconds Total sum of Time To First Token in ms\n")
	fmt.Fprintf(w, "# TYPE ai_ttft_sum_milliseconds counter\n")
	fmt.Fprintf(w, "ai_ttft_sum_milliseconds %d\n", currentTtftSum)

	fmt.Fprintf(w, "# HELP ai_ttft_count Total number of TTFT measurements\n")
	fmt.Fprintf(w, "# TYPE ai_ttft_count counter\n")
	fmt.Fprintf(w, "ai_ttft_count %d\n", currentTtftCount)
}

// ttftResponseWriter는 프록시 응답을 가로채서 첫 토큰 도달 시간을 잽니다.
type ttftResponseWriter struct {
	http.ResponseWriter
	startTime  time.Time
	firstToken bool
}

func (w *ttftResponseWriter) Write(b []byte) (int, error) {
	if !w.firstToken {
		w.firstToken = true
		ttft := time.Since(w.startTime).Milliseconds()

		fmt.Printf("⏱️ [TTFT 측정] 첫 토큰 도달 시간: %d ms\n", ttft)

		atomic.AddUint64(&ttftSumMs, uint64(ttft))
		atomic.AddUint64(&ttftCount, 1)
	}
	return w.ResponseWriter.Write(b)
}

func (w *ttftResponseWriter) Flush() {
	if f, ok := w.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

func main() {
	// 특정 엔드포인트(또는 루트 "/")를 로드밸런서에 매핑
	// W3C Trace Context 전파 설정 (OpenTelemetry 필수)
	otel.SetTextMapPropagator(propagation.TraceContext{})

	// 라우팅 등록
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
