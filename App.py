
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
st.write("បម្លែងសំឡេងទៅជាអក្សរខ្មែរ")

MODEL_ID = "sengtha/whisper-base-khmer"

@st.cache_resource
def load_model():
    device = 0 if torch.cuda.is_available() else -1
    return pipeline(
        "automatic-speech-recognition",
        model=MODEL_ID,
        device=device
    )

def to_srt_time(seconds):
    ms = int(max(0, seconds) * 1000)
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms = ms % 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def extract_audio(source, destination):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg, "-y", "-i", source,
            "-vn", "-ac", "1", "-ar", "16000",
            destination
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True
    )

uploaded = st.file_uploader(
    "📁 ជ្រើសវីដេអូ ឬសំឡេង",
    type=["mp4", "mov", "mkv", "avi", "webm",
          "mp3", "wav", "m4a", "flac", "ogg"]
)

if uploaded is not None:
    st.success(f"បានបញ្ចូល៖ {uploaded.name}")

    if uploaded.type and uploaded.type.startswith("video/"):
        st.video(uploaded.getvalue())

    if st.button("បង្កើតអក្សរខ្មែរ", type="primary",
                 use_container_width=True):
        with tempfile.TemporaryDirectory() as folder:
            safe_name = Path(uploaded.name).name
            input_path = os.path.join(folder, safe_name)
            audio_path = os.path.join(folder, "audio.wav")

            with open(input_path, "wb") as file:
                file.write(uploaded.getvalue())

            try:
                if Path(safe_name).suffix.lower() in [
                    ".mp4", ".mov", ".mkv", ".avi", ".webm"
                ]:
                    with st.spinner("កំពុងរៀបចំសំឡេង..."):
                        extract_audio(input_path, audio_path)
                else:
                    audio_path = input_path

                with st.spinner(
                    "AI កំពុងស្ដាប់សំឡេង... "
                    "ការប្រើលើកដំបូងអាចចំណាយពេល"
                ):
                    recognizer = load_model()
                    result = recognizer(
                        audio_path,
                        return_timestamps=True,
                        chunk_length_s=25
                    )

                transcript = result.get("text", "").strip()
                chunks = result.get("chunks") or []

                if not transcript:
                    st.warning("មិនអាចស្គាល់សំឡេងបានទេ។")
                else:
                    st.success("បង្កើតអត្ថបទបានហើយ!")
                    st.text_area(
                        "អត្ថបទខ្មែរ",
                        transcript,
                        height=220
                    )

                    srt = []
                    for i, chunk in enumerate(chunks, 1):
                        caption = chunk.get("text", "").strip()
                        times = chunk.get("timestamp") or (0, None)
                        start = times[0] or 0
                        end = times[1]
                        if not caption:
                            continue
                        if end is None:
                            end = start + 3
                        srt.extend([
                            str(i),
                            f"{to_srt_time(start)} --> "
                            f"{to_srt_time(end)}",
                            caption,
                            ""
                        ])

                    if not srt:
                        srt = [
                            "1",
                            "00:00:00,000 --> 00:00:10,000",
                            transcript,
                            ""
                        ]

                    st.download_button(
                        "⬇️ ទាញយក Subtitle (.srt)",
                        "\n".join(srt),
                        file_name="khmer_subtitles.srt",
                        mime="text/plain",
                        use_container_width=True
                    )

                    st.download_button(
                        "⬇️ ទាញយកអត្ថបទ (.txt)",
                        transcript,
                        file_name="khmer_transcript.txt",
                        mime="text/plain",
                        use_container_width=True
                    )

            except Exception as error:
                st.error("កម្មវិធីមានបញ្ហាពេលដំណើរការ។")
                st.code(str(error))

else:
    st.info("សូមជ្រើសវីដេអូ ឬឯកសារសំឡេងជាមុនសិន។")
