import os
import io
import re
import json
import time
import shutil
import asyncio
import zipfile
import tempfile
import subprocess
import urllib.parse
import urllib.request
import unicodedata

import streamlit as st
import streamlit.components.v1 as components
import imageio_ffmpeg
import edge_tts
from google import genai
from google.genai import types

st.set_page_config(
    page_title="Khmer Auto Caption",
    page_icon="🎬",
    layout="centered",
)

# លាក់ម៉ឺនុយ និងរបារបច្ចេកទេសរបស់ Streamlit
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;}
    [data-testid="stDecoration"] {display: none;}
    .stDeployButton {display: none;}
    </style>
    """,
    unsafe_allow_html=True,
)

DEBUG = bool(st.secrets.get("DEBUG", False))

REQUEST_TIMEOUT_MS = 120000  # 120 វិនាទី
MAX_CAPTION_CHARS = 26
MAX_DOWNLOAD_MB = 300
MAX_VIDEOS = 5  # ចំនួនវីដេអូអតិបរមាក្នុងមួយដង
MAX_ZIP_MB = 250

PREFERRED_MODELS = [
    "gemini-3.8-flash",
    "gemini-3-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"

# (ឈ្មោះឯកសារ, តំណ, ឈ្មោះ Font លំនាំដើម)
FONT_SOURCES = [
    (
        "Battambang.ttf",
        GF + "battambang/Battambang-Regular.ttf",
        "Battambang",
    ),
    ("Content.ttf", GF + "content/Content-Regular.ttf", "Content"),
    ("Siemreap.ttf", GF + "siemreap/Siemreap-Regular.ttf", "Siemreap"),
    ("Bokor.ttf", GF + "bokor/Bokor-Regular.ttf", "Bokor"),
]

# ឈ្មោះ: (ទំហំអតិបរមា, CRF, preset)
QUALITY = {
    "⚡ លឿន": (480, 28, "ultrafast"),
    "✨ ល្អ (ណែនាំ)": (720, 24, "veryfast"),
    "💎 គុណភាពខ្ពស់": (0, 20, "veryfast"),
}

# ភាសាក្នុងវីដេអូ: ឈ្មោះអង់គ្លេសសម្រាប់ប្រាប់ AI (None = ស្វ័យប្រវត្តិ)
LANGUAGES = {
    "🌐 ស្វ័យប្រវត្តិ (ភាសាអ្វីក៏បាន)": None,
    "ខ្មែរ": "Khmer",
    "អង់គ្លេស": "English",
    "ថៃ": "Thai",
    "វៀតណាម": "Vietnamese",
    "ចិន": "Chinese",
    "ជប៉ុន": "Japanese",
    "កូរ៉េ": "Korean",
    "បារាំង": "French",
}

# សំឡេងអានខ្មែរ (edge-tts)
TTS_VOICES = {
    "ស្រី (Sreymom)": "km-KH-SreymomNeural",
    "ប្រុស (Piseth)": "km-KH-PisethNeural",
}


class UserError(RuntimeError):
    """សារកំហុសដែលសមស្របនឹងបង្ហាញដល់អ្នកប្រើផ្ទាល់។"""


def friendly_message(error):
    if isinstance(error, UserError):
        return str(error)

    low = str(error).lower()

    if "429" in low or "resource_exhausted" in low or "quota" in low:
        return (
            "មានអ្នកប្រើច្រើនពេកនៅពេលនេះ។ "
            "សូមរង់ចាំមួយភ្លែត រួចសាកម្តងទៀត។"
        )
    if (
        "503" in low
        or "unavailable" in low
        or "high demand" in low
        or "overloaded" in low
        or "timeout" in low
        or "timed out" in low
    ):
        return "ប្រព័ន្ធ AI កំពុងរវល់។ សូមសាកម្តងទៀតក្នុងមួយភ្លែត។"
    if "api key" in low or "api_key" in low or "permission" in low:
        return "សេវា AI មានបញ្ហា។ សូមទាក់ទងម្ចាស់កម្មវិធី។"

    return "ការបង្កើតវីដេអូមិនបានសម្រេច។ សូមសាកម្តងទៀត។"


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


def has_khmer(text):
    return bool(re.search(r"[\u1780-\u17FF]", text or ""))


def khmer_ratio(segments):
    """សមាមាត្រនៃអត្ថបទដែលមានអក្សរខ្មែរ។"""
    if not segments:
        return 0.0
    good = sum(1 for _, _, t in segments if has_khmer(t))
    return good / len(segments)


def safe_filename(name):
    base = os.path.splitext(str(name))[0]
    base = re.sub(r"[^\w\-]+", "_", base).strip("_")[:40]
    return base or "video"


def run_ffmpeg(args, cwd=None, verbose=False, env=None):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [exe, "-y"]
    if verbose:
        cmd += ["-loglevel", "verbose"]
    cmd += args

    full_env = None
    if env:
        full_env = os.environ.copy()
        full_env.update(env)

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            cwd=cwd,
            env=full_env,
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
        raise UserError(
            "មិនអាចអានវីដេអូនេះបានទេ។ សូមសាកវីដេអូ MP4 ផ្សេង។"
        )
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


# ---------- Font ----------

@st.cache_resource(show_spinner=False)
def load_font_bytes():
    """ទាញយក Font ខ្មែរតែម្តង (cache) ប្រើបានគ្រប់វីដេអូ។"""
    out = []
    for i, (filename, url, default_name) in enumerate(FONT_SOURCES):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(request, timeout=25) as response:
                data = response.read()
            if len(data) < 1000:
                raise RuntimeError("ទាញយក Font ខ្មែរមិនបាន។")
        except Exception:
            if i == 0:
                raise
            continue
        out.append((filename, data, default_name))
    return out


def install_fonts(folder):
    """ដាក់ Font ចូលថតរបស់វីដេអូនីមួយៗ។"""
    fonts = []
    for filename, data, default_name in load_font_bytes():
        path = os.path.join(folder, filename)
        with open(path, "wb") as f:
            f.write(data)
        fonts.append((path, default_name))

    # ចម្លង Font ទីមួយទៅ ~/.fonts ដើម្បីឱ្យប្រព័ន្ធរកឃើញបន្ថែម
    try:
        home_fonts = os.path.expanduser("~/.fonts")
        os.makedirs(home_fonts, exist_ok=True)
        dst = os.path.join(home_fonts, "Battambang-Regular.ttf")
        if not os.path.exists(dst):
            shutil.copy(fonts[0][0], dst)
    except Exception:
        pass

    return fonts


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


def make_fontconfig_env(folder):
    """បង្កើត fontconfig ផ្ទាល់ខ្លួន ដើម្បីបង្ខំឱ្យរក Font ក្នុងថតនេះឃើញ។"""
    cache_dir = os.path.join(folder, "fc-cache")
    os.makedirs(cache_dir, exist_ok=True)
    conf_path = os.path.join(folder, "fonts.conf")

    conf = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        "<fontconfig>\n"
        '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
        f"  <dir>{folder}</dir>\n"
        "  <dir>~/.fonts</dir>\n"
        f"  <cachedir>{cache_dir}</cachedir>\n"
        "</fontconfig>\n"
    )
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(conf)

    return {
        "FONTCONFIG_FILE": conf_path,
        "FONTCONFIG_PATH": folder,
    }


def font_was_used(log, keys):
    """ពិនិត្យ log របស់ FFmpeg ថា Font ខ្មែរត្រូវបានប្រើពិតឬទេ។"""
    lines = [l for l in log.splitlines() if "fontselect" in l.lower()]
    if not lines:
        return True  # មិនដឹង → ទទួលយក

    for line in lines:
        right = line.split("->", 1)[-1].lower()
        if any(k in right for k in keys):
            return True
    return False


# ---------- ទាញយកវីដេអូ និងសំឡេង ----------

def normalize_link(url):
    """បំលែងតំណ Google Drive ទៅជាតំណទាញយកផ្ទាល់។"""
    url = url.strip()
    match = re.search(r"drive\.google\.com/file/d/([\w-]+)", url)
    if not match:
        match = re.search(r"drive\.google\.com/open\?id=([\w-]+)", url)
    if match:
        return (
            "https://drive.google.com/uc?export=download&id="
            + match.group(1)
        )
    return url


def download_video(url, path, progress):
    """ទាញយកវីដេអូពីតំណដោយ server (លឿនជាងការ upload ពីទូរសព្ទ)។"""
    url = normalize_link(url)
    limit = MAX_DOWNLOAD_MB * 1024 * 1024

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            ctype = (response.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype:
                raise UserError(
                    "តំណនេះមិនមែនជាវីដេអូផ្ទាល់ទេ។ "
                    "សូមប្រើតំណ .mp4 ផ្ទាល់ ឬ Google Drive "
                    "ដែលចែករំលែកជាសាធារណៈ។"
                )

            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(path, "wb") as f:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if done > limit:
                        raise UserError(
                            f"វីដេអូធំជាង {MAX_DOWNLOAD_MB}MB។ "
                            "សូមប្រើវីដេអូតូចជាងនេះ។"
                        )
                    if total:
                        progress.progress(min(1.0, done / total))
    except UserError:
        raise
    except Exception:
        raise UserError(
            "ទាញយកវីដេអូពីតំណមិនបានទេ។ សូមពិនិត្យតំណ ឬសាកម្តងទៀត។"
        )

    if os.path.getsize(path) < 1000:
        raise UserError("ទាញយកវីដេអូមិនបាន។ សូមពិនិត្យតំណ។")
    progress.progress(1.0)


def extract_audio(video_path, audio_path):
    run_ffmpeg([
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        audio_path,
    ])


# ---------- Gemini ----------

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

def dbg(status, message):
    """បង្ហាញព័ត៌មានបច្ចេកទេស តែក្នុងមុខងារ DEBUG ប៉ុណ្ណោះ។"""
    if DEBUG:
        status.write(message)


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
                status.write("ប្រព័ន្ធរវល់បន្តិច កំពុងសាកម្តងទៀត...")
                dbg(status, f"[{model}] busy, wait {wait}s")
                time.sleep(wait)
                continue

            if quota and attempt < 1:
                status.write("ប្រព័ន្ធរវល់បន្តិច កំពុងសាកម្តងទៀត...")
                dbg(status, f"[{model}] quota, wait 20s")
                time.sleep(20)
                continue

            raise


def build_prompt(duration, source_language, concise=False):
    """បង្កើតសេចក្តីណែនាំឱ្យ AI៖ ស្តាប់ភាសាអ្វីក៏បាន ហើយចេញជាអក្សរខ្មែរ។"""
    if source_language == "Khmer":
        task = (
            "The speech or singing is in Khmer. Transcribe it exactly as "
            "spoken, in Khmer script, with correct Khmer spelling. "
            "Do not translate or summarize."
        )
    elif source_language:
        task = (
            f"The speech or singing is in {source_language}. "
            "Listen carefully and translate everything into natural, "
            "fluent, easy-to-understand Khmer, written in Khmer script. "
            "Translate the meaning, not word for word."
        )
    else:
        task = (
            "First detect the spoken or sung language. "
            "If it is Khmer, transcribe it exactly in Khmer script. "
            "If it is any other language, translate everything into "
            "natural, fluent, easy-to-understand Khmer written in Khmer "
            "script. Translate the meaning, not word for word."
        )

    concise_rule = ""
    if concise:
        concise_rule = (
            "Each Khmer line must be short enough to be spoken naturally "
            "within its own time range: at most about 11 Khmer "
            "characters per second of that segment. "
            "Prefer concise wording. "
        )

    return (
        task
        + " The text of every segment MUST be written only in Khmer "
        "script (names of people, places, brands may stay as they are or "
        "be transliterated into Khmer). Never output the original "
        "language, romanization, or explanations. "
        "Put a normal space between Khmer phrases so lines can wrap. "
        "Split into short subtitle segments, each about 1.5 to 4 seconds "
        "long and at most 26 characters. "
        + concise_rule
        + "Timestamps must match exactly when each part is heard. "
        f"The audio is {duration:.1f} seconds long. "
        "Return ONLY a JSON array. Each item must be an object: "
        '{"start": <seconds as number>, "end": <seconds as number>, '
        '"text": "<Khmer text>"}. '
        "If there is no speech or singing, return an empty array []."
    )


def transcribe(api_key, audio_path, duration, source_language, status,
               concise=False):
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    if len(audio_bytes) > 18 * 1024 * 1024:
        raise UserError(
            "វីដេអូវែងពេក។ សូមប្រើវីដេអូខ្លីជាងនេះ "
            "(ប្រហែលក្រោម ៣០ នាទី)។"
        )

    models = get_available_models(client)

    if not models:
        raise RuntimeError("API Key មើលមិនឃើញម៉ូដែលណាមួយទេ។ api key")

    dbg(status, "ម៉ូដែលដែលរកឃើញ: " + ", ".join(models))

    prompt = build_prompt(duration, source_language, concise)

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
    weak = None  # លទ្ធផលមិនសូវល្អ ទុកជាជម្រើសចុងក្រោយ

    for model in models:
        for config in configs:
            dbg(status, f"កំពុងសាកម៉ូដែល {model}...")

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
                ratio = khmer_ratio(segments)
                dbg(status, f"[{model}] khmer ratio = {ratio:.2f}")

                if ratio >= 0.6:
                    return segments, model

                # មិនមែនខ្មែរគ្រប់គ្រាន់ → ទុកជាបម្រុង ហើយសាកម្តងទៀត
                kept = [s for s in segments if has_khmer(s[2])]
                if kept and (weak is None or len(kept) > len(weak[0])):
                    weak = (kept, model)
                errors.append(f"{model}: មិនមែនអក្សរខ្មែរ")
                break

            # AI មិនបានឆ្លើយជា JSON → ប្រើអត្ថបទធម្មតា
            plain = fix_khmer(re.sub(r"[\[\]{}\"]", " ", raw))
            if plain and has_khmer(plain):
                return plain_to_segments(plain, duration), model

            errors.append(f"{model}: មិនមានអត្ថបទ")
            break

    if weak:
        return weak

    # គ្មានអត្ថបទ → ទំនងគ្មានសំឡេងនិយាយ
    if not any("429" in e or "503" in e or "404" in e for e in errors):
        raise UserError(
            "រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូនេះទេ។ "
            "សូមសាកវីដេអូដែលមានសំឡេងនិយាយច្បាស់។"
        )

    raise RuntimeError(
        "ម៉ូដែលទាំងអស់បរាជ័យ។\n\n" + "\n\n".join(errors)
    )


# ---------- សំឡេងអានខ្មែរ (Dubbing) ----------

def tts_segment(text, voice, path):
    """បង្កើតសំឡេងអានខ្មែរមួយឃ្លា។"""
    async def _go():
        await edge_tts.Communicate(text, voice).save(path)

    asyncio.run(_go())


def shorten_khmer(client, model, text, max_seconds):
    """ឱ្យ AI បង្រួមប្រយោគខ្មែរ ឱ្យអានទាន់ក្នុងពេលកំណត់។"""
    limit = max(6, int(max_seconds * 11))
    try:
        response = client.models.generate_content(
            model=model,
            contents=(
                f"Shorten this Khmer sentence to at most {limit} "
                "characters. Keep the meaning. Khmer script only. "
                f"Return only the sentence.\n{text}"
            ),
        )
        out = fix_khmer(getattr(response, "text", "") or "")
        return out if has_khmer(out) else text
    except Exception:
        return text


def make_dub(folder, segments, voice, duration, keep_bg, client, model):
    """បង្កើត dub.wav ពីអត្ថបទខ្មែរ ឱ្យត្រូវតាមម៉ោងនីមួយៗ។"""
    inputs, filters = [], []
    n = 0

    if keep_bg:
        inputs += ["-i", "audio.mp3"]
        filters.append("[0:a]volume=0.15[bg]")
        n = 1

    first_voice = n
    voices = 0

    for i, (s, e, t) in enumerate(segments):
        next_s = segments[i + 1][0] if i + 1 < len(segments) else duration
        slot = max(0.5, min(next_s - 0.05, e + 0.4) - s)

        name = f"tts_{i}.mp3"
        path = os.path.join(folder, name)

        try:
            tts_segment(t, voice, path)
            d, _, _ = probe_video(path)

            # វែងពេក → បង្រួមប្រយោគ ហើយអានម្តងទៀត
            if d > slot * 1.25:
                t2 = shorten_khmer(client, model, t, slot)
                if t2 != t:
                    tts_segment(t2, voice, path)
                    d, _, _ = probe_video(path)
        except Exception:
            continue

        speed = min(1.6, max(1.0, d / slot))
        delay = int(s * 1000)

        inputs += ["-i", name]
        filters.append(
            f"[{n}:a]atempo={speed:.3f},adelay={delay}:all=1[a{n}]"
        )
        n += 1
        voices += 1

    if voices == 0:
        return False

    labels = "[bg]" if keep_bg else ""
    labels += "".join(f"[a{k}]" for k in range(first_voice, n))

    fc = (
        ";".join(filters)
        + f";{labels}amix=inputs={n}:dropout_transition=0,"
        f"volume={n}[out]"
    )

    run_ffmpeg(
        inputs + [
            "-filter_complex", fc,
            "-map", "[out]",
            "-t", f"{duration:.2f}",
            "dub.wav",
        ],
        cwd=folder,
    )
    return os.path.exists(os.path.join(folder, "dub.wav"))


# ---------- Render វីដេអូ ----------

def build_video_filter(max_side):
    """បង្រួមវីដេអូ (បើជ្រើស) ហើយបង្កប់អក្សរ។"""
    ass = "ass=filename=captions.ass:fontsdir=."
    if max_side and max_side > 0:
        scale = (
            f"scale=w='if(gt(iw,ih),-2,min({max_side},iw))':"
            f"h='if(gt(iw,ih),min({max_side},ih),-2)'"
        )
        return f"{scale},{ass},format=yuv420p"
    return f"{ass},format=yuv420p"


def render_with_fonts(folder, fonts, captions, font_size, outline_size,
                      color, vid_w, vid_h, quality, status, dub=False):
    """
    Render វីដេអូ ហើយពិនិត្យថា Font ខ្មែរត្រូវបានប្រើពិតឬទេ។
    បើមិនបាន សាកវិធី ឬ Font ផ្សេងបន្ត។
    """
    ass_path = os.path.join(folder, "captions.ass")
    output_path = os.path.join(folder, "output.mp4")
    max_side, crf, preset = quality

    conf_env = make_fontconfig_env(folder)

    # (លេខ Font, ប្រើ fontconfig ផ្ទាល់ខ្លួនឬទេ)
    plan = [(0, False), (0, True)]
    plan += [(i, True) for i in range(1, len(fonts))]

    attempts = []
    have_output = False
    best = None

    for font_index, use_conf in plan:
        font_path, default_name = fonts[font_index]
        family = get_font_family(font_path, default_name)
        keys = [family.lower(), default_name.lower()]

        write_ass(
            ass_path, captions, family, font_size, outline_size,
            color, vid_w, vid_h,
        )

        args = ["-i", "input.mp4"]
        if dub:
            args += ["-i", "dub.wav"]
        args += ["-vf", build_video_filter(max_side)]
        if dub:
            args += ["-map", "0:v:0", "-map", "1:a:0"]
        args += [
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(crf),
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "output.mp4",
        ]

        try:
            log = run_ffmpeg(
                args,
                cwd=folder,
                verbose=True,
                env=conf_env if use_conf else None,
            )
        except RuntimeError:
            attempts.append(f"{family} conf={use_conf}: ffmpeg error")
            if not have_output and (font_index, use_conf) == plan[-1]:
                raise
            continue

        ok = font_was_used(log, keys)
        attempts.append(f"{family} conf={use_conf}: ok={ok}")

        have_output = True
        best = (family, log)

        if ok:
            break
        dbg(status, f"Font {family} មិនត្រូវបានប្រើ កំពុងសាកវិធីផ្សេង...")

    if not have_output:
        raise RuntimeError("Render មិនបាន។\n" + "\n".join(attempts))

    with open(output_path, "rb") as f:
        data = f.read()

    return data, best[0], best[1], attempts


# ---------- ដំណើរការវីដេអូមួយៗ (កន្លែងធ្វើការ) ----------

def process_one(index, total, item, settings, box):
    """ធ្វើវីដេអូមួយ នៅក្នុងប្រអប់ផ្ទាល់ខ្លួនរបស់វា។"""
    name = item["name"]
    result = {
        "name": name,
        "video": None,
        "captions": [],
        "error": None,
        "raw_error": "",
        "debug": {},
    }

    with box:
        st.markdown(f"**🎞️ វីដេអូទី {index}/{total}៖ {name}**")
        status = st.status("កំពុងដំណើរការ...", expanded=True)

        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "input.mp4")
            audio_path = os.path.join(folder, "audio.mp3")

            try:
                if item.get("file") is not None:
                    with open(source, "wb") as f:
                        f.write(item["file"].getbuffer())
                else:
                    status.write("កំពុងទាញយកវីដេអូ...")
                    bar = status.progress(0.0)
                    download_video(item["url"], source, bar)

                status.write("១/៤ កំពុងរៀបចំ...")
                fonts = install_fonts(folder)

                status.write("២/៤ កំពុងដកសំឡេង...")
                extract_audio(source, audio_path)
                duration, vid_w, vid_h = probe_video(source)

                status.write("៣/៤ កំពុងស្តាប់ និងបកប្រែជាភាសាខ្មែរ...")
                segments, used_model = transcribe(
                    API_KEY,
                    audio_path,
                    duration,
                    settings["language"],
                    status,
                    concise=settings["dub_on"],
                )

                captions, sync_mode = build_captions(
                    segments, audio_path, duration
                )

                if not captions:
                    raise UserError(
                        "រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូនេះទេ។"
                    )

                dub_ok = False
                if settings["dub_on"]:
                    status.write("🎙 កំពុងបង្កើតសំឡេងខ្មែរ...")
                    try:
                        dub_ok = make_dub(
                            folder,
                            segments,
                            settings["voice"],
                            duration,
                            settings["keep_bg"],
                            genai.Client(api_key=API_KEY),
                            used_model,
                        )
                    except Exception:
                        dub_ok = False
                    if not dub_ok:
                        st.warning(
                            "បង្កើតសំឡេងអានមិនបានទេ។ "
                            "វីដេអូនឹងមានតែអក្សរ។"
                        )

                status.write("៤/៤ កំពុងដាក់អក្សរចូលវីដេអូ...")
                video, used_font, ffmpeg_log, attempts = render_with_fonts(
                    folder,
                    fonts,
                    captions,
                    settings["font_size"],
                    settings["outline_size"],
                    settings["color"],
                    vid_w,
                    vid_h,
                    settings["quality"],
                    status,
                    dub=dub_ok,
                )

                result["video"] = video
                result["captions"] = [t for _, _, t in captions]
                result["debug"] = {
                    "ម៉ូដែល": used_model,
                    "ការតម្រឹម": sync_mode,
                    "Font ដែលប្រើ": used_font,
                    "Dubbing": dub_ok,
                    "ទំហំលទ្ធផល": f"{len(video) / (1024 * 1024):.1f}MB",
                    "ការសាក Font": "\n".join(attempts),
                    "fontselect": "\n".join(
                        line
                        for line in ffmpeg_log.splitlines()
                        if "fontselect" in line.lower()
                    )[:1500],
                }

                status.update(
                    label=f"✅ រួចរាល់៖ {name}",
                    state="complete",
                    expanded=False,
                )

            except Exception as error:
                msg = friendly_message(error)
                result["error"] = msg
                result["raw_error"] = str(error)
                status.update(
                    label=f"❌ មានបញ្ហា៖ {name}",
                    state="error",
                    expanded=False,
                )
                st.error(msg)
                if DEBUG:
                    st.text(str(error))

    return result


# ---------- កន្លែងទាញយក ----------

def build_zip(results):
    ok = [r for r in results if r.get("video")]
    if len(ok) < 2:
        return None
    total = sum(len(r["video"]) for r in ok)
    if total > MAX_ZIP_MB * 1024 * 1024:
        return None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i, r in enumerate(ok, start=1):
            z.writestr(
                f"{i:02d}_{safe_filename(r['name'])}_khmer.mp4",
                r["video"],
            )
    return buf.getvalue()


def render_results(results, zip_bytes):
    # ចំណុចយោងសម្រាប់លោតមកទីនេះ
    st.markdown('<div id="download-area"></div>', unsafe_allow_html=True)
    st.divider()
    st.subheader("⬇️ កន្លែងទាញយក")

    ok_count = sum(1 for r in results if r.get("video"))
    st.caption(f"រួចរាល់ {ok_count} / {len(results)} វីដេអូ")

    if zip_bytes:
        st.download_button(
            "📦 ទាញយកទាំងអស់ (ZIP)",
            data=zip_bytes,
            file_name="khmer_videos.zip",
            mime="application/zip",
            use_container_width=True,
            key="dl_zip",
        )

    for i, r in enumerate(results, start=1):
        with st.container(border=True):
            st.markdown(f"**វីដេអូទី {i}៖ {r['name']}**")

            if not r.get("video"):
                st.error(r.get("error") or "មិនបានសម្រេច។")
                continue

            st.video(r["video"])
            st.download_button(
                "⬇️ ទាញយកវីដេអូនេះ",
                data=r["video"],
                file_name=f"{safe_filename(r['name'])}_khmer.mp4",
                mime="video/mp4",
                type="primary",
                use_container_width=True,
                key=f"dl_{i}",
            )

            with st.expander("📝 មើលអត្ថបទខ្មែរ"):
                for text in r["captions"]:
                    st.write(text)

            if DEBUG:
                with st.expander("🛠 DEBUG"):
                    for key, value in r["debug"].items():
                        st.text(f"{key}: {value}")

    if st.button("🗑 លុបលទ្ធផលទាំងអស់", key="clear_results"):
        st.session_state.pop("results", None)
        st.session_state.pop("zip", None)
        st.rerun()


def scroll_to_downloads():
    """រមូរទៅកន្លែងទាញយកដោយស្វ័យប្រវត្តិ។"""
    components.html(
        f"""
        <script>
        // {time.time()}
        const go = () => {{
          try {{
            const doc = window.parent.document;
            const el = doc.getElementById("download-area");
            if (el) {{
              el.scrollIntoView({{behavior: "smooth", block: "start"}});
              return true;
            }}
          }} catch (e) {{}}
          return false;
        }};
        let tries = 0;
        const timer = setInterval(() => {{
          if (go() || ++tries > 24) clearInterval(timer);
        }}, 250);
        </script>
        """,
        height=0,
    )


# ---------- ចំណុចប្រទាក់ ----------

API_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.title("🎬 Khmer Auto Caption")
st.caption(
    "ដាក់វីដេអូភាសាអ្វីក៏បាន ទទួលបានអក្សររត់ជាភាសាខ្មែរដោយស្វ័យប្រវត្តិ "
    f"(ធ្វើបានរហូតដល់ {MAX_VIDEOS} វីដេអូម្តង)"
)

if not API_KEY:
    st.error("កម្មវិធីមិនទាន់រួចរាល់ទេ។ សូមទាក់ទងម្ចាស់កម្មវិធី។")
    st.stop()

colors = {
    "ស": "&H00FFFFFF",
    "លឿង": "&H0000FFFF",
    "បៃតង": "&H0000FF00",
    "ខៀវ": "&H00FF0000",
}

mode = st.radio(
    "វិធីបញ្ចូលវីដេអូ",
    ["📁 Upload ឯកសារ", "🔗 បិទភ្ជាប់តំណ (Link)"],
    horizontal=True,
)

uploaded_files = []
link_text = ""

if mode.startswith("📁"):
    uploaded_files = st.file_uploader(
        "ជ្រើសរើសវីដេអូ (ជ្រើសបានច្រើន)",
        type=["mp4", "mov", "mkv", "avi", "webm"],
        accept_multiple_files=True,
        help="បើអ៊ីនធឺណិតយឺត សូមប្រើវីដេអូតូច ឬជម្រើស Link",
    ) or []
else:
    link_text = st.text_area(
        "តំណវីដេអូ (.mp4 ផ្ទាល់ ឬ Google Drive សាធារណៈ) — មួយបន្ទាត់ ១ តំណ",
        placeholder="https://...\nhttps://...",
        height=110,
    )

language_label = st.selectbox(
    "ភាសាក្នុងវីដេអូ",
    list(LANGUAGES.keys()),
    index=0,
    help=(
        "ស្វ័យប្រវត្តិ៖ AI ស្គាល់ភាសាដោយខ្លួនឯង។ "
        "បើលទ្ធផលមិនត្រឹមត្រូវ សូមជ្រើសភាសាជាក់លាក់។"
    ),
)

quality_label = st.selectbox(
    "គុណភាពវីដេអូ",
    list(QUALITY.keys()),
    index=1,
)

dub_on = st.checkbox("🎙 បន្ថែមសំឡេងអានជាភាសាខ្មែរ (Dubbing)")
voice_label = list(TTS_VOICES.keys())[0]
keep_bg = False
if dub_on:
    voice_label = st.selectbox("សំឡេង", list(TTS_VOICES.keys()))
    keep_bg = st.checkbox("រក្សាសំឡេងដើមតិចៗ")

with st.expander("🎨 កំណត់អក្សរ"):
    font_size = st.slider("ទំហំអក្សរ", 16, 36, 22)
    outline_size = st.slider("កម្រាស់គែមអក្សរ", 1, 5, 2)
    font_color = st.selectbox("ពណ៌អក្សរ", list(colors.keys()))

# រៀបចំបញ្ជីវីដេអូ
items = []
too_many = False

if uploaded_files:
    too_many = len(uploaded_files) > MAX_VIDEOS
    for f in uploaded_files[:MAX_VIDEOS]:
        items.append({"name": f.name, "file": f, "url": None})
else:
    lines = [
        ln.strip()
        for ln in link_text.splitlines()
        if ln.strip().lower().startswith(("http://", "https://"))
    ]
    too_many = len(lines) > MAX_VIDEOS
    for i, url in enumerate(lines[:MAX_VIDEOS], start=1):
        tail = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
        items.append({
            "name": tail or f"តំណទី {i}",
            "file": None,
            "url": url,
        })

if too_many:
    st.warning(
        f"អាចធ្វើបានត្រឹម {MAX_VIDEOS} វីដេអូម្តង។ "
        f"កម្មវិធីនឹងធ្វើតែ {MAX_VIDEOS} ដំបូង។"
    )

run = False
if not items:
    st.info("សូមជ្រើសរើសវីដេអូ ឬបិទភ្ជាប់តំណជាមុនសិន។")
else:
    label = "🚀 បង្កើតវីដេអូមានអក្សរខ្មែរ"
    if len(items) > 1:
        label += f" ({len(items)} វីដេអូ)"
    run = st.button(label, type="primary", use_container_width=True)

# ---------- កន្លែងធ្វើការ ----------

if run:
    settings = {
        "language": LANGUAGES[language_label],
        "quality": QUALITY[quality_label],
        "dub_on": dub_on,
        "voice": TTS_VOICES[voice_label],
        "keep_bg": keep_bg,
        "font_size": font_size,
        "outline_size": outline_size,
        "color": colors[font_color],
    }

    work = st.container(border=True)
    with work:
        st.subheader("⚙️ កន្លែងធ្វើការ")
        overall = st.progress(0.0, text=f"កំពុងចាប់ផ្តើម... (0/{len(items)})")

    results = []
    for i, item in enumerate(items, start=1):
        box = work.container(border=True)
        res = process_one(i, len(items), item, settings, box)
        results.append(res)
        overall.progress(
            i / len(items),
            text=f"បានធ្វើរួច {i}/{len(items)}",
        )

    st.session_state["results"] = results
    st.session_state["zip"] = build_zip(results)

    ok_total = sum(1 for r in results if r.get("video"))
    if ok_total:
        work.success(
            f"រួចរាល់ {ok_total}/{len(results)} វីដេអូ 🎉 "
            "កំពុងទៅកន្លែងទាញយក ⬇️"
        )
    else:
        work.error("គ្មានវីដេអូណាមួយសម្រេចទេ។ សូមសាកម្តងទៀត។")

# ---------- កន្លែងទាញយក ----------

saved = st.session_state.get("results")
if saved:
    render_results(saved, st.session_state.get("zip"))
    if run and any(r.get("video") for r in saved):
        scroll_to_downloads()
