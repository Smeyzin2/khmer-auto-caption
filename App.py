
import os
import tempfile
import subprocess
from pathlib import Path

import streamlit as st
import imageio_ffmpeg
import torch
from transformers import pipeline

st.set_page_config(
    page_title="Khmer Auto Caption",
    page_icon="🎬",
    layout="centered"
)

st.title("🎬 Khmer Auto Caption")
st.write("បម្លែងសំឡេងក្នុងវីដេអូទៅជាអក្សរខ្មែរ និងបង្កើត Subtitle")

MODEL_ID = "sengtha/whisper-base-khmer"


@st.cache_resource
def load_model():
    device = 0 if torch.cuda.is_available() else -1
    return pipeline(
        "automatic-speech-recognition",
        model=MODEL_ID,
        device=device
    )


def timestamp(seconds):
    ms = int(max(0, seconds) * 1000)
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds_part = (ms % 60000) // 1000
    millis = ms % 1000
    return (
        f"{hours:02}:{minutes:02}:"
        f"{seconds_part:02},{millis:03}"
    )


def extract_audio(input_path, output_path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg, "-y", "-i", input_path,
            "-vn", "-ac", "1", "-ar", "16000",
            "-acodec", "pcm_s16le", output_path
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )


uploaded = st.file_uploader(
    "ជ្រើសរើសវីដេអូ ឬឯកសារសំឡេង",
    type=[
        "mp4", "mov", "mkv", "avi", "webm",
        "mp3", "wav", "m4a", "flac", "ogg"
    ]
)

if uploaded:
    st.video(uploaded) if uploaded.type and uploaded.type.startswith("video/") else None

    if st.button("បង្កើតអក្សរខ្មែរ", type="primary"):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, uploaded.name)
            audio_path = os.path.join(temp_dir, "audio.wav")

            with open(input_path, "wb") as f:
                f.write(uploaded.getvalue())

            try:
                with st.spinner("កំពុងរៀបចំសំឡេង..."):
                    suffix = Path(uploaded.name).suffix.lower()

                    if suffix in {
                        ".mp4", ".mov", ".mkv", ".avi", ".webm"
                    }:
                        extract_audio(input_path, audio_path)
                    else:
                        audio_path = input_path

                with st.spinner(
                    "AI កំពុងស្ដាប់សំឡេង និងបង្កើតអក្សរ... "
                    "សូមរង់ចាំ។"
                ):
                    recognizer = load_model()
                    result = recognizer(
                        audio_path,
                        return_timestamps=True,
                        chunk_length_s=25,
                        stride_length_s=5
                    )

                chunks = result.get("chunks") or []
                text = result.get("text", "").strip()

                srt_lines = []
                plain_lines = []

                for index, chunk in enumerate(chunks, start=1):
                    caption = chunk.get("text", "").strip()
                    times = chunk.get("timestamp") or (None, None)

                    start = times[0]
                    end = times[1]

                    if not caption:
                        continue

                    plain_lines.append(caption)

                    if start is None:
                        start = 0
                    if end is None:
                        end = start + 3

                    srt_lines.extend([
                        str(index),
                        f"{timestamp(start)} --> {timestamp(end)}",
                        caption,
                        ""
                    ])

                if not plain_lines and text:
                    plain_lines = [text]
                    srt_lines = [
                        "1",
                        "00:00:00,000 --> 00:00:10,000",
                        text,
                        ""
                    ]

                if not text:
                    st.warning(
                        "មិនអាចស្គាល់សំឡេងបានទេ។ "
                        "សូមសាកល្បងឯកសារផ្សេង។"
                    )
                else:
                    st.success("បង្កើតអក្សរបានហើយ!")

                    st.subheader("អត្ថបទដែលស្គាល់បាន")
                    st.text_area(
                        "អត្ថបទ",
                        value="\n".join(plain_lines) or text,
                        height=220
                    )

                    st.download_button(
                        "⬇️ ទាញយក Subtitle (.srt)",
                        data="\n".join(srt_lines),
                        file_name="khmer_subtitles.srt",
                        mime="text/plain"
                    )

                    st.download_button(
                        "⬇️ ទាញយកអត្ថបទ (.txt)",
                        data="\n".join(plain_lines) or text,
                        file_name="khmer_transcript.txt",
                        mime="text/plain"
                    )

            except Exception as error:
                st.error("កម្មវិធីមិនអាចដំណើរការឯកសារនេះបានទេ។")
                st.code(str(error))
                st.info(
                    "សូមពិនិត្យ Logs ប្រសិនបើបញ្ហានៅតែបន្ត។"
                )
else:
    st.info("សូមបញ្ចូលវីដេអូ ឬសំឡេងជាមុនសិន។")

st.caption("Khmer Auto Caption · AI Speech Recognition")
