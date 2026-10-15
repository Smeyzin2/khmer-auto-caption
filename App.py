import os
import subprocess
import tempfile
from pathlib import Path

import streamlit as st
import imageio_ffmpeg
import torch
from transformers import pipeline

st.set_page_config(page_title="Khmer Auto Caption", page_icon="🎬")
st.title("🎬 Khmer Auto Caption")
st.write("បម្លែងសំឡេងក្នុងវីដេអូទៅជាអក្សរខ្មែរ")

@st.cache_resource
def load_model():
    return pipeline(
        "automatic-speech-recognition",
        model="sengtha/whisper-base-khmer",
        device=0 if torch.cuda.is_available() else -1,
    )

def time_srt(seconds):
    ms = int(max(0, seconds) * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

uploaded = st.file_uploader(
    "ជ្រើសរើសវីដេអូ ឬសំឡេង",
    type=["mp4", "mov", "mkv", "avi", "webm",
          "mp3", "wav", "m4a", "flac", "ogg"],
)

if uploaded:
    st.success(f"បានជ្រើស៖ {uploaded.name}")
    if uploaded.type and uploaded.type.startswith("video/"):
        st.video(uploaded.getvalue())

    if st.button("បង្កើតអក្សរខ្មែរ", type="primary"):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, Path(uploaded.name).name)
            audio = os.path.join(folder, "audio.wav")

            with open(source, "wb") as f:
                f.write(uploaded.getvalue())

            try:
                if Path(source).suffix.lower() in [
                    ".mp4", ".mov", ".mkv", ".avi", ".webm"
                ]:
                    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
                    subprocess.run(
                        [ffmpeg, "-y", "-i", source, "-vn",
                         "-ac", "1", "-ar", "16000", audio],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                else:
                    audio = source

                with st.spinner("កំពុងស្ដាប់សំឡេង និងបង្កើតអក្សរ..."):
                    model = load_model()
                    result = model(
                        audio,
                        return_timestamps=True,
                        chunk_length_s=25,
                    )

                transcript = result.get("text", "").strip()
                chunks = result.get("chunks", [])

                if not transcript:
                    st.warning("មិនអាចស្គាល់សំឡេងបានទេ។")
                else:
                    st.text_area("អត្ថបទដែលបានស្គាល់", transcript, height=220)

                    lines = []
                    for i, chunk in enumerate(chunks, 1):
                        text = chunk.get("text", "").strip()
                        stamp = chunk.get("timestamp") or (0, None)
                        start = stamp[0] or 0
                        end = stamp[1] if stamp[1] is not None else start + 3
                        if text:
                            lines.extend([
                                str(i),
                                f"{time_srt(start)} --> {time_srt(end)}",
                                text,
                                "",
                            ])

                    if not lines:
                        lines = ["1", "00:00:00,000 --> 00:00:10,000",
                                 transcript, ""]

                    st.download_button(
                        "ទាញយក Subtitle (.srt)",
                        "\n".join(lines),
                        file_name="khmer_subtitles.srt",
                        mime="text/plain",
                    )
                    st.download_button(
                        "ទាញយកអត្ថបទ (.txt)",
                        transcript,
                        file_name="khmer_transcript.txt",
                        mime="text/plain",
                    )

            except Exception as e:
                st.error("មានបញ្ហាពេលដំណើរការ៖")
                st.code(str(e))
else:
    st.info("សូមជ្រើសរើសវីដេអូ ឬឯកសារសំឡេងជាមុន។")
