
import os
import re
import subprocess
import tempfile
import wave
import urllib.request

import imageio_ffmpeg
import numpy as np
import streamlit as st
from transformers import pipeline

st.set_page_config(
    page_title="Khmer Auto Caption",
    page_icon="🎬",
)

st.title("🎬 Khmer Auto Caption")
st.write("បង្កើតវីដេអូមានអក្សរខ្មែរ និងជ្រើសរើស Font")

MODEL = "openai/whisper-small"

FONTS = {
    "Noto Sans Khmer — ច្បាស់ងាយអាន": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskhmer/NotoSansKhmer%5Bwdth%2Cwght%5D.ttf",
        "file": "NotoSansKhmer.ttf",
        "name": "Noto Sans Khmer",
    },
    "Noto Serif Khmer — បែបបុរាណ": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifkhmer/NotoSerifKhmer%5Bwdth%2Cwght%5D.ttf",
        "file": "NotoSerifKhmer.ttf",
        "name": "Noto Serif Khmer",
    },
    "Battambang — ទន់ភ្នែក": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/battambang/Battambang-Regular.ttf",
        "file": "Battambang.ttf",
        "name": "Battambang",
    },
    "Moul — សម្រាប់ចំណងជើង": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/moul/Moul-Regular.ttf",
        "file": "Moul.ttf",
        "name": "Moul",
    },
    "Kantumruy Pro — បែបទំនើប": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/kantumruypro/KantumruyPro%5Bwght%5D.ttf",
        "file": "KantumruyPro.ttf",
        "name": "Kantumruy Pro",
    },
    "Khmer — ស្ទីលសាមញ្ញ": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/khmer/Khmer.ttf",
        "file": "Khmer.ttf",
        "name": "Khmer",
    },
}


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


def wrap_caption(text, max_chars=28):
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = (
            word if not current
            else current + " " + word
        )

        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return "\n".join(lines)


st.subheader("🎨 កំណត់រចនាប័ទ្មអក្សរ")

font_choice = st.selectbox(
    "ជ្រើសរើស Font ខ្មែរ",
    list(FONTS.keys()),
)

font_size = st.slider(
    "ទំហំអក្សរ",
    min_value=16,
    max_value=36,
    value=24,
)

outline_size = st.slider(
    "កម្រាស់គែមអក្សរ",
    min_value=1,
    max_value=5,
    value=2,
)

font_color = st.selectbox(
    "ពណ៌អក្សរ",
    ["ស", "លឿង", "បៃតង", "ខៀវ"],
)

color_codes = {
    "ស": "&H00FFFFFF",
    "លឿង": "&H0000FFFF",
    "បៃតង": "&H0000FF00",
    "ខៀវ": "&H00FF0000",
}

uploaded = st.file_uploader(
    "ជ្រើសរើសវីដេអូ",
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
            font = FONTS[font_choice]
            font_path = os.path.join(
                folder, font["file"]
            )

            with open(source, "wb") as f:
                f.write(uploaded.getvalue())

            try:
                with st.spinner("កំពុងទាញយក Font..."):
                    urllib.request.urlretrieve(
                        font["url"], font_path
                    )

                with st.spinner("កំពុងបំបែកសំឡេង..."):
                    extract_audio(source, audio_path)
                    audio = read_audio(audio_path)

                with st.spinner("AI កំពុងស្គាល់សំឡេងខ្មែរ..."):
                    model = load_model()
                    result = model(
                        audio,
                        return_timestamps=True,
                        chunk_length_s=15,
                        generate_kwargs={
                            "language": "khmer",
                            "task": "transcribe",
                        },
                    )

                transcript = result.get(
                    "text", ""
                ).strip()
                chunks = result.get("chunks") or []

                if not transcript:
                    st.error("មិនអាចស្គាល់សំឡេងបានទេ។")
                    st.stop()

                entries = []

                for chunk in chunks:
                    text = chunk.get("text", "").strip()
                    stamps = chunk.get("timestamp") or (0, None)

                    start = stamps[0]
                    end = stamps[1]

                    if start is None:
                        start = 0
                    if end is None:
                        end = start + 3

                    if text:
                        entries.append((
                            float(start),
                            max(float(start) + 0.2, float(end)),
                            text,
                        ))

                if not entries:
                    entries = [(0.0, 10.0, transcript)]

                lines = []

                for i, (start, end, text) in enumerate(
                    entries, 1
                ):
                    lines.extend([
                        str(i),
                        f"{srt_time(start)} --> {srt_time(end)}",
                        wrap_caption(text),
                        "",
                    ])

                with open(
                    srt_path, "w", encoding="utf-8-sig"
                ) as f:
                    f.write("\n".join(lines))

                with st.spinner("កំពុងដាក់អក្សរលើវីដេអូ..."):
                    subtitles = escape_path(srt_path)
                    fontsdir = escape_path(folder)

                    vf = (
                        f"subtitles=filename='{subtitles}'"
                        f":fontsdir='{fontsdir}'"
                        f":force_style='FontName={font['name']},"
                        f"FontSize={font_size},"
                        f"PrimaryColour={color_codes[font_color]},"
                        f"Outline={outline_size},"
                        "OutlineColour=&H00000000,"
                        "Shadow=1,Alignment=2,MarginV=35'"
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
                st.subheader("មើលវីដេអូជាគំរូ")
                st.video(video_data)

                st.download_button(
                    "⬇️ ទាញយក MP4",
                    data=video_data,
                    file_name="khmer_subtitle.mp4",
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True,
                )

                with st.expander("មើលអត្ថបទដែល AI ស្គាល់"):
                    st.write(transcript)

            except Exception as e:
                st.error(
                    "មានបញ្ហាក្នុងការបង្កើតវីដេអូ។"
                )
                st.code(str(e))

else:
    st.info("សូមជ្រើសរើសវីដេអូជាមុនសិន។")
