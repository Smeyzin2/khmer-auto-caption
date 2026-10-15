
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import streamlit as st
import torch
from transformers import pipeline

st.set_page_config(page_title="Khmer Auto Caption", page_icon="🎬")
st.title("🎬 Khmer Auto Caption")
st.write("បម្លែងសំឡេងទៅជាអក្សរខ្មែរ")

@st.cache_resource
def load_model():
    return pipeline(
        "automatic-speech-recognition",
        model="sengtha/whisper-base-khmer",
        device=-1,
    )

def to_srt_time(seconds):
    ms = int(max(0, seconds) * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def extract_audio(source, output):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg, "-y", "-i", source, "-vn",
         "-ac", "1", "-ar", "16000",
         "-acodec", "pcm_s16le", output],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

def read_audio(path):
    with wave.open(path, "rb") as wav:
        channels = wav.getnchannels()
        rate = wav.getframerate()
        width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())

    if width != 2:
        raise ValueError("សំឡេងមិនមែនជា WAV 16-bit PCM ទេ")

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    return {"raw": audio, "sampling_rate": rate}

uploaded = st.file_uploader(
    "ជ្រើសរើសវីដេអូ ឬសំឡេង",
    type=["mp4", "mov", "mkv", "avi", "webm",
          "mp3", "wav", "m4a", "flac", "ogg"],
)

if uploaded:
    st.success(f"បានជ្រើសរើស៖ {uploaded.name}")

    if uploaded.type and uploaded.type.startswith("video/"):
        st.video(uploaded.getvalue())

    if st.button("បង្កើតអក្សរខ្មែរ", type="primary",
                 use_container_width=True):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, Path(uploaded.name).name)
            audio_path = os.path.join(folder, "audio.wav")

            with open(source, "wb") as f:
                f.write(uploaded.getvalue())

            try:
                with st.spinner("កំពុងរៀបចំសំឡេង..."):
                    extract_audio(source, audio_path)
                    audio_data = read_audio(audio_path)

                with st.spinner("AI កំពុងស្ដាប់សំឡេង..."):
                    model = load_model()
                    result = model(
                        audio_data,
                        return_timestamps=True,
                        chunk_length_s=25,
                    )

                transcript = result.get("text", "").strip()
                chunks = result.get("chunks") or []

                if not transcript:
                    st.warning("មិនអាចស្គាល់សំឡេងបានទេ។")
                else:
                    st.success("បានបង្កើតអត្ថបទ!")
                    st.text_area("អត្ថបទខ្មែរ", transcript, height=220)

                    lines = []
                    for i, chunk in enumerate(chunks, 1):
                        text = chunk.get("text", "").strip()
                        stamp = chunk.get("timestamp") or (0, None)
                        start = stamp[0] or 0
                        end = stamp[1] if stamp[1] is not None else start + 3

                        if text:
                            lines.extend([
                                str(i),
                                f"{to_srt_time(start)} --> {to_srt_time(end)}",
                                text,
                                "",
                            ])

                    if not lines:
                        lines = [
                            "1",
                            "00:00:00,000 --> 00:00:10,000",
                            transcript,
                            "",
                        ]

                    st.download_button(
                        "ទាញយក Subtitle (.srt)",
                        "\n".join(lines),
                        file_name="khmer_subtitles.srt",
                        mime="text/plain",
                        use_container_width=True,
                    )
                    st.download_button(
                        "ទាញយកអត្ថបទ (.txt)",
                        transcript,
                        file_name="khmer_transcript.txt",
                        mime="text/plain",
                        use_container_width=True,
                    )

            except Exception as e:
                st.error("កម្មវិធីមានបញ្ហា៖")
                st.code(str(e))
else:
    st.info("សូមជ្រើសរើសវីដេអូ ឬសំឡេងជាមុនសិន។")
