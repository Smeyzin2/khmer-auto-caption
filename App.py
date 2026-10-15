import os
import re
import json
import time
import shutil
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
MAX_CAPTION_CHARS = 26

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


def run_ffmpeg(args, cwd=None, verbose=False):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [exe, "-y"]
    if verbose:
        cmd += ["-loglevel", "verbose"]
    cmd += args
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            cwd=cwd,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", "ignore")[-1500:]
        raise RuntimeError("FFmpeg បរាជ័យ:\n" + err)
    return (result.stderr or b"").decode("utf-8", "ignore")


def probe_video(path):
    """អានរយៈពេល និងទំហំវីដេអូ។"""
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [exe, "-i", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    err = result.stderr

    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        err,
    )
    if not match:
        raise RuntimeError("មិនអាចអានរយៈពេលវីដេអូបានទេ។")
    h, m, s = match.groups()
    duration = int(h) * 3600 + int(m) * 60 + float(s)

    width, height = 16, 9
    size = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", err)
    if size:
        width, height = int(size.group(1)), int(size.group(2))

    rot = re.search(r"rotation of (-?\d+(?:\.\d+)?)", err)
    if rot and abs(float(rot.group(1))) % 180 == 90:
        width, height = height, width

    return duration, width, height


def time_ass(seconds):
    cs = max(0, int(round(float(seconds) * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


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

    # ចម្លងទៅ ~/.fonts ដើម្បីឱ្យប្រព័ន្ធរកឃើញបន្ថែម
    try:
        home_fonts = os.path.expanduser("~/.fonts")
        os.makedirs(home_fonts, exist_ok=True)
        shutil.copy(path, os.path.join(home_fonts, "Battambang-Regular.ttf"))
    except Exception:
        pass


def get_font_family(path, default):
    """អានឈ្មោះ Font ពិតពីឯកសារ Font។"""
    try:
        from fontTools.ttLib import TTFont

        font = TTFont(path)
        for record in font["name"].names:
            if record.nameID == 1:
                name = record.toUnicode().strip()
                if name:
                    return name
    except Exception:
        pass
    return default


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


def plain_to_segments(text, duration):
    """បែងចែកម៉ោងតាមប្រវែងអក្សរ ប្រើពេល AI មិនផ្តល់ម៉ោង។"""
    text = fix_khmer(text)
    if not text:
        return []

    sentences = [
        fix_khmer(p)
        for p in re.split(r"(?<=[។.!?])\s+|\n+", text)
        if fix_khmer(p)
    ]
    if not sentences:
        return [(0.0, max(duration, 0.4), text)]

    total = sum(max(1, len(p)) for p in sentences)
    cursor = 0.0
    out = []
    for i, piece in enumerate(sentences):
        if i == len(sentences) - 1:
            end = max(duration, cursor + 0.4)
        else:
            end = cursor + duration * max(1, len(piece)) / total
        out.append((cursor, end, piece))
        cursor = end
    return out


# ---------- បែងចែកអក្សរ និងតម្រឹមតាមសំឡេង ----------

def safe_split(word, n):
    """កាត់ពាក្យវែងដោយមិនបំបែកព្យញ្ជនៈជើង ឬស្រៈ។"""
    chunks = []
    while len(word) > n:
        cut = n
        while cut > 1 and (
            "\u17B6" <= word[cut] <= "\u17D3" or word[cut - 1] == "\u17D2"
        ):
            cut -= 1
        if cut <= 1:
            cut = n
        chunks.append(word[:cut])
        word = word[cut:]
    if word:
        chunks.append(word)
    return chunks


def split_display(text, max_chars=MAX_CAPTION_CHARS):
    text = fix_khmer(text)
    if not text:
        return []

    pieces = []
    current = ""
    for word in text.split():
        if len(word) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(safe_split(word, max_chars))
            continue

        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)

    return [fix_khmer(p) for p in pieces if fix_khmer(p)]


def detect_speech(audio_path, duration):
    """រកចន្លោះដែលមានសំឡេង (ផ្ទុយពីចន្លោះស្ងាត់)។"""
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [
                exe, "-i", audio_path,
                "-af", "silencedetect=noise=-32dB:d=0.35",
                "-f", "null", "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        err = result.stderr
        starts = [
            max(0.0, float(x))
            for x in re.findall(r"silence_start:\s*(-?[\d.]+)", err)
        ]
        ends = [
            float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", err)
        ]

        silences = []
        for i, s in enumerate(starts):
            e = ends[i] if i < len(ends) else duration
            silences.append((s, min(e, duration)))

        speech = []
        cursor = 0.0
        for s, e in silences:
            if s - cursor >= 0.2:
                speech.append((cursor, s))
            cursor = max(cursor, e)
        if duration - cursor >= 0.2:
            speech.append((cursor, duration))
        return speech
    except Exception:
        return []


def align_to_speech(pieces, speech):
    """ដាក់អក្សរតាមចន្លោះដែលមានសំឡេង តាមសមាមាត្រប្រវែងអក្សរ។"""
    total_len = sum(max(1, len(p)) for p in pieces)
    total_speech = sum(b - a for a, b in speech)

    idx = 0
    offset = 0.0
    out = []

    for p in pieces:
        d = total_speech * max(1, len(p)) / total_len

        a, b = speech[idx]
        if (b - (a + offset)) <= 0.001 and idx < len(speech) - 1:
            idx += 1
            offset = 0.0
            a, b = speech[idx]

        start = a + offset
        remaining = d

        while True:
            a, b = speech[idx]
            avail = b - (a + offset)
            if remaining <= avail + 1e-6 or idx == len(speech) - 1:
                offset += remaining
                end = a + offset
                break
            remaining -= avail
            idx += 1
            offset = 0.0

        out.append((start, max(end, start + 0.25), p))

    return out


def build_captions(segments, audio_path, duration):
    items = []
    for s, e, t in segments:
        parts = split_display(t)
        if not parts:
            continue
        total = sum(max(1, len(p)) for p in parts)
        cur = s
        for p in parts:
            d = (e - s) * max(1, len(p)) / total
            items.append((cur, cur + d, p))
            cur += d

    if not items:
        return [], ""

    speech = detect_speech(audio_path, duration)
    total_speech = sum(b - a for a, b in speech)

    if speech and total_speech > 0.5 and total_speech / duration < 0.92:
        pieces = [p for _, _, p in items]
        return align_to_speech(pieces, speech), "តាមសំឡេងពិត"

    return items, "តាមម៉ោងពី AI"


def write_ass(path, captions, font_family, font_size, outline_size,
              primary_color, width, height):
    play_res_y = 288
    play_res_x = max(100, int(round(play_res_y * width / max(1, height))))

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {play_res_x}",
        f"PlayResY: {play_res_y}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_family},{font_size},{primary_color},"
        f"&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,"
        f"{outline_size},1,2,20,20,35,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text",
    ]

    events = []
    for start, end, text in captions:
        clean = fix_khmer(text).replace("{", "").replace("}", "")
        clean = clean.replace("\n", " ")
        events.append(
            f"Dialogue: 0,{time_ass(start)},"
            f"{time_ass(max(start + 0.25, end))},Default,,0,0,0,,{clean}"
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + events) + "\n")


# ---------- ហៅ Gemini ----------

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
        "Transcribe this audio exactly as spoken or sung. "
        "The speech is primarily Khmer. Write in Khmer script. "
        "Do not translate, summarize, or explain. "
        "Preserve complete Khmer words and correct Khmer spelling. "
        "Put a normal space between Khmer phrases so lines can wrap. "
        "Split the speech into short subtitle segments, each about "
        "1.5 to 4 seconds long and at most 26 characters. "
        "Timestamps must match exactly when each segment is heard. "
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
                return plain_to_segments(plain, duration), model

            errors.append(f"{model}: មិនមានអត្ថបទ")
            break

    raise RuntimeError(
        "ម៉ូដែលទាំងអស់បរាជ័យ។\n\n" + "\n\n".join(errors)
    )


# ---------- ចំណុចប្រទាក់ ----------

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
            ass_path = os.path.join(folder, "captions.ass")
            output_path = os.path.join(folder, "output.mp4")
            font_path = os.path.join(folder, "Battambang.ttf")

            with open(source, "wb") as f:
                f.write(video_data)

            try:
                with st.spinner("១/៤ កំពុងទាញយក Font ខ្មែរ..."):
                    download_font(font_path)
                    font_family = get_font_family(font_path, FONT_NAME)

                with st.spinner("២/៤ កំពុងដកសំឡេង..."):
                    extract_audio(source, audio_path)
                    duration, vid_w, vid_h = probe_video(source)

                status = st.status(
                    "៣/៤ កំពុងស្គាល់សំឡេង...",
                    expanded=True,
                )
                segments, used_model = transcribe(
                    API_KEY, audio_path, duration, status
                )
                status.update(
                    label=f"បានស្គាល់សំឡេងដោយ {used_model}",
                    state="complete",
                )

                with st.spinner("កំពុងតម្រឹមអក្សរតាមសំឡេង..."):
                    captions, sync_mode = build_captions(
                        segments, audio_path, duration
                    )

                if not captions:
                    raise RuntimeError("មិនអាចបង្កើត Subtitle បានទេ។")

                write_ass(
                    ass_path,
                    captions,
                    font_family,
                    font_size,
                    outline_size,
                    colors[font_color],
                    vid_w,
                    vid_h,
                )

                with st.spinner("៤/៤ កំពុងបង្កប់អក្សរចូល MP4..."):
                    ffmpeg_log = run_ffmpeg(
                        [
                            "-i", "input.mp4",
                            "-vf", "ass=filename=captions.ass:fontsdir=.",
                            "-c:v", "libx264",
                            "-preset", "ultrafast",
                            "-crf", "26",
                            "-c:a", "aac",
                            "-b:a", "128k",
                            "-movflags", "+faststart",
                            "output.mp4",
                        ],
                        cwd=folder,
                        verbose=True,
                    )

                with open(output_path, "rb") as f:
                    result_video = f.read()

                st.success(
                    f"រួចរាល់! ម៉ូដែល៖ {used_model} | "
                    f"ការតម្រឹម៖ {sync_mode}"
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
                    for start, end, text in captions:
                        st.write(f"[{start:.1f}s - {end:.1f}s] {text}")

                with st.expander("ព័ត៌មាន Font (សម្រាប់ពិនិត្យ)"):
                    st.write(f"ឈ្មោះ Font ដែលប្រើ: {font_family}")
                    font_lines = [
                        line
                        for line in ffmpeg_log.splitlines()
                        if "fontselect" in line.lower()
                    ][:8]
                    if font_lines:
                        st.text("\n".join(font_lines))
                    else:
                        st.text("រកមិនឃើញបន្ទាត់ fontselect ក្នុង log ទេ។")

            except Exception as error:
                st.error("ការបង្កើតវីដេអូបរាជ័យ។")
                st.text(str(error))
else:
    st.info("សូមជ្រើសរើសវីដេអូជាមុនសិន។")
