from whisper_live.client2 import TranscriptionClient
client = TranscriptionClient(
  "localhost",
  9090,
  lang="ko",
  translate=False,
  model="large-v3-turbo",                             # also support hf_model => `Systran/faster-whisper-small`
  use_vad=True,
  save_output_recording=False,                         # Only used for microphone input, False by Default
  output_recording_filename="./output_recording.wav", # Only used for microphone input
  max_clients=4,
  max_connection_time=600,
  style="no_clear",                                    # complete, no_clear, empty
)

client("d:\shopping.wav")
