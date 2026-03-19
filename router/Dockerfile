# 1단계: 빌더 (컴파일 환경) - 버전을 alpine 으로 변경하여 최신 유지
FROM golang:alpine AS builder
WORKDIR /app
COPY go.mod ./
COPY main.go ./
# CGO 비활성화로 완전한 정적 바이너리 생성 (K8s 환경에서 오류 방지)
RUN CGO_ENABLED=0 GOOS=linux go build -o go-router main.go

# 2단계: 실행 환경 (극경량 이미지)
FROM alpine:latest
WORKDIR /app
# 빌더 단계에서 만들어진 바이너리만 복사
COPY --from=builder /app/go-router .

EXPOSE 8080
CMD ["./go-router"]