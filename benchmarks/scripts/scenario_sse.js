import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

// SSE 전용 커스텀 메트릭 정의
const ttftTrend = new Trend('ai_ttft_ms'); // Time To First Token

export const options = {
    vus: 50, // 스트리밍은 커넥션을 유지하므로 VUS를 적절히 조절
    duration: '1m',
    thresholds: {
        'ai_ttft_ms': ['p(95)<300'], // 첫 토큰은 300ms 이내에 도착해야 함
    },
};

const binData = open('../data/chat_req.bin', 'b');

export default function () {
    const params = {
        headers: {
            'Content-Type': 'application/x-protobuf',
            'Accept': 'text/event-stream'
        },
    };

    // 1. 요청 시작 시간 기록
    const startTime = Date.now();
    let firstTokenReceived = false;

    const res = http.post('http://localhost:8080/api/chat', binData, {
        ...params,
        responseType: 'text',
        // 스트리밍 데이터를 실시간으로 처리하기 위한 설정
    });

    // k6는 기본적으로 응답이 완료된 후 본문을 제공하므로,
    // 여기서는 '첫 바이트가 도착한 시간'을 TTFT의 근사치로 측정하거나
    // Python 백엔드에서 보낸 timestamp를 파싱하여 계산합니다.

    if (res.status === 200) {
        const timeToFirstByte = Date.now() - startTime;
        ttftTrend.add(timeToFirstByte);

        check(res, {
            'is sse format': (r) => r.body.includes('data:'),
            'is stream finished': (r) => r.body.includes('[DONE]'),
        });
    }

    sleep(1); // 다음 대화를 시도하기 전 휴식
}