import os
import re
import time
import tempfile
import subprocess
import urllib.request
import unicodedata

import streamlit as st
import imageio_ffmpeg
from google import genai

st.set_page_config(page_title="Khmer Auto Caption", page_icon="🎬")
st.title("🎬 Khmer Auto Caption")
st.write("បង្កើតវីដេអូមានអក្សរខ្មែរ ដោយ AI")

PRIMARY_MODEL = "gemini-3.5-transcribe"
FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]

FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/"
    "main/ofl/battambang/Battambang-Regular.ttf"
)
FONT_NAME = "Battambang"


def fix_khmer(text):
    if not text:
        return ""

    text = unicodedata.normalize("NFC", str(text))

    # កុំឱ្យដកឃ្លាបំបែកជើងអក្សរខ្មែរ
    text = re.sub(r"(\u17D2)\s+", r"\1", text)
    text = re.sub(r"\s+([\u17B6-\u17D3])", r"\1", text)
    text = re.sub(
        r"([\u17B6-\u17D3])\s+([\u17B6-\u17D3])",
        r"\1\2",
        text,
    )
    text = re.sub(
        r"(\u17D2)\s+([\u1780-\u17A2])",
        r"\1\2",
        text,
    )

    return re.sub(r"[ \t]+", " ", text).strip()


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


def get_duration(path):
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
        raise RuntimeError("មិនអាចអានរយៈពេលវីដេអូបានទេ។")

    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def time_srt(seconds):
    ms = max(0, int(float(seconds) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def parse_time(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    match = re.search(r"(\d+(?:\.\d+)?)", str(value))
    return float(match.group(1)) if match else None


def download_font(path):
    request = urllib.request.Request(
        FONT_URL,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()

    if len(data) < 1000:
        raise RuntimeError("ទាញយក Font ខ្មែរមិនបានត្រឹមត្រូវ។")

    with open(path, "wb") as f:
        f.write(data)


def extract_audio(video_path, audio_path):
    run_ffmpeg([
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        audio_path,
    ])


def transcribe(api_key, audio_path, status):
    client = genai.Client(api_key=api_key)

    status.write("កំពុងផ្ទុកសំឡេងទៅ AI...")
    audio = client.files.upload(file=audio_path)
    errors = []

    for attempt in range(2):
        try:
            status.write("កំពុងសាក Gemini Transcribe...")

            result = client.interactions.create(
                model=PRIMARY_MODEL,
                input=[{
                    "type": "audio",
                    "uri": audio.uri,
                    "mime_type": audio.mime_type,
                }],
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

            transcript = fix_khmer(
                getattr(result, "output_text", None) or ""
            )

            if transcript:
                status.write("បានស្គាល់សំឡេងដោយ Gemini Transcribe")
                return transcript, PRIMARY_MODEL

            errors.append("Gemini Transcribe មិនបានផ្ដល់អត្ថបទ")

        except Exception as e:
            errors.append(f"{PRIMARY_MODEL}: {e}")

        if attempt == 0:
            time.sleep(2)

    for model in FALLBACK_MODELS:
        try:
            status.write(f"កំពុងសាកម៉ូដែលបម្រុង {model}...")

            prompt = (
                "Transcribe the audio exactly as spoken. "
                "The speech is primarily Khmer. Write in Khmer script. "
                "Do not translate, summarize, invent, or explain. "
                "Preserve complete Khmer words and correct Khmer spelling. "
                "Do not split Khmer consonant clusters or words into fragments. "
                "Return only the transcript."
            )

            response = client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    genai.types.Part.from_uri(
                        file_uri=audio.uri,
                        mime_type=audio.mime_type,
                    ),
                ],
            )

            transcript = fix_khmer(
                getattr(response, "text", None) or ""
            )

            if transcript:
                status.write(f"បានស្គាល់សំឡេងដោយ {model}")
                return transcript, model

            errors.append(f"{model}: មិនបានផ្ដល់អត្ថបទ")

        except Exception as e:
            errors.append(f"{model}: {e}")

    raise RuntimeError(
        "ម៉ូដែលទាំងអស់បរាជ័យ:\n\n" + "\n\n".join(errors)
    )


def make_captions(transcript, duration, max_chars=42):
    text = fix_khmer(transcript)

    if not text:
        return []

    # បំបែកតាមប្រយោគជាមុន
    sentences = [
        fix_khmer(part)
        for part in re.split(r"(?<=[។.!?])\s+|\n+", text)
        if fix_khmer(part)
    ]

    pieces = []

    for sentence in sentences:
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue

        # បំបែកតាមចន្លោះដែលមានស្រាប់ មិនកាត់ពាក់កណ្ដាលពាក្យ
        current = ""

        for word in sentence.split():
            candidate = f"{current} {word}".strip()

            if current and len(candidate) > max_chars:
                pieces.append(fix_khmer(current))
                current = word
            else:
                current = candidate

        if current:
            pieces.append(fix_khmer(current))

    if not pieces:
        return [(0.0, max(duration, 0.2), text)]

    total = sum(max(1, len(piece)) for piece in pieces)
    cursor = 0.0
    captions = []

    for index, piece in enumerate(pieces):
        if index == len(pieces) - 1:
            end = max(duration, cursor + 0.2)
        else:
            end = cursor + duration * max(1, len(piece)) / total

        captions.append((cursor, end, fix_khmer(piece)))
        cursor = end

    return captions


API_KEY = st.secrets.get("GEMINI_API_KEY", "")

if not API_KEY:
    st.error("រកមិនឃើញ GEMINI_API_KEY ក្នុង Streamlit Secrets ទេ។")
    st.stop()


st.subheader("🎨 កំណត់អក្សរ")

font_size = st.slider("ទំហំអក្សរ", 16, 36, 25)
outline_size = st.slider("កម្រាស់គែមអក្សរ", 1, 5, 2)

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
            subtitle_path = os.path.join(folder, "captions.srt")
            output_path = os.path.join(folder, "output.mp4")
            font_path = os.path.join(folder, "Battambang.ttf")

            with open(source, "wb") as f:
                f.write(video_data)

            try:
                with st.spinner("១/៤ កំពុងទាញយក Font ខ្មែរ..."):
                    download_font(font_path)

                with st.spinner("២/៤ កំពុងដកសំឡេង..."):
                    extract_audio(source, audio_path)
                    duration = get_duration(source)

                status = st.status(
                    "៣/៤ កំពុងស្គាល់សំឡេង...",
                    expanded=True,
                )

                transcript, used_model = transcribe(
                    API_KEY,
                    audio_path,
                    status,
                )

                status.update(
                    label=f"បានស្គាល់សំឡេងដោយ {used_model}",
                    state="complete",
                )

                captions = make_captions(transcript, duration)

                if not captions:
                    raise RuntimeError("មិនអាចបង្កើត Subtitle បានទេ។")

                srt_lines = []

                for index, (start, end, caption_text) in enumerate(
                    captions, start=1
                ):
                    caption_text = fix_khmer(caption_text)
                    start = max(0.0, start)
                    end = max(start + 0.2, end)

                    srt_lines.extend([
                        str(index),
                        f"{time_srt(start)} --> {time_srt(end)}",
                        caption_text,
                        "",
                    ])

                with open(
                    subtitle_path,
                    "w",
                    encoding="utf-8-sig",
                ) as f:
                    f.write("\n".join(srt_lines))

                with st.spinner("៤/៤ កំពុងបង្កប់អក្សរចូល MP4..."):
                    sub = escape_path(subtitle_path)
                    fonts = escape_path(folder)

                    video_filter = (
                        f"subtitles=filename='{sub}'"
                        f":fontsdir='{fonts}'"
                        f":force_style='FontName={FONT_NAME},"
                        f"FontSize={font_size},"
                        f"PrimaryColour={colors[font_color]},"
                        f"Outline={outline_size},"
                        "OutlineColour=&H00000000,"
                        "Shadow=1,"
                        "Alignment=2,"
                        "MarginV=35,"
                        "WrapStyle=2'"
                    )

                    run_ffmpeg([
                        "-i", source,
                        "-vf", video_filter,
                        "-c:v", "libx264",
                        "-preset", "ultrafast",
                        "-crf", "26",
                        "-c:a", "aac",
                        "-b:a", "128k",
                        "-movflags", "+faststart",
                        output_path,
                    ])

                with open(output_path, "rb") as f:
                    result_video = f.read()

                st.success(
                    f"បង្កើតវីដេអូរួចរាល់! ម៉ូដែល៖ {used_model}"
                )

                st.video(result_video)

                st.download_button(
                    "⬇️ ទាញយកវីដេអូ MP4",
                    data=result_video,
                    file_name="khmer_caption.mp4",
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True,
                )

                with st.expander("អត្ថបទដែល AI ស្គាល់"):
                    st.write(transcript)

            except Exception as error:
                st.error("ការបង្កើតវីដេអូបរាជ័យ។")
                st.code(str(error))

else:
    st.info("សូមជ្រើសរើសវីដេអូជាមុនសិន។")
