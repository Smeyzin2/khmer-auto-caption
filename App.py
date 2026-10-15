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
from google.genai import types

st.set_page_config(page_title="Khmer Auto Caption", page_icon="🎬")
st.title("🎬 Khmer Auto Caption")
st.write("បង្កើតវីដេអូមានអក្សរខ្មែរ ដោយ AI")

PRIMARY_MODEL = "gemini-3.5-transcribe"
REQUEST_TIMEOUT_MS = 90000  # 90 វិនាទី

FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/"
    "main/ofl/battambang/Battambang-Regular.ttf"
)
FONT_NAME = "Battambang"


def fix_khmer(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    text = re.sub(r"(\u17D2)\s+", r"\1", text)
    text = re.sub(r"\s+([\u17B6-\u17D3])", r"\1", text)
    text = re.sub(
        r"([\u17B6-\u17D3])\s+([\u17B6-\u17D3])",
        r"\1\2",
        text,
    )
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


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


def download_font(path):
    request = urllib.request.Request(
        FONT_URL,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = response.read()
    if len(data) < 1000:
        raise RuntimeError("ទាញយក Font ខ្មែរមិនបាន។")
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


def get_fallback_models(client):
    """រកម៉ូដែល GenerateContent ដែល API Key អាចមើលឃើញ។"""
    found = []
    try:
        for model in client.models.list():
            name = getattr(model, "name", "") or ""
            name = name.replace("models/", "")
            methods = getattr(model, "supported_actions", None) or []

            if not name or "generateContent" not in methods:
                continue

            low = name.lower()
            if "flash" not in low:
                continue
            if "tts" in low or "live" in low or "embedding" in low:
                continue

            found.append(name)
    except Exception:
        pass

    preferred = [
        "gemini-3.8-flash",
        "gemini-3-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]

    ordered = [m for m in preferred if m in found]
    ordered += [m for m in found if m not in ordered]
    return ordered[:3]


def wait_until_active(client, audio, status, max_wait=60):
    """រង់ចាំឱ្យឯកសារសំឡេងរួចរាល់ (ACTIVE) មុនប្រើ។"""
    waited = 0
    while waited < max_wait:
        state = getattr(audio, "state", None)
        state_name = getattr(state, "name", str(state or "")).upper()
        if "PROCESSING" not in state_name:
            return audio
        status.write("កំពុងរង់ចាំឯកសារសំឡេងរួចរាល់...")
        time.sleep(2)
        waited += 2
        audio = client.files.get(name=audio.name)
    return audio


def is_timeout(message):
    low = message.lower()
    return (
        "timeout" in low
        or "timed out" in low
        or "deadline" in low
    )


def transcribe(api_key, audio_path, status):
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )

    status.write("កំពុងផ្ទុកសំឡេងទៅ AI...")
    audio = client.files.upload(file=audio_path)
    audio = wait_until_active(client, audio, status)
    errors = []

    # សាកម៉ូដែល Transcribe ត្រឹម 2 ដងប៉ុណ្ណោះ។
    for attempt in range(2):
        try:
            status.write("កំពុងស្គាល់សំឡេងដោយ Gemini Transcribe...")

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
                    }
                },
            )

            transcript = fix_khmer(
                getattr(result, "output_text", None) or ""
            )
            if transcript:
                return transcript, PRIMARY_MODEL

            errors.append("Transcribe មិនបានផ្ដល់អត្ថបទ")

        except Exception as e:
            message = str(e)
            errors.append(f"{PRIMARY_MODEL}: {message}")

            # កូតាអស់ ឬ timeout → ទៅម៉ូដែលបម្រុងភ្លាម
            if "429" in message or "rate limit" in message.lower():
                break
            if is_timeout(message):
                status.write("Transcribe ឆ្លើយយឺតពេក សាកម៉ូដែលបម្រុង...")
                break

            if attempt == 0 and (
                "503" in message or "UNAVAILABLE" in message.upper()
            ):
                time.sleep(1)
                continue

            break

    fallback_models = get_fallback_models(client)

    if not fallback_models:
        raise RuntimeError(
            "រកមិនឃើញម៉ូដែល Flash ដែលអាចប្រើបានសម្រាប់ API Key នេះ។\n"
            + "\n".join(errors)
        )

    prompt = (
        "Transcribe the audio exactly as spoken. "
        "The speech is primarily Khmer. Write in Khmer script. "
        "Do not translate, summarize, or explain. "
        "Preserve complete Khmer words and correct Khmer spelling. "
        "Return only the transcript."
    )

    for model in fallback_models:
        try:
            status.write(f"កំពុងសាកម៉ូដែលបម្រុង {model}...")

            response = client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    types.Part.from_uri(
                        file_uri=audio.uri,
                        mime_type=audio.mime_type,
                    ),
                ],
            )

            transcript = fix_khmer(
                getattr(response, "text", None) or ""
            )
            if transcript:
                return transcript, model

            errors.append(f"{model}: មិនមានអត្ថបទ")

        except Exception as e:
            errors.append(f"{model}: {e}")
            continue

    raise RuntimeError(
        "ម៉ូដែលទាំងអស់បរាជ័យ។ សូមពិនិត្យកូតា និងសិទ្ធិ API Key:\n\n"
        + "\n\n".join(errors)
    )


def make_captions(transcript, duration, max_chars=42):
    text = fix_khmer(transcript)
    if not text:
        return []

    sentences = [
        fix_khmer(p)
        for p in re.split(r"(?<=[។.!?])\s+|\n+", text)
        if fix_khmer(p)
    ]

    pieces = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue

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

    total = sum(max(1, len(p)) for p in pieces)
    cursor = 0.0
    captions = []

    for i, piece in enumerate(pieces):
        if i == len(pieces) - 1:
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
font_color = st.selectbox("ពណ៌អក្សរ", ["ស", "លឿង", "បៃតង", "ខៀវ"])

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
                    API_KEY, audio_path, status
                )
                status.update(
                    label=f"បានស្គាល់សំឡេងដោយ {used_model}",
                    state="complete",
                )

                captions = make_captions(transcript, duration)
                if not captions:
                    raise RuntimeError("មិនអាចបង្កើត Subtitle បានទេ។")

                lines = []
                for i, (start, end, caption_text) in enumerate(
                    captions, start=1
                ):
                    lines.extend([
                        str(i),
                        f"{time_srt(start)} --> {time_srt(max(start + 0.2, end))}",
                        fix_khmer(caption_text),
                        "",
                    ])

                with open(subtitle_path, "w", encoding="utf-8-sig") as f:
                    f.write("\n".join(lines))

                with st.spinner("៤/៤ កំពុងបង្កប់អក្សរចូល MP4..."):
                    vf = (
                        f"subtitles=filename='{escape_path(subtitle_path)}'"
                        f":fontsdir='{escape_path(folder)}'"
                        f":force_style='FontName={FONT_NAME},"
                        f"FontSize={font_size},"
                        f"PrimaryColour={colors[font_color]},"
                        f"Outline={outline_size},"
                        "OutlineColour=&H00000000,"
                        "Shadow=1,Alignment=2,MarginV=35,WrapStyle=2'"
                    )

                    run_ffmpeg([
                        "-i", source,
                        "-vf", vf,
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

                st.success(f"រួចរាល់! ម៉ូដែល៖ {used_model}")
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
