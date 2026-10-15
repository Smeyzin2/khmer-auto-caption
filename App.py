
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
st.write("បង្កើត Subtitle ខ្មែរ និងទាញយកវីដេអូមានអក្សរខ្មែរ")

@st.cache_resource
def load_model():
    return pipeline(
        "automatic-speech-recognition",
        model="sengtha/whisper-base-khmer",
        device=-1,
    )

def srt_time(seconds):
    ms = int(max(0, seconds) * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def run_ffmpeg(args):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    return subprocess.run(
        [ffmpeg, "-y"] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

def extract_audio(source, destination):
    run_ffmpeg([
        "-i", source, "-vn", "-ac", "1", "-ar", "16000",
        "-acodec", "pcm_s16le", destination
    ])

def read_audio(path):
    with wave.open(path, "rb") as wav:
        channels = wav.getnchannels()
        rate = wav.getframerate()
        width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())

    if width != 2:
        raise ValueError("ទម្រង់សំឡេងមិនត្រឹមត្រូវ")

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    return {"raw": audio, "sampling_rate": rate}

uploaded = st.file_uploader(
    "ជ្រើសរើសវីដេអូ",
    type=["mp4", "mov", "mkv", "avi", "webm"],
)

if uploaded:
    st.video(uploaded.getvalue())

    if st.button("បង្កើត Subtitle ខ្មែរ", type="primary",
                 use_container_width=True):
        with tempfile.TemporaryDirectory() as folder:
            video_path = os.path.join(folder, "input.mp4")
            audio_path = os.path.join(folder, "audio.wav")
            srt_path = os.path.join(folder, "khmer.srt")
            output_path = os.path.join(folder, "khmer_subtitle_video.mp4")

            with open(video_path, "wb") as f:
                f.write(uploaded.getvalue())

            try:
                with st.spinner("កំពុងបម្លែងសំឡេង..."):
                    extract_audio(video_path, audio_path)
                    audio = read_audio(audio_path)

                with st.spinner("AI កំពុងស្ដាប់សំឡេង..."):
                    model = load_model()
                    result = model(
                        audio,
                        return_timestamps=True,
                        chunk_length_s=25,
                    )

                transcript = result.get("text", "").strip()
                chunks = result.get("chunks") or []

                if not transcript:
                    st.error("មិនអាចស្គាល់សំឡេងបានទេ។")
                    st.stop()

                lines = []
                for i, chunk in enumerate(chunks, 1):
                    text = chunk.get("text", "").strip()
                    times = chunk.get("timestamp") or (0, None)
                    start = times[0] or 0
                    end = times[1] if times[1] is not None else start + 3
                    if text:
                        lines.extend([
                            str(i),
                            f"{srt_time(start)} --> {srt_time(end)}",
                            text,
                            "",
                        ])

                if not lines:
                    lines = [
                        "1", "00:00:00,000 --> 00:00:10,000",
                        transcript, ""
                    ]

                with open(srt_path, "w", encoding="utf-8-sig") as f:
                    f.write("\n".join(lines))

                st.success("បានបង្កើត Subtitle ខ្មែរ!")
                st.text_area("អត្ថបទខ្មែរ", transcript, height=180)

                st.download_button(
                    "ទាញយក Subtitle (.srt)",
                    "\n".join(lines),
                    file_name="khmer_subtitles.srt",
                    mime="text/plain",
                    use_container_width=True,
                )

                with st.spinner("កំពុងបង្កប់ Subtitle ក្នុងវីដេអូ..."):
                    # Use a subtitle filter that supports Khmer Unicode.
                    escaped = srt_path.replace("\\", "/").replace(":", "\\:")
                    run_ffmpeg([
                        "-i", video_path,
                        "-vf", f"subtitles='{escaped}':charenc=UTF-8",
                        "-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "23", "-c:a", "aac",
                        "-movflags", "+faststart",
                        output_path,
                    ])

                with open(output_path, "rb") as f:
                    video_bytes = f.read()

                st.success("វីដេអូមាន Subtitle រួចរាល់!")
                st.video(video_bytes)
                st.download_button(
                    "⬇️ ទាញយកវីដេអូ MP4 មាន Subtitle ខ្មែរ",
                    video_bytes,
                    file_name="khmer_subtitle_video.mp4",
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True,
                )

            except Exception as e:
                st.error("កម្មវិធីមានបញ្ហា៖")
                st.code(str(e))
else:
    st.info("សូមជ្រើសរើសវីដេអូ MP4 ជាមុនសិន។")
