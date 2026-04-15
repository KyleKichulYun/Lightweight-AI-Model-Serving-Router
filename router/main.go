package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"sync/atomic"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
)

// 전역 변수 설정
var (
	backendServers  = []string{"http://localhost:80"}
	requestCounter  uint64
	chatRequests    uint64
	summarizeRequests uint64
	ttftSumMs       uint64
	ttftCount       uint64

	// Backpressure용 세마포어 (최대 동시성 100으로 가정)
	semaphore = make(chan struct{}, 100)

	// 전역 Transport (커넥션 풀링 핵심)
	sharedTransport = &http.Transport{
		Proxy: http.ProxyFromEnvironment,
		DialContext: (&net.Dialer{
			Timeout:   30 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		MaxIdleConns:          1000,
		MaxIdleConnsPerHost:   100,
		IdleConnTimeout:       90 * time.Second,
		TLSHandshakeTimeout:   10 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
		ForceAttemptHTTP2:     true,
	}

	proxies = make(map[string]*httputil.ReverseProxy)
)

func init() {
	for _, addr := range backendServers {
		target, _ := url.Parse(addr)
		p := httputil.NewSingleHostReverseProxy(target)
		p.Transport = sharedTransport
		proxies[addr] = p
	}
}

func getNextServer() string {
	nextIndex := atomic.AddUint64(&requestCounter, 1)
	return backendServers[nextIndex%uint64(len(backendServers))]
}

func loadBalancerHandler(w http.ResponseWriter, r *http.Request) {
	// 1. Backpressure 제어
	select {
	case semaphore <- struct{}{}:
		defer func() { <-semaphore }()
	default:
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = fmt.Fprintf(w, `{"error": "Too many requests (Backpressure active)"}`)
		return
	}

	// 2. 캐싱된 프록시 객체 획득
	targetAddr := getNextServer()
	proxy, ok := proxies[targetAddr]
	if !ok {
		http.Error(w, "Backend not found", http.StatusBadGateway)
		return
	}

	// 3. Tracing & Context 전파
	ctx := otel.GetTextMapPropagator().Extract(r.Context(), propagation.HeaderCarrier(r.Header))
	tracer := otel.Tracer("go-router")
	newCtx, span := tracer.Start(ctx, "Go Router Forwarding")
	defer span.End()

	r = r.WithContext(newCtx)
	otel.GetTextMapPropagator().Inject(newCtx, propagation.HeaderCarrier(r.Header))

	// 대상 서버 호스트 헤더 동기화
	parsedURL, _ := url.Parse(targetAddr)
	r.Host = parsedURL.Host

	fmt.Printf("[Go Router] ➡️ %s | Path: %s | TraceID: %s\n", targetAddr, r.URL.Path, span.SpanContext().TraceID().String())

	// 4. 경로별 핸들링 및 실행 (단일 지점 실행 후 리턴)
	if r.URL.Path == "/api/chat" {
		atomic.AddUint64(&chatRequests, 1)
		tw := &ttftResponseWriter{
			ResponseWriter: w,
			startTime:      time.Now(),
		}
		proxy.ServeHTTP(tw, r)
	} else {
		if r.URL.Path == "/api/summarize" {
			atomic.AddUint64(&summarizeRequests, 1)
		}
		proxy.ServeHTTP(w, r)
	}
}

// Prometheus 메트릭 엔드포인트
func metricsHandler(w http.ResponseWriter, _ *http.Request) {
	currentActive := len(semaphore)
	chatTotal := atomic.LoadUint64(&chatRequests)
	summarizeTotal := atomic.LoadUint64(&summarizeRequests)

	// 🔥 [수정 2] 메모리에 저장된 TTFT 변수들 읽어오기
	currentTtftSum := atomic.LoadUint64(&ttftSumMs)
	currentTtftCount := atomic.LoadUint64(&ttftCount)

	// [핵심] Prometheus가 긁어갈 수 있는 Plain Text 포맷으로 헤더 및 내용 출력
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")

	// 1. 활성 요청 수 게이지 (Gauge)
	_, _ = fmt.Fprintf(w, "# HELP active_requests Number of currently active requests\n")
	_, _ = fmt.Fprintf(w, "# TYPE active_requests gauge\n")
	_, _ = fmt.Fprintf(w, "active_requests %d\n", currentActive)

	// 2. 총 요청 수 카운터 (Counter)
	_, _ = fmt.Fprintf(w, "# HELP http_requests_total Total number of HTTP requests\n")
	_, _ = fmt.Fprintf(w, "# TYPE http_requests_total counter\n")
	_, _ = fmt.Fprintf(w, "http_requests_total{path=\"/api/chat\"} %d\n", chatTotal)
	_, _ = fmt.Fprintf(w, "http_requests_total{path=\"/api/summarize\"} %d\n", summarizeTotal)

	// 🔥 Prometheus가 긁어갈 수 있도록 텍스트로 출력
	_, _ = fmt.Fprintf(w, "# HELP ai_ttft_sum_milliseconds Total sum of Time To First Token in ms\n")
	_, _ = fmt.Fprintf(w, "# TYPE ai_ttft_sum_milliseconds counter\n")
	_, _ = fmt.Fprintf(w, "ai_ttft_sum_milliseconds %d\n", currentTtftSum)

	_, _ = fmt.Fprintf(w, "# HELP ai_ttft_count Total number of TTFT measurements\n")
	_, _ = fmt.Fprintf(w, "# TYPE ai_ttft_count counter\n")
	_, _ = fmt.Fprintf(w, "ai_ttft_count %d\n", currentTtftCount)
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

// guardrailMiddleware는 들어오는 요청의 Body를 검사하여 위험 프롬프트를 차단합니다.
func guardrailMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// 채팅 API이고 POST 요청일 때만 검사
		if r.URL.Path == "/api/chat" && r.Method == http.MethodPost {
			// 1. Request Body 읽기
			bodyBytes, err := io.ReadAll(r.Body)
			if err == nil {
				// 원본 데이터를 다시 읽을 수 있도록 Body 복구
				r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
				bodyString := string(bodyBytes)

				// 2. 금지어 (테스트용)
				forbiddenWords := []string{
					"바보",
				}

				// 3. 검사 및 차단
				for _, word := range forbiddenWords {
					if strings.Contains(strings.ToLower(bodyString), word) {
						fmt.Printf("🛡️ [Guardrail] 위험 키워드 감지 및 차단: '%s'\n", word)

						w.Header().Set("WWW-Authenticate", `Basic realm="Restricted"`)
						w.Header().Set("Content-Type", "application/json")
						w.WriteHeader(http.StatusUnauthorized)
						_, _ = w.Write([]byte(`{"error": "401 Unauthorized: Guardrail에 의해 차단되었습니다."}`))
						return
					}
				}
			}
		}
		// 안전한 요청이면 원래 라우터 핸들러 실행
		next(w, r)
	}
}

func main() {
	// W3C Trace Context 전파 설정 (OpenTelemetry 필수)
	otel.SetTextMapPropagator(propagation.TraceContext{})

	// 라우팅 등록
	http.HandleFunc("/api/summarize", loadBalancerHandler)

	// 채팅 API에 Guardrail 미들웨어 적용
	http.HandleFunc("/api/chat", guardrailMiddleware(loadBalancerHandler))
	http.HandleFunc("/metrics", metricsHandler)

	port := ":8080"
	fmt.Printf("🚀 Go 기반 AI 모델 서빙 라우터 시작 (포트 %s)\n", port)
	fmt.Printf("🎯 타겟 서버: %v\n", backendServers)

	if err := http.ListenAndServe(port, nil); err != nil {
		log.Fatalf("라우터 서버 실행 실패: %v", err)
	}
}