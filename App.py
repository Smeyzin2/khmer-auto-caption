
import os
import re
import subprocess
import tempfile
import urllib.request

import imageio_ffmpeg
import streamlit as st
from google import genai

st.set_page_config(
    page_title="Khmer Auto Caption",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 Khmer Auto Caption")
st.write("បង្កើតវីដេអូមានអក្សរខ្មែរតាមពេលដោយ Gemini AI")

MODEL = "gemini-3.5-transcribe"

FONTS = {
    "Noto Sans Khmer": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskhmer/NotoSansKhmer%5Bwdth%2Cwght%5D.ttf",
        "file": "NotoSansKhmer.ttf",
        "name": "Noto Sans Khmer",
    },
    "Noto Serif Khmer": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifkhmer/NotoSerifKhmer%5Bwdth%2Cwght%5D.ttf",
        "file": "NotoSerifKhmer.ttf",
        "name": "Noto Serif Khmer",
    },
    "Battambang": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/battambang/Battambang-Regular.ttf",
        "file": "Battambang.ttf",
        "name": "Battambang",
    },
    "Moul": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/moul/Moul-Regular.ttf",
        "file": "Moul.ttf",
        "name": "Moul",
    },
    "Kantumruy Pro": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/kantumruypro/KantumruyPro%5Bwght%5D.ttf",
        "file": "KantumruyPro.ttf",
        "name": "Kantumruy Pro",
    },
    "Khmer": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/khmer/Khmer.ttf",
        "file": "Khmer.ttf",
        "name": "Khmer",
    },
}


def run_ffmpeg(args):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    return subprocess.run(
        [exe, "-y"] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
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


def srt_time(seconds):
    ms = max(0, int(float(seconds) * 1000))
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return (
        f"{hours:02}:{minutes:02}:"
        f"{seconds:02},{ms:03}"
    )


def get_video_duration(path):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [exe, "-i", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        result.stderr,
    )
    if not match:
        raise RuntimeError(
            "មិនអាចអានរយៈពេលវីដេអូបានទេ។"
        )

    hours, minutes, seconds = match.groups()
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + float(seconds)
    )


def extract_audio(video_path, audio_path):
    run_ffmpeg([
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        audio_path,
    ])


def download_font(url, path):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()

    if len(data) < 1000:
        raise RuntimeError(
            "Font ដែលទាញយកមកមិនត្រឹមត្រូវ។"
        )

    with open(path, "wb") as file:
        file.write(data)


def parse_time(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    match = re.search(
        r"(\d+(?:\.\d+)?)",
        str(value),
    )
    return float(match.group(1)) if match else None


def transcribe_audio(api_key, audio_path):
    client = genai.Client(api_key=api_key)

    audio_file = client.files.upload(file=audio_path)

    interaction = client.interactions.create(
        model=MODEL,
        input=[
            {
                "type": "audio",
                "uri": audio_file.uri,
                "mime_type": audio_file.mime_type,
            }
        ],
        generation_config={
            "transcription_config": {
                "language_codes": ["km-KH"],
                "mode": {
                    "type": "verbatim",
                    "timestamp_granularities": ["word"],
                },
            }
        },
    )

    transcript = (
        getattr(interaction, "output_text", None) or ""
    ).strip()

    words = []

    for step in getattr(interaction, "steps", []) or []:
        for content in getattr(step, "content", []) or []:
            for annotation in (
                getattr(content, "annotations", []) or []
            ):
                if getattr(annotation, "type", None) != "word_info":
                    continue

                text = (
                    getattr(annotation, "text", None) or ""
                ).strip()
                start = parse_time(
                    getattr(annotation, "start_offset", None)
                )
                end = parse_time(
                    getattr(annotation, "end_offset", None)
                )

                if text and start is not None and end is not None:
                    if end > start:
                        words.append((start, end, text))

    words.sort(key=lambda item: item[0])
    return transcript, words


def group_words(words, max_chars=32, max_seconds=3.5):
    captions = []
    current_text = []
    start_time = None
    end_time = None

    for start, end, word in words:
        candidate = " ".join(current_text + [word])

        too_long = len(candidate) > max_chars
        too_slow = (
            start_time is not None
            and end - start_time > max_seconds
        )

        if current_text and (too_long or too_slow):
            captions.append((
                start_time,
                end_time,
                " ".join(current_text),
            ))
            current_text = []
            start_time = None

        if start_time is None:
            start_time = start

        current_text.append(word)
        end_time = end

    if current_text:
        captions.append((
            start_time,
            end_time,
            " ".join(current_text),
        ))

    fixed = []
    for start, end, text in captions:
        if fixed and start < fixed[-1][1]:
            prev_start, prev_end, prev_text = fixed[-1]
            fixed[-1] = (
                prev_start,
                max(prev_start + 0.1, start),
                prev_text,
            )

        if end > start:
            fixed.append((start, end, text))

    return [
        item for item in fixed
        if item[2].strip() and item[1] > item[0]
    ]


def fallback_captions(transcript, duration):
    text = re.sub(r"\s+", " ", transcript).strip()
    if not text:
        return []

    pieces = []
    while len(text) > 32:
        cut = text.rfind(" ", 0, 32)
        if cut < 8:
            cut = 32
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()

    if text:
        pieces.append(text)

    total = sum(max(1, len(piece)) for piece in pieces)
    cursor = 0.0
    captions = []

    for index, piece in enumerate(pieces):
        if index == len(pieces) - 1:
            end = max(duration, cursor + 0.2)
        else:
            end = cursor + duration * len(piece) / total

        captions.append((cursor, end, piece))
        cursor = end

    return captions


# API Key ត្រូវបានយកពី Streamlit Secrets
API_KEY = st.secrets.get("GEMINI_API_KEY", "")

if not API_KEY:
    st.error(
        'រកមិនឃើញ GEMINI_API_KEY ក្នុង Secrets ទេ។ '
        'សូមពិនិត្យឈ្មោះ Key ក្នុង Secrets។'
    )
    st.stop()


st.subheader("🎨 រចនាប័ទ្មអក្សរ")

font_choice = st.selectbox(
    "ជ្រើសរើស Font ខ្មែរ",
    list(FONTS.keys()),
)

font_size = st.slider(
    "ទំហំអក្សរ", 16, 36, 24
)

outline_size = st.slider(
    "កម្រាស់គែមអក្សរ", 1, 5, 2
)

font_color = st.selectbox(
    "ពណ៌អក្សរ",
    ["ស", "លឿង", "បៃតង", "ខៀវ"],
)

colors = {
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
    video_data = uploaded.getvalue()
    st.video(video_data)

    if st.button(
        "🚀 បង្កើតវីដេអូមានអក្សរខ្មែរ",
        type="primary",
        use_container_width=True,
    ):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "input.mp4")
            audio_path = os.path.join(folder, "audio.mp3")
            srt_path = os.path.join(folder, "captions.srt")
            output_path = os.path.join(folder, "output.mp4")

            font = FONTS[font_choice]
            font_path = os.path.join(folder, font["file"])

            with open(source, "wb") as file:
                file.write(video_data)

            try:
                with st.spinner("១/៤ កំពុងទាញយក Font..."):
                    download_font(font["url"], font_path)

                with st.spinner("២/៤ កំពុងដកសំឡេង..."):
                    extract_audio(source, audio_path)
                    duration = get_video_duration(source)

                with st.spinner(
                    "៣/៤ Gemini កំពុងស្គាល់សំឡេងខ្មែរ..."
                ):
                    transcript, words = transcribe_audio(
                        API_KEY, audio_path
                    )

                if not transcript:
                    st.error("Gemini មិនបានបញ្ជូនអត្ថបទមកទេ។")
                    st.stop()

                captions = group_words(words)

                if not captions:
                    captions = fallback_captions(
                        transcript, duration
                    )

                if not captions:
                    st.error("មិនអាចបង្កើតអក្សរបានទេ។")
                    st.stop()

                srt_lines = []
                for index, (start, end, text) in enumerate(
                    captions, start=1
                ):
                    start = max(0.0, start)
                    end = max(start + 0.15, end)

                    srt_lines.extend([
                        str(index),
                        f"{srt_time(start)} --> {srt_time(end)}",
                        text,
                        "",
                    ])

                with open(
                    srt_path, "w", encoding="utf-8-sig"
                ) as file:
                    file.write("\n".join(srt_lines))

                with st.spinner(
                    "៤/៤ កំពុងបង្កប់អក្សរចូល MP4..."
                ):
                    subtitle_path = escape_path(srt_path)
                    fontsdir = escape_path(folder)

                    vf = (
                        f"subtitles=filename='{subtitle_path}'"
                        f":fontsdir='{fontsdir}'"
                        f":force_style='FontName={font['name']},"
                        f"FontSize={font_size},"
                        f"PrimaryColour={colors[font_color]},"
                        f"Outline={outline_size},"
                        "OutlineColour=&H00000000,"
                        "Shadow=1,Alignment=2,MarginV=35'"
                    )

                    run_ffmpeg([
                        "-i", source,
                        "-vf", vf,
                        "-c:v", "libx264",
                        "-preset", "ultrafast",
                        "-crf", "28",
                        "-c:a", "aac",
                        "-b:a", "96k",
                        "-movflags", "+faststart",
                        output_path,
                    ])

                with open(output_path, "rb") as file:
                    result_video = file.read()

                st.success("បង្កើតវីដេអូរួចរាល់!")
                st.video(result_video)

                st.download_button(
                    "⬇️ ទាញយកវីដេអូ MP4",
                    data=result_video,
                    file_name="khmer_caption.mp4",
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True,
                )

                st.download_button(
                    "⬇️ ទាញយកអក្សរ SRT",
                    data="\n".join(srt_lines),
                    file_name="khmer_caption.srt",
                    mime="text/plain",
                    use_container_width=True,
                )

                with st.expander("អត្ថបទដែល Gemini ស្គាល់"):
                    st.write(transcript)

                with st.expander("ពិនិត្យពេលវេលាអក្សរ"):
                    st.code("\n".join(
                        f"{srt_time(a)} --> {srt_time(b)}  {t}"
                        for a, b, t in captions[:50]
                    ))

            except Exception as error:
                st.error("ការបង្កើតវីដេអូបរាជ័យ។")
                st.code(str(error))

else:
    st.info("សូមជ្រើសរើសវីដេអូជាមុនសិន។")
