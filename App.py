import os
import re
import json
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

REQUEST_TIMEOUT_MS = 120000  # 120 វិនាទី

PREFERRED_MODELS = [
    "gemini-3.8-flash",
    "gemini-3-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
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
    try:
        return subprocess.run(
            [exe, "-y"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", "ignore")[-1500:]
        raise RuntimeError("FFmpeg បរាជ័យ:\n" + err)


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


def get_available_models(client):
    """សួរ API ថាម៉ូដែលណាអាចប្រើ generateContent បាន។"""
    found = []
    try:
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            actions = getattr(m, "supported_actions", None) or []
            low = name.lower()

            if not name or "generateContent" not in actions:
                continue
            if "flash" not in low and "pro" not in low:
                continue
            if any(
                x in low
                for x in (
                    "tts", "live", "embedding", "image",
                    "imagen", "veo", "robotics",
                )
            ):
                continue
            found.append(name)
    except Exception:
        pass

    ordered = [m for m in PREFERRED_MODELS if m in found]
    ordered += [m for m in found if m not in ordered and "flash" in m.lower()]
    ordered += [m for m in found if m not in ordered]
    return ordered[:5]


def parse_segments(raw, duration):
    """បំលែងចម្លើយ JSON ពី AI ទៅជាបញ្ជី (start, end, text)។"""
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except Exception:
        match = re.search(r"\[.*\]", raw, re.S)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except Exception:
            return []

    if isinstance(data, dict):
        data = data.get("segments") or data.get("captions") or []

    segments = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = fix_khmer(item.get("text", ""))
        try:
            start = float(item.get("start", 0))
            end = float(item.get("end", 0))
        except Exception:
            continue
        if not text:
            continue
        start = min(max(0.0, start), duration)
        end = min(max(end, start + 0.4), duration + 0.5)
        segments.append([start, end, text])

    segments.sort(key=lambda s: s[0])

    # កុំឱ្យអក្សរជាន់គ្នា
    for i in range(len(segments) - 1):
        if segments[i][1] > segments[i + 1][0]:
            segments[i][1] = max(
                segments[i][0] + 0.2, segments[i + 1][0] - 0.02
            )

    return [(s, e, t) for s, e, t in segments]


def fallback_captions(text, duration, max_chars=42):
    """បែងចែកម៉ោងតាមប្រវែងអក្សរ ប្រើពេល AI មិនផ្តល់ម៉ោង។"""
    text = fix_khmer(text)
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
        captions.append((cursor, end, piece))
        cursor = end
    return captions


def call_with_retry(client, model, prompt, audio_bytes, config, status):
    """ហៅម៉ូដែល ហើយសាកម្តងទៀតបើ Google រវល់ (503) ឬកូតាពេញ (429)។"""
    for attempt in range(3):
        try:
            kwargs = dict(
                model=model,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=audio_bytes,
                        mime_type="audio/mp3",
                    ),
                ],
            )
            if config is not None:
                kwargs["config"] = config
            return client.models.generate_content(**kwargs)

        except Exception as e:
            low = str(e).lower()

            busy = (
                "503" in low
                or "unavailable" in low
                or "high demand" in low
                or "overloaded" in low
                or "timeout" in low
                or "timed out" in low
            )
            quota = "429" in low or "resource_exhausted" in low

            if busy and attempt < 2:
                wait = 4 * (attempt + 1)
                status.write(
                    f"{model} រវល់ រង់ចាំ {wait} វិនាទី រួចសាកម្តងទៀត..."
                )
                time.sleep(wait)
                continue

            if quota and attempt < 1:
                status.write(
                    f"{model} កូតាពេញ រង់ចាំ 20 វិនាទី រួចសាកម្តងទៀត..."
                )
                time.sleep(20)
                continue

            raise


def transcribe(api_key, audio_path, duration, status):
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    if len(audio_bytes) > 18 * 1024 * 1024:
        raise RuntimeError(
            "សំឡេងធំពេក។ សូមប្រើវីដេអូខ្លីជាងនេះ (ប្រហែលក្រោម ៣០ នាទី)។"
        )

    status.write("កំពុងរកម៉ូដែលដែលអាចប្រើបាន...")
    models = get_available_models(client)

    if not models:
        raise RuntimeError(
            "API Key នេះមើលមិនឃើញម៉ូដែលណាមួយទេ។\n"
            "សូមបង្កើត Key ថ្មីនៅ aistudio.google.com "
            "ហើយដាក់ក្នុង Streamlit Secrets (GEMINI_API_KEY)។"
        )

    status.write("ម៉ូដែលដែលរកឃើញ: " + ", ".join(models))

    prompt = (
        "Transcribe this audio exactly as spoken. "
        "The speech is primarily Khmer. Write in Khmer script. "
        "Do not translate, summarize, or explain. "
        "Preserve complete Khmer words and correct Khmer spelling. "
        "Split the speech into short subtitle segments, each about "
        "2 to 6 seconds long and under 40 characters. "
        f"The audio is {duration:.1f} seconds long. "
        "Return ONLY a JSON array. Each item must be an object: "
        '{"start": <seconds as number>, "end": <seconds as number>, '
        '"text": "<Khmer text>"}. '
        "If there is no speech, return an empty array []."
    )

    # ការកំណត់ពីលឿន → ងាយ → គ្មានការកំណត់
    configs = [
        types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
        types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
        None,
    ]

    errors = []

    for model in models:
        for config in configs:
            status.write(f"កំពុងស្គាល់សំឡេងដោយ {model}...")

            try:
                response = call_with_retry(
                    client, model, prompt, audio_bytes, config, status
                )
            except Exception as e:
                message = str(e)
                low = message.lower()
                errors.append(f"{model}: {message}")

                # 400 → សាកការកំណត់ងាយជាងមុន
                if "400" in message or "invalid_argument" in low:
                    continue

                # 404 / 429 / 503 / ផ្សេងៗ → ទៅម៉ូដែលបន្ទាប់
                break

            raw = getattr(response, "text", None) or ""

            segments = parse_segments(raw, duration)
            if segments:
                return segments, model

            # AI មិនបានឆ្លើយជា JSON → ប្រើអត្ថបទធម្មតា
            plain = fix_khmer(re.sub(r"[\[\]{}\"]", " ", raw))
            if plain:
                return fallback_captions(plain, duration), model

            errors.append(f"{model}: មិនមានអត្ថបទ")
            break

    raise RuntimeError(
        "ម៉ូដែលទាំងអស់បរាជ័យ។\n\n" + "\n\n".join(errors)
    )


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
                captions, used_model = transcribe(
                    API_KEY, audio_path, duration, status
                )
                status.update(
                    label=f"បានស្គាល់សំឡេងដោយ {used_model}",
                    state="complete",
                )

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
                        "Shadow=1,Alignment=2,MarginV=35,WrapStyle=0'"
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
                    for start, end, text in captions:
                        st.write(f"[{start:.1f}s - {end:.1f}s] {text}")

            except Exception as error:
                st.error("ការបង្កើតវីដេអូបរាជ័យ។")
                st.text(str(error))
else:
    st.info("សូមជ្រើសរើសវីដេអូជាមុនសិន។")
