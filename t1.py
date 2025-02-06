import av
import pyaudio
import numpy as np

rtsp_url = "rtsp://localhost:8554/myrtsp"

print("[INFO]: Connecting to RTSP stream using PyAV...")
try:
    container = av.open(rtsp_url, format="rtsp", options={"rtsp_transport": "udp"})
    print("[INFO]: Successfully connected to RTSP stream.")
    audio_stream = next(s for s in container.streams if s.type == 'audio')

    p = pyaudio.PyAudio()
    stream = p.open(format=p.get_format_from_width(audio_stream.format.bytes),
                    channels=audio_stream.channels,
                    rate=int(audio_stream.rate),
                    output=True)

    for packet in container.demux(audio_stream):
        for frame in packet.decode():
            audio_data = frame.to_ndarray().tobytes()
            stream.write(audio_data)

    stream.stop_stream()
    stream.close()
    p.terminate()
except StopIteration:
    print("[ERROR]: No audio stream found in the RTSP stream.")
except Exception as e:
    print(f"[ERROR]: Unexpected error: {e}")