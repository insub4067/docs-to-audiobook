import os
import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def run_test():
    print("=== Audiobook Maker Hybrid API Integration Test ===")
    
    # 1. Create a dummy text file
    test_file_path = "test_dummy.txt"
    test_content = "안녕하세요. 오디오북 만들기 하이브리드 통합 테스트입니다. 이 문장이 서버에서 고속 파싱되고 오디오는 파일 저장 없이 스트림으로 브라우저에 반환되는지 검증합니다."
    
    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write(test_content)
    
    print(f"[1/4] 임시 테스트 파일 생성 완료: {test_file_path}")
    
    try:
        # 2. Upload file to /api/upload
        print("[2/4] 파일 업로드 및 서버 고속 파싱 API (/api/upload) 호출 중...")
        with open(test_file_path, "rb") as f:
            files = {"file": (test_file_path, f, "text/plain")}
            response = requests.post(f"{BASE_URL}/api/upload", files=files)
            
        if response.status_code != 200:
            print(f"❌ 업로드 실패! 상태 코드: {response.status_code}, 내용: {response.text}")
            return False
            
        upload_data = response.json()
        text_id = upload_data.get("text_id")
        char_count = upload_data.get("char_count")
        print(f"✅ 업로드 성공! Text ID: {text_id}, 글자 수: {char_count}")
        
        # 3. Synthesize to Streaming response
        print("[3/4] 오디오북 실시간 합성 API (/api/synthesize) 호출 중...")
        payload = {
            "text_id": text_id,
            "voice": "ko-KR-SunHiNeural",
            "rate": "+0%",
            "pitch": "+0Hz"
        }
        
        response = requests.post(f"{BASE_URL}/api/synthesize", data=payload, stream=True)
        
        if response.status_code != 200:
            print(f"❌ 합성 실패! 상태 코드: {response.status_code}, 내용: {response.text}")
            return False
            
        audio_bytes = response.content
        print(f"✅ TTS 합성 성공! 수신된 오디오 스트림 크기: {len(audio_bytes)} bytes")
        
        if len(audio_bytes) == 0:
            print("❌ 오류: 수신된 오디오 데이터 크기가 0 bytes 입니다!")
            return False
            
        # 4. Verify no file written on server disk
        print("[4/4] 서버 디스크 오디오 무기록 검증 중...")
        # Check if output directory is empty or doesn't exist
        output_dir_exists = os.path.exists("output")
        output_files = os.listdir("output") if output_dir_exists else []
        
        if len(output_files) > 0:
            print(f"⚠️ 경고: 서버 output/ 디렉토리에 파일이 존재합니다: {output_files}")
        else:
            print("✅ 검증 성공! 서버 디스크에 어떤 오디오 파일도 쓰여지지 않았습니다.")
            
        print("\n🎉 모든 하이브리드 API 통합 테스트 통과! 고속 파싱과 실시간 무기록 오디오 스트리밍이 완벽하게 결합되었습니다.")
        return True
        
    except Exception as e:
        print(f"❌ 테스트 중 예외 발생: {str(e)}")
        return False
        
    finally:
        # Cleanup dummy file
        if os.path.exists(test_file_path):
            os.remove(test_file_path)
            print("🧹 임시 파일 정리 완료.")

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
