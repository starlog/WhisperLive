import os
import shutil
import wave

import logging
import numpy as np
import pyaudio
import threading
import json
import websocket
import uuid
import time
import av
import requests
import whisper_live.utils as utils

import pyaudio
import numpy as np
from datetime import datetime

isRecording = False
#isPause = False

# Add logging function to log to both console and file
def log_message(message, level="INFO"):
    """
    Log a message to both console and file.
    
    Args:
        message (str): The message to log
        level (str): Log level (INFO, ERROR, WARN, DEBUG)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{level}] {timestamp}: {message}"
    
    # Print to console
    print(formatted_message)
    
    # Append to log file
    log_file = "/tmp/whisper-client.log"
    with open(log_file, "a") as f:
        f.write(formatted_message + "\n")

def wait_for_keypress():
    log_message("Press Enter to continue recording...", "INFO")
    input()

class Client2:
    """
    Handles communication with a server using WebSocket.
    """
    INSTANCES = {}
    END_OF_AUDIO = "END_OF_AUDIO"

    def __init__(
        self,
        host=None,
        port=None,
        lang=None,
        translate=False,
        model="small",
        srt_file_path="output.srt",
        use_vad=True,
        log_transcription=True,
        max_clients=4,
        max_connection_time=600,
        last_segment=None,
        style=None,
        last_display=None,
        chatbot_url="",
        initial_prompt=None,  # Add this parameter
    ):
        """
        Initializes a Client instance for audio recording and streaming to a server.

        If host and port are not provided, the WebSocket connection will not be established.
        When translate is True, the task will be set to "translate" instead of "transcribe".
        he audio recording starts immediately upon initialization.

        Args:
            host (str): The hostname or IP address of the server.
            port (int): The port number for the WebSocket server.
            lang (str, optional): The selected language for transcription. Default is None.
            translate (bool, optional): Specifies if the task is translation. Default is False.
        """
        self.recording = False
        self.task = "transcribe"
        self.uid = str(uuid.uuid4())
        self.waiting = False
        self.last_response_received = None
        self.disconnect_if_no_response_for = 15
        self.language = lang
        self.model = model
        self.server_error = False
        self.srt_file_path = srt_file_path
        self.use_vad = use_vad
        self.last_segment = None
        self.last_received_segment = None
        self.log_transcription = log_transcription
        self.max_clients = max_clients
        self.max_connection_time = max_connection_time
        self.style = style
        self.last_display = None
        self.chatbot_url = chatbot_url
        self.initial_prompt = initial_prompt  # Add this line

        if translate:
            self.task = "translate"

        self.audio_bytes = None

        if host is not None and port is not None:
            socket_url = f"ws://{host}:{port}"
            self.client_socket = websocket.WebSocketApp(
                socket_url,
                on_open=lambda ws: self.on_open(ws),
                on_message=lambda ws, message: self.on_message(ws, message),
                on_error=lambda ws, error: self.on_error(ws, error),
                on_close=lambda ws, close_status_code, close_msg: self.on_close(
                    ws, close_status_code, close_msg
                ),
            )
        else:
            log_message("No host or port specified.", "ERROR")
            return

        Client2.INSTANCES[self.uid] = self

        # start websocket client in a thread
        self.ws_thread = threading.Thread(target=self.client_socket.run_forever)
        self.ws_thread.setDaemon(True)
        self.ws_thread.start()

        self.transcript = []
        log_message("* recording", "INFO")

    def handle_status_messages(self, message_data):
        """Handles server status messages."""
        status = message_data["status"]
        if status == "WAIT":
            self.waiting = True
            log_message(f"Server is full. Estimated wait time {round(message_data['message'])} minutes.", "INFO")
        elif status == "ERROR":
            log_message(f"Message from Server: {message_data['message']}", "ERROR")
            self.server_error = True
        elif status == "WARNING":
            log_message(f"Message from Server: {message_data['message']}", "WARN")

    def process_segments_complete(self, segments):
        """Processes transcript segments."""
        text = []
        for i, seg in reversed(list(enumerate(segments))):
            if seg.get("completed", True):
                if not self.last_segment:
                    self.last_segment = seg
                    log_message(f"{seg['start']}, {seg['end']} - {seg['text']}", "INFO")
                if seg != self.last_segment:
                    log_message(f"{seg['start']}, {seg['end']} - {seg['text']}", "INFO")
                    self.last_segment = seg
                break
    
    def process_segments_no_clear(self, segments):
        """Processes transcript segments."""
#        global isPause  # Declare global variable at the beginning of the function
        text = []
        for i, seg in enumerate(segments):
            if not text or text[-1] != seg["text"]:
                text.append(seg["text"])
                if i == len(segments) - 1 and not seg.get("completed", False):
                    self.last_segment = seg
                elif (self.server_backend == "faster_whisper" and seg.get("completed", False) and
                      (not self.transcript or
                        float(seg['start']) >= float(self.transcript[-1]['end']))):
                    self.transcript.append(seg)
                    utils.clear_screen()
                    if self.last_display is None:
                        self.last_display = f"인식 완료 ======> {seg['start']}, {seg['end']} - {seg['text']}"
                        if isRecording == True:
                            log_message("sending text to AI", "INFO")
                            try:
#                                isPause = True
                                response = requests.post(
                                    # "http://localhost:9999/webhook/message",
                                    self.chatbot_url,
                                    json={"text": seg['text']}
                                )
                                if response.status_code == 200:
                                    log_message("Successfully sent text to webhook.", "INFO")
                                else:
                                    log_message(f"Failed to send text to webhook. Status code: {response.status_code}", "ERROR")
                            except requests.exceptions.RequestException as e:
                                log_message(f"Exception occurred while sending text to webhook: {e}", "ERROR")
#                            wait_for_keypress()
                        log_message(self.last_display, "INFO")
                    else:
                        log_message(self.last_display, "INFO")
                        self.last_display = f"인식 완료 ======> {seg['start']}, {seg['end']} - {seg['text']}"
                        if isRecording == True:
                            log_message("sending text to AI", "INFO")
                            try:
#                                isPause = True
                                response = requests.post(
                                    # "http://localhost:9999/webhook/message",
                                    self.chatbot_url,
                                    json={"text": seg['text']}
                                )
                                if response.status_code == 200:
                                    log_message("Successfully sent text to webhook.", "INFO")
                                else:
                                    log_message(f"Failed to send text to webhook. Status code: {response.status_code}", "ERROR")
                            except requests.exceptions.RequestException as e:
                                log_message(f"Exception occurred while sending text to webhook: {e}", "ERROR")
#                            wait_for_keypress()
                        log_message(self.last_display, "INFO")
        # update last received segment and last valid response time
        if self.last_received_segment is None or self.last_received_segment != segments[-1]["text"]:
            self.last_response_received = time.time()
            self.last_received_segment = segments[-1]["text"]

        if self.log_transcription:
            # Truncate to last 3 entries for brevity.
            text = text[-1:]
            #utils.clear_screen()
            utils.print_transcript(text)

    def process_segments(self, segments):
        """Processes transcript segments."""
        text = []
        for i, seg in enumerate(segments):
            if not text or text[-1] != seg["text"]:
                text.append(seg["text"])
                if i == len(segments) - 1 and not seg.get("completed", False):
                    self.last_segment = seg
                elif (self.server_backend == "faster_whisper" and seg.get("completed", False) and
                      (not self.transcript or
                        float(seg['start']) >= float(self.transcript[-1]['end']))):
                    self.transcript.append(seg)
        # update last received segment and last valid response time
        if self.last_received_segment is None or self.last_received_segment != segments[-1]["text"]:
            self.last_response_received = time.time()
            self.last_received_segment = segments[-1]["text"]

        if self.log_transcription:
            # Truncate to last 3 entries for brevity.
            text = text[-3:]
            utils.clear_screen()
            utils.print_transcript(text)

    def on_message(self, ws, message):
        """
        Callback function called when a message is received from the server.

        It updates various attributes of the client based on the received message, including
        recording status, language detection, and server messages. If a disconnect message
        is received, it sets the recording status to False.

        Args:
            ws (websocket.WebSocketApp): The WebSocket client instance.
            message (str): The received message from the server.

        """
        message = json.loads(message)

        if self.uid != message.get("uid"):
            log_message("invalid client uid", "ERROR")
            return

        if "status" in message.keys():
            self.handle_status_messages(message)
            return

        if "message" in message.keys() and message["message"] == "DISCONNECT":
            log_message("Server disconnected due to overtime.", "INFO")
            self.recording = False

        if "message" in message.keys() and message["message"] == "SERVER_READY":
            self.last_response_received = time.time()
            self.recording = True
            self.server_backend = message["backend"]
            log_message(f"Server Running with backend {self.server_backend}", "INFO")
            return

        if "language" in message.keys():
            self.language = message.get("language")
            lang_prob = message.get("language_prob")
            log_message(
                f"Server detected language {self.language} with probability {lang_prob}", "INFO"
            )
            return

        if "segments" in message.keys():
            if self.style == "complete":
                self.process_segments_complete(message["segments"])
            elif self.style == "no_clear":
                self.process_segments_no_clear(message["segments"])
            else:
                self.process_segments(message["segments"])

    def on_error(self, ws, error):
        log_message(f"WebSocket Error: {error}", "ERROR")
        self.server_error = True
        self.error_message = error

    def on_close(self, ws, close_status_code, close_msg):
        log_message(f"Websocket connection closed: {close_status_code}: {close_msg}", "INFO")
        self.recording = False
        self.waiting = False

    def on_open(self, ws):
        """
        Callback function called when the WebSocket connection is successfully opened.

        Sends an initial configuration message to the server, including client UID,
        language selection, and task type.

        Args:
            ws (websocket.WebSocketApp): The WebSocket client instance.

        """
        log_message("Opened connection", "INFO")
        ws.send(
            json.dumps(
                {
                    "uid": self.uid,
                    "language": self.language,
                    "task": self.task,
                    "model": self.model,
                    "use_vad": self.use_vad,
                    "initial_prompt": self.initial_prompt,  # Add this line
                    "max_clients": self.max_clients,
                    "max_connection_time": self.max_connection_time,
                }
            )
        )

    def send_packet_to_server(self, message):
        """
        Send an audio packet to the server using WebSocket.

        Args:
            message (bytes): The audio data packet in bytes to be sent to the server.

        """
        try:
            self.client_socket.send(message, websocket.ABNF.OPCODE_BINARY)
        except Exception as e:
            log_message(e, "ERROR")

    def close_websocket(self):
        """
        Close the WebSocket connection and join the WebSocket thread.

        First attempts to close the WebSocket connection using `self.client_socket.close()`. After
        closing the connection, it joins the WebSocket thread to ensure proper termination.

        """
        try:
            self.client_socket.close()
        except Exception as e:
            log_message(f"Error closing WebSocket: {e}", "ERROR")

        try:
            self.ws_thread.join()
        except Exception as e:
            log_message(f"Error joining WebSocket thread: {e}", "ERROR")

    def get_client_socket(self):
        """
        Get the WebSocket client socket instance.

        Returns:
            WebSocketApp: The WebSocket client socket instance currently in use by the client.
        """
        return self.client_socket

    def write_srt_file(self, output_path="output.srt"):
        """
        Writes out the transcript in .srt format.

        Args:
            message (output_path, optional): The path to the target file.  Default is "output.srt".

        """
        if self.server_backend == "faster_whisper":
            if not self.transcript and self.last_segment is not None:
                self.transcript.append(self.last_segment)
            elif self.last_segment and self.transcript[-1]["text"] != self.last_segment["text"]:
                self.transcript.append(self.last_segment)
            utils.create_srt_file(self.transcript, output_path)

    def wait_before_disconnect(self):
        """Waits a bit before disconnecting in order to process pending responses."""
        assert self.last_response_received
        while time.time() - self.last_response_received < self.disconnect_if_no_response_for:
            continue


class TranscriptionTeeClient:
    """
    Client for handling audio recording, streaming, and transcription tasks via one or more
    WebSocket connections.

    Acts as a high-level client for audio transcription tasks using a WebSocket connection. It can be used
    to send audio data for transcription to one or more servers, and receive transcribed text segments.
    Args:
        clients (list): one or more previously initialized Client instances

    Attributes:
        clients (list): the underlying Client instances responsible for handling WebSocket connections.
    """
    def __init__(self, clients, save_output_recording=False, output_recording_filename="./output_recording.wav"):
        self.clients = clients
        if not self.clients:
            raise Exception("At least one client is required.")
        self.chunk = 4096
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000
        self.record_seconds = 60000
        self.save_output_recording = save_output_recording
        self.output_recording_filename = output_recording_filename
        self.frames = b""
        self.p = pyaudio.PyAudio()
        try:
            self.stream = self.p.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk,
            )
        except OSError as error:
            log_message(f"Unable to access microphone. {error}", "WARN")
            self.stream = None

    def __call__(self, audio=None, rtsp_url=None, hls_url=None, save_file=None):
        """
        Start the transcription process.

        Initiates the transcription process by connecting to the server via a WebSocket. It waits for the server
        to be ready to receive audio data and then sends audio for transcription. If an audio file is provided, it
        will be played and streamed to the server; otherwise, it will perform live recording.

        Args:
            audio (str, optional): Path to an audio file for transcription. Default is None, which triggers live recording.

        """
        assert sum(
            source is not None for source in [audio, rtsp_url, hls_url]
        ) <= 1, 'You must provide only one selected source'

        log_message("Waiting for server ready ...", "INFO")
        for client in self.clients:
            while not client.recording:
                if client.waiting or client.server_error:
                    self.close_all_clients()
                    return

        log_message("Server Ready!", "INFO")

        log_message("Selection start", "INFO")
        if hls_url is not None:
            log_message("HLS mode ...", "INFO")
            self.process_hls_stream(hls_url, save_file)
        elif audio is not None:
            log_message("Audio file mode ...", "INFO")
            resampled_file = utils.resample(audio)
            self.play_file(resampled_file)
        elif rtsp_url is not None:
            log_message("RTSP mode ...", "INFO")
            self.process_rtsp_stream(rtsp_url)
        else:
            log_message("Starting live recording ...", "INFO")
            global isRecording
            isRecording = True
            log_message(f"Recording {isRecording}", "INFO")
            self.record()

    def close_all_clients(self):
        """Closes all client websockets."""
        for client in self.clients:
            client.close_websocket()

    def write_all_clients_srt(self):
        """Writes out .srt files for all clients."""
        for client in self.clients:
            client.write_srt_file(client.srt_file_path)

    def multicast_packet(self, packet, unconditional=False):
        """
        Sends an identical packet via all clients.

        Args:
            packet (bytes): The audio data packet in bytes to be sent.
            unconditional (bool, optional): If true, send regardless of whether clients are recording.  Default is False.
        """
        for client in self.clients:
            if (unconditional or client.recording):
                client.send_packet_to_server(packet)

    def play_file(self, filename):
        """
        Play an audio file and send it to the server for processing.

        Reads an audio file, plays it through the audio output, and simultaneously sends
        the audio data to the server for processing. It uses PyAudio to create an audio
        stream for playback. The audio data is read from the file in chunks, converted to
        floating-point format, and sent to the server using WebSocket communication.
        This method is typically used when you want to process pre-recorded audio and send it
        to the server in real-time.

        Args:
            filename (str): The path to the audio file to be played and sent to the server.
        """

        # read audio and create pyaudio stream
        with wave.open(filename, "rb") as wavfile:
            self.stream = self.p.open(
                format=self.p.get_format_from_width(wavfile.getsampwidth()),
                channels=wavfile.getnchannels(),
                rate=wavfile.getframerate(),
                input=True,
                output=True,
                frames_per_buffer=self.chunk,
            )
            try:
                while any(client.recording for client in self.clients):
                    data = wavfile.readframes(self.chunk)
                    if data == b"":
                        break

                    audio_array = self.bytes_to_float_array(data)
                    self.multicast_packet(audio_array.tobytes())
                    self.stream.write(data)

                wavfile.close()

                for client in self.clients:
                    client.wait_before_disconnect()
                self.multicast_packet(Client.END_OF_AUDIO.encode('utf-8'), True)
                self.write_all_clients_srt()
                self.stream.close()
                self.close_all_clients()

            except KeyboardInterrupt:
                wavfile.close()
                self.stream.stop_stream()
                self.stream.close()
                self.p.terminate()
                self.close_all_clients()
                self.write_all_clients_srt()
                log_message("Keyboard interrupt.", "INFO")

    def process_rtsp_stream(self, rtsp_url):
        """
        Connect to an RTSP source, process the audio stream, and send it for transcription.

        Args:
            rtsp_url (str): The URL of the RTSP stream source.
        """
        log_message("Connecting to RTSP stream...", "INFO")
        try:
            container = av.open(rtsp_url, format="rtsp", options={"rtsp_transport": "tcp"})
            log_message("Successfully connected to RTSP stream.", "INFO")
            self.process_av_stream(container, stream_type="RTSP")
        except Exception as e:
            log_message(f"Failed to process RTSP stream: {e}", "ERROR")
        finally:
            for client in self.clients:
                client.wait_before_disconnect()
            self.multicast_packet(Client.END_OF_AUDIO.encode('utf-8'), True)
            self.close_all_clients()
            self.write_all_clients_srt()
        log_message("RTSP stream processing finished.", "INFO")

    def process_hls_stream(self, hls_url, save_file=None):
        """
        Connect to an HLS source, process the audio stream, and send it for transcription.

        Args:
            hls_url (str): The URL of the HLS stream source.
            save_file (str, optional): Local path to save the network stream.
        """
        log_message("Connecting to HLS stream...", "INFO")
        try:
            container = av.open(hls_url, format="hls")
            self.process_av_stream(container, stream_type="HLS", save_file=save_file)
        except Exception as e:
            log_message(f"Failed to process HLS stream: {e}", "ERROR")
        finally:
            for client in self.clients:
                client.wait_before_disconnect()
            self.multicast_packet(Client.END_OF_AUDIO.encode('utf-8'), True)
            self.close_all_clients()
            self.write_all_clients_srt()
        log_message("HLS stream processing finished.", "INFO")

    def process_av_stream(self, container, stream_type, save_file=None):
        """
        Process an AV container stream and send audio packets to the server.

        Args:
            container (av.container.InputContainer): The input container to process.
            stream_type (str): The type of stream being processed ("RTSP" or "HLS").
            save_file (str, optional): Local path to save the stream. Default is None.
        """
        global isRecording
        isRecording = True
        audio_stream = next((s for s in container.streams if s.type == "audio"), None)
        if not audio_stream:
            log_message(f"No audio stream found in {stream_type} source.", "ERROR")
            return

        log_message(f"audio_stream.format.bytes: {audio_stream.format.bytes}  audio_stream.channels: {audio_stream.channels}  audio_stream.rate: {audio_stream.rate}", "INFO")
        # p = pyaudio.PyAudio()
        # stream = p.open(format=p.get_format_from_width(audio_stream.format.bytes),
        #             channels=audio_stream.channels,
        #             rate=int(audio_stream.rate),
        #             output=True)

        output_container = None
        if save_file:
            output_container = av.open(save_file, mode="w")
            output_audio_stream = output_container.add_stream(codec_name="pcm_s16le", rate=self.rate)

        try:
            for packet in container.demux(audio_stream):
                for frame in packet.decode():
                    audio_data = frame.to_ndarray().tobytes()
                    # log_message(f"Sending audio packet to server: {len(audio_data)} bytes", "DEBUG")
                    # Just for testing only, playing audio
                    # stream.write(audio_data)
                    self.multicast_packet(audio_data)

                    if save_file:
                        output_container.mux(frame)
        except Exception as e:
            log_message(f"Error during {stream_type} stream processing: {e}", "ERROR")
        finally:
            # Wait for server to send any leftover transcription.
            time.sleep(5)
            self.multicast_packet(Client.END_OF_AUDIO.encode('utf-8'), True)
            if output_container:
                output_container.close()
            container.close()

    def save_chunk(self, n_audio_file):
        """
        Saves the current audio frames to a WAV file in a separate thread.

        Args:
        n_audio_file (int): The index of the audio file which determines the filename.
                            This helps in maintaining the order and uniqueness of each chunk.
        """
        t = threading.Thread(
            target=self.write_audio_frames_to_file,
            args=(self.frames[:], f"chunks/{n_audio_file}.wav",),
        )
        t.start()

    def finalize_recording(self, n_audio_file):
        """
        Finalizes the recording process by saving any remaining audio frames,
        closing the audio stream, and terminating the process.

        Args:
        n_audio_file (int): The file index to be used if there are remaining audio frames to be saved.
                            This index is incremented before use if the last chunk is saved.
        """
        if self.save_output_recording and len(self.frames):
            self.write_audio_frames_to_file(
                self.frames[:], f"chunks/{n_audio_file}.wav"
            )
            n_audio_file += 1
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        self.close_all_clients()
        if self.save_output_recording:
            self.write_output_recording(n_audio_file)
        self.write_all_clients_srt()

    def record(self):
        """
        Record audio data from the input stream and save it to a WAV file.

        Continuously records audio data from the input stream, sends it to the server via a WebSocket
        connection, and simultaneously saves it to multiple WAV files in chunks. It stops recording when
        the `RECORD_SECONDS` duration is reached or when the `RECORDING` flag is set to `False`.

        Audio data is saved in chunks to the "chunks" directory. Each chunk is saved as a separate WAV file.
        The recording will continue until the specified duration is reached or until the `RECORDING` flag is set to `False`.
        The recording process can be interrupted by sending a KeyboardInterrupt (e.g., pressing Ctrl+C). After recording,
        the method combines all the saved audio chunks into the specified `out_file`.
        """
        n_audio_file = 0
        if self.save_output_recording:
            if os.path.exists("chunks"):
                shutil.rmtree("chunks")
            os.makedirs("chunks")
        try:
            for _ in range(0, int(self.rate / self.chunk * self.record_seconds)):
                if not any(client.recording for client in self.clients):
                    break

                data = self.stream.read(self.chunk, exception_on_overflow=False)
                self.frames += data

                audio_array = self.bytes_to_float_array(data)

                self.multicast_packet(audio_array.tobytes())

                # save frames if more than a minute
                if len(self.frames) > 60 * self.rate:
                    if self.save_output_recording:
                        self.save_chunk(n_audio_file)
                        n_audio_file += 1
                    self.frames = b""
            self.write_all_clients_srt()

        except KeyboardInterrupt:
            self.finalize_recording(n_audio_file)

    def write_audio_frames_to_file(self, frames, file_name):
        """
        Write audio frames to a WAV file.

        The WAV file is created or overwritten with the specified name. The audio frames should be
        in the correct format and match the specified channel, sample width, and sample rate.

        Args:
            frames (bytes): The audio frames to be written to the file.
            file_name (str): The name of the WAV file to which the frames will be written.

        """
        with wave.open(file_name, "wb") as wavfile:
            wavfile: wave.Wave_write
            wavfile.setnchannels(self.channels)
            wavfile.setsampwidth(2)
            wavfile.setframerate(self.rate)
            wavfile.writeframes(frames)

    def write_output_recording(self, n_audio_file):
        """
        Combine and save recorded audio chunks into a single WAV file.

        The individual audio chunk files are expected to be located in the "chunks" directory. Reads each chunk
        file, appends its audio data to the final recording, and then deletes the chunk file. After combining
        and saving, the final recording is stored in the specified `out_file`.


        Args:
            n_audio_file (int): The number of audio chunk files to combine.
            out_file (str): The name of the output WAV file to save the final recording.

        """
        input_files = [
            f"chunks/{i}.wav"
            for i in range(n_audio_file)
            if os.path.exists(f"chunks/{i}.wav")
        ]
        with wave.open(self.output_recording_filename, "wb") as wavfile:
            wavfile: wave.Wave_write
            wavfile.setnchannels(self.channels)
            wavfile.setsampwidth(2)
            wavfile.setframerate(self.rate)
            for in_file in input_files:
                with wave.open(in_file, "rb") as wav_in:
                    while True:
                        data = wav_in.readframes(self.chunk)
                        if data == b"":
                            break
                        wavfile.writeframes(data)
                # remove this file
                os.remove(in_file)
        wavfile.close()
        # clean up temporary directory to store chunks
        if os.path.exists("chunks"):
            shutil.rmtree("chunks")

    @staticmethod
    def bytes_to_float_array(audio_bytes):
        """
        Convert audio data from bytes to a NumPy float array.

        It assumes that the audio data is in 16-bit PCM format. The audio data is normalized to
        have values between -1 and 1.

        Args:
            audio_bytes (bytes): Audio data in bytes.

        Returns:
            np.ndarray: A NumPy array containing the audio data as float values normalized between -1 and 1.
        """
        raw_data = np.frombuffer(buffer=audio_bytes, dtype=np.int16)
        return raw_data.astype(np.float32) / 32768.0


class TranscriptionClient(TranscriptionTeeClient):
    """
    Client for handling audio transcription tasks via a single WebSocket connection.

    Acts as a high-level client for audio transcription tasks using a WebSocket connection. It can be used
    to send audio data for transcription to a server and receive transcribed text segments.

    Args:
        host (str): The hostname or IP address of the server.
        port (int): The port number to connect to on the server.
        lang (str, optional): The primary language for transcription. Default is None, which defaults to English ('en').
        translate (bool, optional): Indicates whether translation tasks are required (default is False).
        save_output_recording (bool, optional): Indicates whether to save recording from microphone.
        output_recording_filename (str, optional): File to save the output recording.
        output_transcription_path (str, optional): File to save the output transcription.
        vad_parameters (dict, optional): Parameters for voice activity detection (e.g., {"onset": 0.5, "min_silence_duration_ms": 1000})

    Attributes:
        client (Client): An instance of the underlying Client class responsible for handling the WebSocket connection.

    Example:
        To create a TranscriptionClient and start transcription on microphone audio:
        ```python
        transcription_client = TranscriptionClient(host="localhost", port=9090)
        transcription_client()
        ```
    """
    def __init__(
        self,
        host,
        port,
        lang=None,
        translate=False,
        model="small",
        use_vad=True,
        vad_parameters=None,
        save_output_recording=False,
        output_recording_filename="./output_recording.wav",
        output_transcription_path="./output.srt",
        log_transcription=True,
        max_clients=4,
        max_connection_time=600,
        style=None,
        chatbot_url="http://localhost:9999/webhook/message",
        initial_prompt=None  # Add this parameter
    ):
        self.vad_parameters = vad_parameters
        self.client = Client2(
            host, port, lang, translate, model, srt_file_path=output_transcription_path,
            use_vad=use_vad, log_transcription=log_transcription, max_clients=max_clients,
            max_connection_time=max_connection_time, style=style, chatbot_url=chatbot_url,
            initial_prompt=initial_prompt  # Pass it to Client2
        )

        # Add vad_parameters to the client
        if vad_parameters is not None:
            self.client.vad_parameters = vad_parameters

        if save_output_recording and not output_recording_filename.endswith(".wav"):
            raise ValueError(f"Please provide a valid `output_recording_filename`: {output_recording_filename}")
        if not output_transcription_path.endswith(".srt"):
            raise ValueError(f"Please provide a valid `output_transcription_path`: {output_transcription_path}. The file extension should be `.srt`.")
        TranscriptionTeeClient.__init__(
            self,
            [self.client],
            save_output_recording=save_output_recording,
            output_recording_filename=output_recording_filename
        )
