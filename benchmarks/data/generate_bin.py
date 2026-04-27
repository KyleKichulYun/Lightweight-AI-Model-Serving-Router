# benchmarks/data/generate_bin.py
import model_service_pb2 as pb

def generate_test_payload():
    chat_req = pb.ChatRequest()
    chat_req.model_id = "hippufu-v1-optimized"
    chat_req.prompt = "안녕 히뿌푸! 오늘 판교 날씨에 맞춰서 기분 좋은 노래 추천해줘뿌!"

    # 바이너리로 직렬화
    with open("benchmarks/data/chat_req.bin", "wb") as f:
        f.write(chat_req.SerializeToString())

    print(f"✅ Test payload generated: benchmarks/data/chat_req.bin ({len(chat_req.SerializeToString())} bytes)")

if __name__ == "__main__":
    generate_test_payload()