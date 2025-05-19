from whisper_live.client2 import TranscriptionClient
import time
import argparse

def main():
    parser = argparse.ArgumentParser(description='RTSP client')
    parser.add_argument('--rtsp_url', type=str, default='rtsp://localhost:8554/audio', help='RTSP URL')
    parser.add_argument('--chatbot_url', type=str, default='http://localhost:7000/stt', help='chatbot URL')
    args = parser.parse_args()

    client = TranscriptionClient(
        "localhost",
        9090,
        lang="ko",
        translate=False,
        model="large-v3-turbo",                             # also support hf_model => `Systran/faster-whisper-small`
        use_vad=True,
        vad_parameters = {"onset": 0.5, "min_silence_duration_ms": 1000},
        save_output_recording=False,                        # Only used for microphone input, False by Default
        output_recording_filename="./output_recording.wav", # Only used for microphone input
        output_transcription_path="./output.srt",
        log_transcription=True,
        max_clients=4,
        max_connection_time=600,
        style="no_clear",                                   # complete, no_clear, empty
        chatbot_url=args.chatbot_url,                       # Chatbot URL
        initial_prompt="이번 대화는 아파트 주소를 포함합니다. 아파트 동은 4자리 또는 3자리 숫자입니다. 예: 1001동 302호, 1203동 701호, 103동 2호",
    )
    
    while True:
        try:
            client(rtsp_url=args.rtsp_url)
        except Exception as e:
            print(f"An error occurred(Retry in 5 seconds.): {e}")
            time.sleep(5)
        except KeyboardInterrupt:
            print("Interrupted by user")
            break

if __name__ == "__main__":
    main()
