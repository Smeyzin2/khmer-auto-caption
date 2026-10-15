
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
    layout="centered",
)

st.title("🎬 Khmer Auto Caption")
st.write("បង្កើតវីដេអូមានអក្សរខ្មែរ តាមពេលនិយាយ")

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
        rate = wav.getframerate()
        frames = wav.getnframes()
        data = wav.readframes(frames)

    samples = np.frombuffer(
        data, dtype=np.int16
    ).astype(np.float32)

    samples /= 32768.0

    return {
        "raw": samples,
        "sampling_rate": rate,
    }, frames / rate


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


def split_caption(text, max_chars=26):
    """បំបែកអត្ថបទវែងជាឃ្លាខ្លីៗ។"""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    words = text.split()
    result = []
    current = ""

    for word in words:
        candidate = word if not current else current + " " + word

        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                result.append(current)

            # កុំទុកពាក្យវែងពេកជាឃ្លាតែមួយ
            if len(word) > max_chars:
                for i in range(0, len(word), max_chars):
                    result.append(word[i:i + max_chars])
                current = ""
            else:
                current = word

    if current:
        result.append(current)

    return result


def split_interval(text, start, end):
    """ចែកពេលវេលារបស់ឃ្លាមួយទៅឃ្លាតូចៗ។"""
    pieces = split_caption(text)

    if not pieces:
        return []

    start = max(0.0, float(start))
    end = max(start + 0.25, float(end))

    weights = [max(1, len(piece)) for piece in pieces]
    total_weight = sum(weights)
    duration = end - start

    result = []
    cursor = start

    for i, piece in enumerate(pieces):
        piece_start = cursor

        if i == len(pieces) - 1:
            piece_end = end
        else:
            piece_end = cursor + duration * (
                weights[i] / total_weight
            )

        piece_end = max(piece_start + 0.15, piece_end)

        result.append((
            piece_start,
            piece_end,
            piece,
        ))
        cursor = piece_end

    return result


def make_timed_entries(chunks, transcript, duration):
    """
    ប្រើ timestamps ពី AI ប្រសិនបើមាន។
    បើមិនមាន ឬមិនត្រឹមត្រូវ ចែកអត្ថបទតាមរយៈពេលវីដេអូ។
    """
    entries = []

    for chunk in chunks:
        text = (chunk.get("text") or "").strip()
        stamp = chunk.get("timestamp")

        if not text or not stamp or len(stamp) < 2:
            continue

        start, end = stamp[0], stamp[1]

        if start is None or end is None:
            continue

        try:
            start = float(start)
            end = float(end)
        except (TypeError, ValueError):
            continue

        if start < 0 or end <= start:
            continue

        start = min(start, duration)
        end = min(end, duration)

        if end <= start:
            continue

        entries.extend(split_interval(text, start, end))

    # បើ AI មិនផ្ដល់ពេលវេលាល្អ ត្រូវចែកអត្ថបទទាំងមូល
    # ជាឃ្លាខ្លីៗ ហើយចែកពេលតាមប្រវែងអត្ថបទ។
    if not entries:
        entries = split_interval(
            transcript, 0.0, max(duration, 1.0)
        )

    entries.sort(key=lambda item: item[0])

    # កែពេលវេលាដែលត្រួតគ្នា ដើម្បីកុំឱ្យឃ្លាច្រើន
    # បង្ហាញលើអេក្រង់ក្នុងពេលតែមួយ។
    fixed = []

    for start, end, text in entries:
        if fixed:
            previous_start, previous_end, previous_text = fixed[-1]

            if start < previous_end:
                fixed[-1] = (
                    previous_start,
                    max(previous_start + 0.15, start),
                    previous_text,
                )

        if end > start:
            fixed.append((start, end, text))

    return [
        item for item in fixed
        if item[1] > item[0] and item[2].strip()
    ]


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
    video_bytes = uploaded.getvalue()
    st.video(video_bytes)

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
            font_path = os.path.join(folder, font["file"])

            with open(source, "wb") as f:
                f.write(video_bytes)

            try:
                with st.spinner("កំពុងទាញយក Font..."):
                    request = urllib.request.Request(
                        font["url"],
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                    with urllib.request.urlopen(
                        request, timeout=30
                    ) as response:
                        font_data = response.read()

                    if len(font_data) < 1000:
                        raise RuntimeError(
                            "ឯកសារ Font មិនត្រឹមត្រូវទេ។"
                        )

                    with open(font_path, "wb") as f:
                        f.write(font_data)

                with st.spinner("កំពុងបំបែកសំឡេង..."):
                    extract_audio(source, audio_path)
                    audio, duration = read_audio(audio_path)

                with st.spinner(
                    "AI កំពុងស្គាល់សំឡេងខ្មែរ..."
                ):
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

                transcript = (
                    result.get("text") or ""
                ).strip()
                chunks = result.get("chunks") or []

                if not transcript:
                    st.error(
                        "AI មិនអាចស្គាល់សំឡេងបានទេ។"
                    )
                    st.stop()

                entries = make_timed_entries(
                    chunks, transcript, duration
                )

                if not entries:
                    st.error(
                        "មិនអាចបង្កើតពេលវេលាអក្សរបានទេ។"
                    )
                    st.stop()

                srt_lines = []

                for index, (start, end, text) in enumerate(
                    entries, start=1
                ):
                    srt_lines.extend([
                        str(index),
                        f"{srt_time(start)} --> {srt_time(end)}",
                        text,
                        "",
                    ])

                with open(
                    srt_path, "w", encoding="utf-8-sig"
                ) as f:
                    f.write("\n".join(srt_lines))

                with st.expander("ពិនិត្យពេលវេលាអក្សរ"):
                    st.write(
                        f"ចំនួនឃ្លាអក្សរ៖ {len(entries)}"
                    )
                    st.code(
                        "\n".join(
                            f"{srt_time(a)} - {srt_time(b)}  {t}"
                            for a, b, t in entries[:30]
                        )
                    )

                with st.spinner(
                    "កំពុងដាក់អក្សរលើវីដេអូ..."
                ):
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
                    output_data = f.read()

                st.success("បង្កើតវីដេអូរួចរាល់!")
                st.subheader("មើលវីដេអូដែលបានដាក់អក្សរ")
                st.video(output_data)

                st.download_button(
                    "⬇️ ទាញយក MP4",
                    data=output_data,
                    file_name="khmer_subtitle.mp4",
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True,
                )

                with st.expander("មើលអត្ថបទដែល AI ស្គាល់"):
                    st.write(transcript)

            except Exception as e:
                st.error("មានបញ្ហាក្នុងការបង្កើតវីដេអូ។")
                st.code(str(e))

else:
    st.info("សូមជ្រើសរើសវីដេអូជាមុនសិន។")
