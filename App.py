
import os
import subprocess
import tempfile
import wave
import urllib.request

import imageio_ffmpeg
import numpy as np
import streamlit as st
import torch
from transformers import pipeline

st.set_page_config(
    page_title="Khmer Auto Caption",
    page_icon="🎬"
)

st.title("🎬 Khmer Auto Caption")
st.write("បង្កើតវីដេអូ MP4 មានអក្សរខ្មែរ")

MODEL = "sengtha/whisper-base-khmer"


FONT_URL = "https://raw.githubusercontent.com/notofonts/khmer/main/fonts/NotoSansKhmer/hinted/ttf/NotoSansKhmer-Regular.ttf"



@st.cache_resource
def load_model():
    return pipeline(
        "automatic-speech-recognition",
        model=MODEL,
        device=-1,
    )


def run_ffmpeg(args):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    return subprocess.run(
        [exe, "-y"] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def extract_audio(video_path, audio_path):
    run_ffmpeg([
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-acodec", "pcm_s16le",
        audio_path,
    ])


def read_audio(path):
    with wave.open(path, "rb") as wav:
        channels = wav.getnchannels()
        rate = wav.getframerate()
        data = wav.readframes(wav.getnframes())

    samples = np.frombuffer(
        data, dtype=np.int16
    ).astype(np.float32)

    samples /= 32768.0

    if channels > 1:
        samples = samples.reshape(
            -1, channels
        ).mean(axis=1)

    return {
        "raw": samples,
        "sampling_rate": rate,
    }


def srt_time(seconds):
    ms = int(max(0, seconds) * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)

    return (
        f"{hours:02}:{minutes:02}:"
        f"{seconds:02},{ms:03}"
    )


def escape_path(path):
    return (
        os.path.abspath(path)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


uploaded = st.file_uploader(
    "ជ្រើសរើសវីដេអូរបស់អ្នក",
    type=["mp4", "mov", "mkv", "avi", "webm"],
)

if uploaded:
    st.video(uploaded.getvalue())

    if st.button(
        "បង្កើតវីដេអូមានអក្សរខ្មែរ",
        type="primary",
        use_container_width=True,
    ):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "input.mp4")
            audio_path = os.path.join(folder, "audio.wav")
            srt_path = os.path.join(folder, "khmer.srt")
            output_path = os.path.join(
                folder, "khmer_subtitle.mp4"
            )
            font_path = os.path.join(
                folder, "NotoSansKhmer-Regular.ttf"
            )

            with open(source, "wb") as f:
                f.write(uploaded.getvalue())

            try:
                with st.spinner("កំពុងទាញយកពុម្ពអក្សរខ្មែរ..."):
                    urllib.request.urlretrieve(
                        FONT_URL, font_path
                    )

                with st.spinner("កំពុងបំបែកសំឡេងពីវីដេអូ..."):
                    extract_audio(source, audio_path)
                    audio = read_audio(audio_path)

                with st.spinner("AI កំពុងស្គាល់សំឡេង..."):
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

                entries = []

                for chunk in chunks:
                    text = chunk.get("text", "").strip()
                    stamps = chunk.get("timestamp") or (0, None)

                    start = stamps[0] or 0
                    end = stamps[1]

                    if text:
                        if end is None:
                            end = start + 3

                        entries.append((
                            start,
                            max(start + 0.1, end),
                            text,
                        ))

                if not entries:
                    entries = [(0, 10, transcript)]

                lines = []

                for i, (start, end, text) in enumerate(
                    entries, 1
                ):
                    lines.extend([
                        str(i),
                        f"{srt_time(start)} --> {srt_time(end)}",
                        text,
                        "",
                    ])

                with open(
                    srt_path, "w", encoding="utf-8-sig"
                ) as f:
                    f.write("\n".join(lines))

                with st.spinner("កំពុងដាក់អក្សរខ្មែរលើវីដេអូ..."):
                    subtitles = escape_path(srt_path)
                    fontsdir = escape_path(folder)

                    vf = (
                        f"subtitles=filename='{subtitles}'"
                        f":fontsdir='{fontsdir}'"
                        ":force_style='FontName=Noto Sans Khmer,"
                        "FontSize=22,Outline=2,Shadow=1,Alignment=2'"
                    )

                    run_ffmpeg([
                        "-i", source,
                        "-vf", vf,
                        "-c:v", "libx264",
                        "-preset", "ultrafast",
                        "-crf", "23",
                        "-c:a", "aac",
                        "-movflags", "+faststart",
                        output_path,
                    ])

                with open(output_path, "rb") as f:
                    video_data = f.read()

                st.success("បង្កើតវីដេអូរួចរាល់!")

                st.download_button(
                    "⬇️ ទាញយកវីដេអូ MP4 មានអក្សរខ្មែរ",
                    data=video_data,
                    file_name="khmer_subtitle.mp4",
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True,
                )

            except Exception as e:
                st.error("មានបញ្ហាក្នុងការបង្កើតវីដេអូ។")
                st.code(str(e))

else:
    st.info("សូមជ្រើសរើសវីដេអូជាមុនសិន។")
