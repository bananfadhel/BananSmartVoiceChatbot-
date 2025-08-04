import cohere
from elevenlabs import ElevenLabs, play
from RealtimeSTT import AudioToTextRecorder
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import base64
import io
import os

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

class VoiceChatbot:
    def __init__(self):
        self.cohere = cohere.Client("nhh1rhpwchYSx0t8aZGHCEZlYWlSkpLFPk8oHp3W")  # Replace with your actual Cohere API key
        self.elevenlabs = ElevenLabs(api_key="sk_fbfeac9c967e1cd58908f9e8bb402bd3f31ebe44ca060cb2")  # Replace with your actual ElevenLabs API key

    def speak(self, text):
        try:
            audio = self.elevenlabs.text_to_speech.convert(voice_id="rPNcQ53R703tTmtue1AT",text=text,model_id="eleven_turbo_v2_5")
            play(b"".join(audio))
        except Exception as e:
            print(f"Speech error: {e}")
    
    def generate_audio(self, text):
        try:
            audio = self.elevenlabs.text_to_speech.convert(voice_id="rPNcQ53R703tTmtue1AT",text=text,model_id="eleven_turbo_v2_5")
            audio_bytes = b"".join(audio)
            return base64.b64encode(audio_bytes).decode('utf-8')
        except Exception as e:
            print(f"Audio generation error: {e}")
            return None

    def think(self, text):
        response = self.cohere.chat(model="command-r7b-arabic-02-2025",message=text,temperature=0.7,max_tokens=200, preamble="جاوب بلهجة سعودية فقط، جاوب بشكل مختصر، اسمك هو المساعد الذكي وقد صممتك بنان فاضل")
        return response.text

    def listen(self):
        try:
            with AudioToTextRecorder(language="ar", sample_rate=16000) as recorder:
                while True:
                    text = recorder.text()
                    if text:
                        print(f"You: {text}")
                        response = self.think(text)
                        print(f"Bot: {response}")
                        self.speak(response)
        except KeyboardInterrupt:
            print("\nExiting chatbot...")
        except Exception as e:
            print(f"Error: {e}")

# Initialize chatbot instance
chatbot = VoiceChatbot()

# ---------------- RealtimeSTT Integration ----------------
import asyncio, threading, json, numpy as np
from scipy.signal import resample

recorder_ready = threading.Event()
is_running = True

# callback from recorder when partial text stabilises
async def _emit_realtime(text):
    emit('realtime', {'text': text})

def on_realtime(text):
    # schedule emit in SocketIO thread
    socketio.start_background_task(_emit_realtime_sync, text)

def _emit_realtime_sync(text):
    socketio.emit('realtime', {'text': text})

def create_recorder():
    config = {
        'spinner': False,
        'use_microphone': False,
        'model': 'base',
        'language': 'ar',
        'silero_sensitivity': 0.4,
        'webrtc_sensitivity': 2,
        'post_speech_silence_duration': 0.7,
        'min_length_of_recording': 0,
        'min_gap_between_recordings': 0,
        'enable_realtime_transcription': True,
        'realtime_processing_pause': 0.8,

        'realtime_model_type': 'base',
        'on_realtime_transcription_stabilized': on_realtime,
    }
    return AudioToTextRecorder(**config)

recorder = None

def recorder_loop():
    global recorder, is_running
    recorder = create_recorder()
    recorder_ready.set()
    while is_running:
        try:
            sentence = recorder.text()
            if sentence:
                socketio.emit('fullSentence', {'text': sentence})
        except Exception as e:
            print('Recorder error', e)

@socketio.on('connect')
def handle_connect():
    print('Web client connected')

@socketio.on('audio_chunk')
def handle_audio(data):
    # data: binary bytes (metadataLen + metadata + pcm16)
    if not recorder_ready.is_set():
        return
    try:
        metadata_length = int.from_bytes(data[:4], 'little')
        metadata_json = data[4:4+metadata_length].decode('utf-8')
        meta = json.loads(me