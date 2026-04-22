// benchmarks/scripts/load_test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

// 1. 바이너리 데이터 로드 (미리 읽어두어 오버헤드 최소화)
const binData = open('../data/chat_req.bin', 'b');

export const options = {
    stages: [
        { duration: '10s', target: 50 },  // 10초 동안 50명까지 증가 (Warm-up)
        { duration: '20s', target: 100 }, // 20초 동안 100명 유지 (Peak)
        { duration: '10s', target: 0 },   // 10초 동안 종료
    ],
    thresholds: {
        http_req_failed: ['rate<0.01'],   // 에러율 1% 미만 유지
        http_req_duration: ['p(95)<200'], // 95%의 요청은 200ms 이내 완료
    },
};

export default function () {
    const params = {
        headers: { 'Content-Type': 'application/x-protobuf' },
    };

    const res = http.post('http://localhost:8080/api/chat', binData, params);

    check(res, {
        'is status 200': (r) => r.status === 200,
    });

    sleep(0.1); // 초당 약 10회 요청 (VUs당)
}