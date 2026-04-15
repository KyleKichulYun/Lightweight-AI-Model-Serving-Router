# 1단계: 빌더 (컴파일 환경) - 버전을 alpine 으로 변경하여 최신 유지
FROM golang:alpine AS builder

# OS 필수 패키지 설치
RUN apk add --no-cache git

WORKDIR /app

# Go 모듈 캐싱 (종속성이 변경되지 않으면 이 레이어는 재사용됨)
# COPY go.mod go.sum ./
# RUN go mod download
# (현재 go.mod가 없다면 바로 COPY . . 로 진행해도 됩니다)

COPY . .

# CGO 비활성화로 완전한 정적 바이너리 생성 (K8s 환경에서 오류 방지)
RUN CGO_ENABLED=0 GOOS=linux go build -o go-router main.go

# 2단계: 실행 환경 (극경량 이미지)
FROM alpine:latest

# 타임존 및 인증서 세팅 (외부 API 통신 시 필수)
RUN apk --no-cache add ca-certificates tzdata
ENV TZ=Asia/Seoul

WORKDIR /app
# 빌더 단계에서 만들어진 바이너리만 복사
COPY --from=builder /app/go-router .

EXPOSE 8080
CMD ["./go-router"]