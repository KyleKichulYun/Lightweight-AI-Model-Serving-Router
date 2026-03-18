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
	"http://localhost:8001",
	"http://localhost:8002",
	"http://localhost:8003",
}

// 스레드 세이프(Thread-safe)한 라운드 로빈 카운터
var requestCounter uint64

// getNextServer는 라운드 로빈 방식으로 다음 호출할 서버의 URL을 반환합니다.
func getNextServer() string {
	// atomic을 사용하여 동시성(Goroutine) 환경에서 안전하게 인덱스 증가
	nextIndex := atomic.AddUint64(&requestCounter, 1)
	return backendServers[nextIndex%uint64(len(backendServers))]
}

// loadBalancerHandler는 들어오는 트래픽을 백엔드로 포워딩합니다.
func loadBalancerHandler(w http.ResponseWriter, r *http.Request) {
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

func main() {
	// 특정 엔드포인트(또는 루트 "/")를 로드밸런서에 매핑
	http.HandleFunc("/api/summarize", loadBalancerHandler)

	port := ":8080"
	fmt.Printf("🚀 Go 기반 AI 모델 서빙 라우터 시작 (포트 %s)\n", port)
	fmt.Printf("🎯 타겟 서버: %v\n", backendServers)

	if err := http.ListenAndServe(port, nil); err != nil {
		log.Fatalf("라우터 서버 실행 실패: %v", err)
	}
}
