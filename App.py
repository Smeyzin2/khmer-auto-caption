import os
import io
import re
import json
import time
import uuid
import shutil
import asyncio
import zipfile
import tempfile
import threading
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

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
REFRESH_SECONDS = 2  # ល្បឿនធ្វើបច្ចុប្បន្នភាពអេក្រង់
MAX_RENDER_AT_ONCE = 3  # ដាក់អក្សរចូលវីដេអូស្មើគ្នាបានអតិបរមា
MAX_DURATION_MIN = 15  # វីដេអូវែងអតិបរមា (នាទី)

# ការកាត់សំឡេងជាផ្នែកៗ ដើម្បីឱ្យម៉ោងត្រឹមត្រូវ
CHUNK_TARGET = 20.0  # វិនាទី
CHUNK_MAX = 28.0
MAX_CHUNK_WORKERS = 3

# ម៉ាស៊ីនឥតគិតថ្លៃ (Groq Whisper)
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODELS = ["whisper-large-v3", "whisper-large-v3-turbo"]

# Groq LLM សម្រាប់បកប្រែបម្រុង (ពេល Google Translate ត្រូវបានរារាំង)
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"

# លេខកូដភាសាសម្រាប់ Whisper
WHISPER_LANG = {
    "Khmer": "km",
    "English": "en",
    "Thai": "th",
    "Vietnamese": "vi",
    "Chinese": "zh",
    "Japanese": "ja",
    "Korean": "ko",
    "French": "fr",
}

# អក្សរចិន/ជប៉ុន/កូរ៉េ (ដើម្បីតម្រងលទ្ធផលបកប្រែ)
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")

try:
    ST_VER = tuple(int(x) for x in re.findall(r"\d+", st.__version__)[:2])
except Exception:
    ST_VER = (1, 0)

# ម៉ូដែលខ្លាំងមុន ម៉ូដែល lite ទុកចុងក្រោយ
PREFERRED_MODELS = [
    "gemini-3.8-flash",
    "gemini-3-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-flash-lite-latest",
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


def is_quota_error(error):
    low = str(error).lower()
    return (
        "429" in low
        or "quota" in low
        or "exhausted" in low
        or "rate limit" in low
    )


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


def prepare_home_font(fonts_data):
    """ដាក់ Font ទីមួយក្នុង ~/.fonts តែម្តង (ធ្វើក្នុង thread មេ)។"""
    try:
        home_fonts = os.path.expanduser("~/.fonts")
        os.makedirs(home_fonts, exist_ok=True)
        dst = os.path.join(home_fonts, "Battambang-Regular.ttf")
        if not os.path.exists(dst):
            with open(dst, "wb") as f:
                f.write(fonts_data[0][1])
    except Exception:
        pass


def install_fonts(folder, fonts_data):
    """ដាក់ Font ចូលថតរបស់វីដេអូនីមួយៗ។"""
    fonts = []
    for filename, data, default_name in fonts_data:
        path = os.path.join(folder, filename)
        with open(path, "wb") as f:
            f.write(data)
        fonts.append((path, default_name))
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


def extract_audio(video_path, audio_path, master_path):
    """
    ដកសំឡេងពីរបែប៖
    - audio.mp3 (ស្រាល) សម្រាប់លាយសំឡេងពេល Dubbing និងម៉ាស៊ីនឥតគិតថ្លៃ
    - master.flac (គ្មានការបាត់បង់គុណភាព) សម្រាប់ឱ្យ AI ស្តាប់
    """
    try:
        run_ffmpeg([
            "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
            audio_path,
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac",
            master_path,
        ])
    except RuntimeError:
        raise UserError(
            "មិនអាចដកសំឡេងពីវីដេអូនេះបានទេ។ វីដេអូអាចគ្មានសំឡេង។"
        )


# ---------- Gemini ----------

def get_available_models(client):
    """សួរ API ថាម៉ូដែលណាអាចប្រើ generateContent បាន (lite ទុកចុងក្រោយ)។"""
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
    rest = [m for m in found if m not in ordered]
    rest.sort(
        key=lambda m: ("lite" in m.lower(), "flash" not in m.lower())
    )
    ordered += rest

    # ម៉ូដែល lite ទុកចុងក្រោយ (ភាសាខ្មែរខ្សោយជាង)
    ordered = (
        [m for m in ordered if "lite" not in m.lower()]
        + [m for m in ordered if "lite" in m.lower()]
    )
    return ordered[:6]


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


# ---------- បែងចែកអក្សរ និងតម្រឹមម៉ោង ----------

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


def snap_segments(segments, speech, duration):
    """
    ចាប់ម៉ោងចាប់ផ្តើម/បញ្ចប់ពី AI ឱ្យជិតសំឡេងពិត (បើអាចរកសំឡេងបាន)។
    បើសំឡេងមានជាប់ជានិច្ច (ភ្លេងខ្លាំង) វាទុកម៉ោងពី AI ដដែល។
    """
    segs = sorted(
        [[s, e, t] for s, e, t in segments], key=lambda x: x[0]
    )

    total_speech = sum(b - a for a, b in speech)
    if speech and duration > 0 and total_speech / duration < 0.9:
        for sg in segs:
            s, e = sg[0], sg[1]

            near = [a for a, b in speech if abs(a - s) <= 0.8]
            ns = min(near, key=lambda a: abs(a - s)) if near else s

            near = [
                b for a, b in speech
                if abs(b - e) <= 0.8 and b > ns + 0.3
            ]
            ne = min(near, key=lambda b: abs(b - e)) if near else e

            sg[0], sg[1] = ns, max(ne, ns + 0.4)

    segs.sort(key=lambda x: x[0])

    # កុំឱ្យអក្សរជាន់គ្នា
    for i in range(len(segs) - 1):
        if segs[i][1] > segs[i + 1][0]:
            segs[i][1] = max(segs[i][0] + 0.2, segs[i + 1][0] - 0.02)

    out = []
    for s, e, t in segs:
        s = min(max(0.0, s), duration)
        e = max(min(e, duration), s + 0.2)
        out.append((s, e, t))
    return out


def build_captions(segments, duration):
    """ចែកអត្ថបទវែងជាបន្ទាត់ខ្លីៗ ក្នុងចន្លោះម៉ោងរបស់វា។"""
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

    return items, "តាមម៉ោងពី AI (កែតម្រឹមតាមសំឡេង)"


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

class Reporter:
    """ផ្ញើស្ថានភាពពី thread ធ្វើការ ទៅឱ្យអេក្រង់ (មិនប្រើ st ក្នុង thread)។"""

    def __init__(self, item):
        self.item = item

    def write(self, message):
        self.item["stage"] = message
        self.item["log"].append(message)

    def progress(self, value):
        self.item["pct"] = 0.03 + 0.09 * max(0.0, min(1.0, value))


def dbg(status, message):
    """កត់ត្រាព័ត៌មានបច្ចេកទេស តែក្នុងមុខងារ DEBUG ប៉ុណ្ណោះ។"""
    if DEBUG:
        status.write(message)


def call_with_retry(client, model, prompt, audio_bytes, mime, config,
                    status):
    """ហៅម៉ូដែល ហើយសាកម្តងទៀតបើ Google រវល់ (503) ឬកូតាពេញ (429)។"""
    for attempt in range(3):
        try:
            kwargs = dict(
                model=model,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=audio_bytes,
                        mime_type=mime,
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


def build_prompt(clip_duration, source_language, concise=False):
    """បង្កើតសេចក្តីណែនាំឱ្យ AI៖ ស្តាប់ឱ្យច្បាស់ ហើយចេញជាអក្សរខ្មែរ។"""
    if source_language == "Khmer":
        task = (
            "The speech or singing is in Khmer (Cambodian). Transcribe it "
            "faithfully, word for word, in Khmer script with correct "
            "standard Khmer spelling. Do not translate, summarize or "
            "paraphrase. Do not confuse Khmer with Thai or Lao. "
            "If a word is unclear, choose the most likely Khmer word "
            "from the context."
        )
    elif source_language:
        task = (
            f"The speech or singing is in {source_language}. "
            "Listen very carefully. First write exactly what is said in "
            "the original language, then translate the meaning into "
            "natural, fluent, easy-to-understand Khmer, written in Khmer "
            "script. Translate the meaning, not word for word."
        )
    else:
        task = (
            "First detect the spoken or sung language. "
            "If it is Khmer (Cambodian), transcribe it faithfully, word "
            "for word, in Khmer script with correct standard Khmer "
            "spelling, and do not confuse it with Thai or Lao. "
            "If it is any other language, first write exactly what is "
            "said in the original language, then translate the meaning "
            "into natural, fluent, easy-to-understand Khmer written in "
            "Khmer script."
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
        + " The field \"text\" of every segment MUST be written only in "
        "Khmer script (names of people, places, brands may stay as they "
        "are or be transliterated into Khmer). Never put romanization or "
        "explanations in \"text\". "
        "Put a normal space between Khmer phrases so lines can wrap. "
        "Split into short subtitle segments, each about 1.5 to 4 seconds "
        "long, and the Khmer \"text\" of each segment at most 26 "
        "characters. "
        + concise_rule
        + "Timestamps are in seconds, measured from the very beginning "
        "of THIS audio clip (0 to "
        f"{clip_duration:.1f}). "
        "Each segment must start exactly when its first word is heard "
        "and end exactly when its last word ends. "
        "Return ONLY a JSON array. Each item must be an object: "
        '{"start": <seconds as number>, "end": <seconds as number>, '
        '"original": "<what was said in the original language>", '
        '"text": "<Khmer text>"}. '
        "If there is no speech or singing, return an empty array []."
    )


def plan_chunks(duration, speech):
    """
    កាត់សំឡេងជាផ្នែកៗ ~20 វិនាទី ត្រង់ចន្លោះស្ងាត់ (កុំឱ្យដាច់ពាក្យ)។
    ផ្នែកខ្លីៗ ធ្វើឱ្យម៉ោងពី AI ត្រឹមត្រូវជាង។
    """
    if duration <= CHUNK_MAX:
        return [(0.0, duration)]

    cuts = []
    for (a1, b1), (a2, b2) in zip(speech, speech[1:]):
        if a2 - b1 >= 0.15:
            cuts.append((b1 + a2) / 2.0)

    chunks = []
    start = 0.0
    while duration - start > CHUNK_MAX:
        target = start + CHUNK_TARGET
        limit = start + CHUNK_MAX
        cands = [c for c in cuts if start + 8.0 <= c <= limit]
        cut = min(cands, key=lambda c: abs(c - target)) if cands else target
        chunks.append((start, cut))
        start = cut
    chunks.append((start, duration))
    return chunks


def is_empty_json(raw):
    return bool(
        re.fullmatch(
            r"\s*(```(?:json)?)?\s*\[\s*\]\s*(```)?\s*", raw or ""
        )
    )


def transcribe_clip(client, models, audio_bytes, mime, clip_duration,
                    source_language, concise, status):
    """ស្តាប់សំឡេងមួយផ្នែក។ ត្រឡប់ (segments, model, errors)។"""
    prompt = build_prompt(clip_duration, source_language, concise)

    # ឱ្យ AI គិតមុនឆ្លើយ (ច្បាស់ជាង) → ការកំណត់ងាយ → គ្មានការកំណត់
    configs = [
        types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
        types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
        None,
    ]

    errors = []
    weak = None

    for model in models:
        for config in configs:
            dbg(status, f"កំពុងសាកម៉ូដែល {model}...")

            try:
                response = call_with_retry(
                    client, model, prompt, audio_bytes, mime, config,
                    status,
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

            segments = parse_segments(raw, clip_duration)
            if segments:
                ratio = khmer_ratio(segments)
                dbg(status, f"[{model}] khmer ratio = {ratio:.2f}")

                if ratio >= 0.6:
                    return segments, model, errors

                kept = [s for s in segments if has_khmer(s[2])]
                if kept and (weak is None or len(kept) > len(weak[0])):
                    weak = (kept, model)
                errors.append(f"{model}: មិនមែនអក្សរខ្មែរ")
                break

            # AI ឆ្លើយថាគ្មានសំឡេងនិយាយ (ត្រឹមត្រូវ) → ឈប់សាក
            if is_empty_json(raw):
                return [], model, []

            # AI មិនបានឆ្លើយជា JSON → ប្រើអត្ថបទធម្មតា
            plain = fix_khmer(re.sub(r"[\[\]{}\"]", " ", raw))
            if plain and has_khmer(plain):
                return plain_to_segments(plain, clip_duration), model, errors

            errors.append(f"{model}: មិនមានអត្ថបទ")
            break

    if weak:
        return weak[0], weak[1], errors

    return [], None, errors


def transcribe(api_key, audio_path, duration, source_language, status,
               concise=False, speech=None):
    """
    ស្តាប់សំឡេងទាំងមូលដោយកាត់ជាផ្នែកៗ ហើយស្តាប់ស្មើគ្នា (Gemini)។
    ត្រឡប់ (segments, model, ចំនួនផ្នែកបរាជ័យ)។
    """
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )

    models = get_available_models(client)
    if not models:
        raise RuntimeError("API Key មើលមិនឃើញម៉ូដែលណាមួយទេ។ api key")

    dbg(status, "ម៉ូដែលដែលរកឃើញ: " + ", ".join(models))

    chunks = plan_chunks(duration, speech or [])
    total = len(chunks)
    folder = os.path.dirname(audio_path)
    base = os.path.basename(audio_path)
    done_counter = {"n": 0}

    dbg(status, f"បែងចែកជា {total} ផ្នែក")

    def work(i, start, end):
        out_name = f"chunk_{i}.flac"
        run_ffmpeg(
            [
                "-ss", f"{start:.3f}",
                "-t", f"{end - start:.3f}",
                "-i", base,
                "-c:a", "flac",
                out_name,
            ],
            cwd=folder,
        )
        with open(os.path.join(folder, out_name), "rb") as f:
            data = f.read()

        if len(data) > 15 * 1024 * 1024:
            raise UserError("សំឡេងធំពេក។ សូមប្រើវីដេអូខ្លីជាងនេះ។")

        segs, model, errors = transcribe_clip(
            client,
            models,
            data,
            "audio/flac",
            end - start,
            source_language,
            concise,
            status,
        )

        done_counter["n"] += 1
        if total > 1:
            status.write(
                f"៣/៤ កំពុងស្តាប់ និងបកប្រែ... "
                f"({done_counter['n']}/{total})"
            )
        return start, segs, model, errors

    all_segments = []
    used_models = []
    failed = 0
    fatal_errors = []
    fatal_keys = ("429", "503", "404", "500", "resource_exhausted")

    workers = max(1, min(MAX_CHUNK_WORKERS, total))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [
            ex.submit(work, i, s, e) for i, (s, e) in enumerate(chunks)
        ]
        for fut in futures:
            try:
                start, segs, model, errors = fut.result()
            except UserError:
                raise
            except Exception as e:
                failed += 1
                fatal_errors.append(str(e))
                continue

            if segs:
                used_models.append(model)
                for s, e, t in segs:
                    all_segments.append(
                        (
                            min(s + start, duration),
                            min(e + start, duration + 0.5),
                            t,
                        )
                    )
            elif any(k in err.lower() for err in errors for k in fatal_keys):
                failed += 1
                fatal_errors.extend(errors)

    if not all_segments:
        if fatal_errors:
            raise RuntimeError(
                "ម៉ូដែលទាំងអស់បរាជ័យ។\n\n" + "\n\n".join(fatal_errors)
            )
        raise UserError(
            "រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូនេះទេ។ "
            "សូមសាកវីដេអូដែលមានសំឡេងនិយាយច្បាស់។"
        )

    all_segments.sort(key=lambda x: x[0])
    main_model = Counter(used_models).most_common(1)[0][0]
    return all_segments, main_model, failed


# ---------- ម៉ាស៊ីនឥតគិតថ្លៃ (Groq Whisper + Google Translate) ----------

def groq_request(api_key, audio_path, model, language):
    """ផ្ញើសំឡេងទៅ Groq Whisper ហើយទទួលអត្ថបទ + ម៉ោងតាមឃ្លា។"""
    boundary = "----kac" + uuid.uuid4().hex

    fields = [
        ("model", model),
        ("response_format", "verbose_json"),
        ("temperature", "0"),
        ("timestamp_granularities[]", "segment"),
    ]
    if language:
        fields.append(("language", language))

    parts = []
    for name, value in fields:
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    parts.append(
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; '
            'filename="audio.mp3"\r\n'
            "Content-Type: audio/mpeg\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(audio_data)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)

    request = urllib.request.Request(
        GROQ_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:500]
        raise RuntimeError(f"Groq HTTP {e.code}: {detail}")


def groq_transcribe(api_key, audio_path, language, status):
    """ហៅ Groq ដោយសាកម៉ូដែលទីពីរ បើទីមួយរវល់ ឬអស់កូតា។"""
    last = None
    for model in GROQ_MODELS:
        for attempt in range(2):
            try:
                return groq_request(api_key, audio_path, model, language), model
            except RuntimeError as e:
                last = e
                text = str(e)
                if ("429" in text or "503" in text) and attempt == 0:
                    status.write("ប្រព័ន្ធរវល់បន្តិច កំពុងសាកម្តងទៀត...")
                    time.sleep(12)
                    continue
                break
            except Exception as e:
                last = e
                break
    raise last or RuntimeError("Groq បរាជ័យ")


def _google_once(text):
    """ហៅ Google Translate ផ្ទាល់ម្តង (POST) → អត្ថបទខ្មែរ។"""
    query = urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": "km", "dt": "t"}
    )
    url = "https://translate.googleapis.com/translate_a/single?" + query
    body = urllib.parse.urlencode({"q": text}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    return "".join(
        part[0] for part in (data[0] or []) if part and part[0]
    )


def google_translate_request(text, retries=3):
    """ហៅ Google Translate ហើយរង់ចាំបន្តិចបើជួប 429។"""
    for attempt in range(retries):
        try:
            return _google_once(text)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise


def clean_translation(out):
    """សម្អាតលទ្ធផលបកប្រែ (លុបអក្សរចិនដែលនៅសល់)។"""
    out = str(out or "")
    out = CJK_RE.sub("", out)
    out = fix_khmer(out)
    return out or None


def groq_translate_chunk(api_key, texts):
    """បកប្រែជាក្រុមដោយ Groq LLM (ម៉ាស៊ីនបម្រុង ពេល Google ត្រូវបានរារាំង)។"""
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    body = json.dumps({
        "model": GROQ_CHAT_MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You translate subtitles into natural, fluent Khmer "
                    "(Khmer script only). Translate meaning, not word for "
                    "word. Return JSON: {\"translations\": [...]} with "
                    "exactly the same number of items, in the same order."
                ),
            },
            {"role": "user", "content": numbered},
        ],
    }).encode("utf-8")

    for attempt in range(3):
        request = urllib.request.Request(
            GROQ_CHAT_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            items = json.loads(content).get("translations") or []
            if len(items) == len(texts):
                return [clean_translation(x) for x in items]
            raise RuntimeError("ចំនួនបន្ទាត់មិនត្រូវគ្នា")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    return [None] * len(texts)


def translate_texts(texts, groq_key=None):
    """
    បកប្រែអត្ថបទជាភាសាខ្មែរ (ឥតគិតថ្លៃ)។
    ១) Google Translate ម្តងមួយក្រុម (បើជួប 429 ឈប់ភ្លាម)
    ២) ឃ្លាដែលនៅខ្វះ → Groq LLM
    ត្រឡប់ (លទ្ធផល, បញ្ជីមូលហេតុបរាជ័យ)។
    """
    errors = []
    outs = [None] * len(texts)
    google_blocked = False

    # បែងជាក្រុម (~1200 តួអក្សរ ក្នុងមួយសំណើ)
    batches, cur, size = [], [], 0
    for i, t in enumerate(texts):
        flat = str(t).replace("\n", " ").strip()
        if cur and size + len(flat) > 1200:
            batches.append(cur)
            cur, size = [], 0
        cur.append((i, flat))
        size += len(flat) + 1
    if cur:
        batches.append(cur)

    # ១) Google ម្តងមួយក្រុម (មិនស្មើគ្នា)
    for batch in batches:
        if google_blocked:
            break
        try:
            raw = google_translate_request("\n".join(t for _, t in batch))
            lines = (raw or "").strip("\n").split("\n")
            if len(lines) == len(batch):
                for (i, _), line in zip(batch, lines):
                    outs[i] = clean_translation(line)
        except Exception as e:
            errors.append(f"google: {e}"[:200])
            google_blocked = True
        time.sleep(0.5)

    # ២) ឃ្លាដែលនៅទទេ → Groq LLM
    missing = [i for i, o in enumerate(outs) if o is None]
    if missing and groq_key:
        for k in range(0, len(missing), 20):
            idxs = missing[k:k + 20]
            try:
                res = groq_translate_chunk(
                    groq_key, [str(texts[i]).strip() for i in idxs]
                )
                for i, r in zip(idxs, res):
                    outs[i] = r
            except Exception as e:
                errors.append(f"groq-llm: {e}"[:200])
            time.sleep(1)

    return outs, errors


def transcribe_free(groq_key, audio_path, duration, source_language,
                    status):
    """
    ស្តាប់ដោយ Groq Whisper រួចបកដោយ Google Translate (បម្រុង Groq LLM)។
    ត្រឡប់ (segments, ឈ្មោះម៉ូដែល, ចំនួនឃ្លាបរាជ័យ)។
    """
    code = WHISPER_LANG.get(source_language) if source_language else None

    data, model = groq_transcribe(groq_key, audio_path, code, status)
    detected = str(data.get("language", "") or "").lower()

    keep = []
    for sg in data.get("segments") or []:
        text = str(sg.get("text", "")).strip()
        if not text:
            continue
        # តម្រងសំឡេងរំខាន (Whisper ពេលខ្លះសរសេរអ្វីៗក្នុងសំឡេងស្ងាត់)
        if (
            float(sg.get("no_speech_prob", 0) or 0) > 0.6
            and float(sg.get("avg_logprob", 0) or 0) < -0.8
        ):
            continue
        try:
            s = float(sg.get("start", 0))
            e = float(sg.get("end", 0))
        except Exception:
            continue
        s = min(max(0.0, s), duration)
        e = min(max(e, s + 0.4), duration + 0.5)
        keep.append((s, e, text))

    if not keep:
        raise UserError(
            "រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូនេះទេ។ "
            "សូមសាកវីដេអូដែលមានសំឡេងនិយាយច្បាស់។"
        )

    failed = 0
    is_khmer = detected in ("khmer", "km") or source_language == "Khmer"

    if is_khmer:
        segs = [
            (s, e, fix_khmer(t)) for s, e, t in keep if has_khmer(t)
        ]
    else:
        status.write("៣/៤ កំពុងបកប្រែជាភាសាខ្មែរ...")
        outs, errs = translate_texts([t for _, _, t in keep], groq_key)
        segs = []
        for (s, e, _), out in zip(keep, outs):
            if out:
                segs.append((s, e, out))
            else:
                failed += 1

        if not segs or failed > len(keep) * 0.5:
            reason = " | ".join(errs[:2]) or "មិនស្គាល់មូលហេតុ"
            raise RuntimeError(
                "ការបកប្រែបរាជ័យ។ "
                f"(ស្តាប់បាន {len(keep)} ឃ្លា បកបាន {len(segs)}) "
                f"មូលហេតុ: {reason}"
            )

    if not segs:
        raise UserError("រកមិនឃើញអត្ថបទខ្មែរក្នុងសំឡេងនេះទេ។")

    segs.sort(key=lambda x: x[0])
    return segs, f"Groq {model} + Translate", failed


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
    """
    បង្កើត dub.wav ពីអត្ថបទខ្មែរ ឱ្យត្រូវតាមម៉ោងនីមួយៗ។
    បើ client = None (ម៉ាស៊ីនឥតគិតថ្លៃ) មិនបង្រួមប្រយោគទេ តែបង្កើនល្បឿនបន្ថែម។
    """
    inputs, filters = [], []
    n = 0
    max_speed = 1.6 if client is not None else 1.8

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
            if client is not None and d > slot * 1.25:
                t2 = shorten_khmer(client, model, t, slot)
                if t2 != t:
                    tts_segment(t2, voice, path)
                    d, _, _ = probe_video(path)
        except Exception:
            continue

        speed = min(max_speed, max(1.0, d / slot))
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


# ---------- ការងារ (Job) ដំណើរការស្មើគ្នា ----------

def new_item(name, path=None, url=None):
    return {
        "name": name,
        "path": path,
        "url": url,
        "state": "queued",  # queued / running / done / error
        "stage": "ក្នុងជួររង់ចាំ...",
        "pct": 0.0,
        "warn": [],
        "log": [],
        "video": None,
        "captions": [],
        "error": None,
        "raw_error": "",
        "debug": {},
        "t0": None,
        "elapsed": None,
    }


class Job:
    def __init__(self, items, folder):
        self.id = uuid.uuid4().hex[:8]
        self.items = items
        self.folder = folder
        self.render_slots = threading.Semaphore(MAX_RENDER_AT_ONCE)
        self.zip = None
        self.zip_done = False
        self.scrolled = False

    def running(self):
        return any(it["state"] in ("queued", "running") for it in self.items)


def engine_name(engine):
    return "ឥតគិតថ្លៃ (Groq)" if engine == "free" else "Gemini"


def run_worker(job, item, settings, fonts_data):
    """ដំណើរការវីដេអូមួយ ក្នុង thread ផ្ទាល់ខ្លួន (គ្មានការហៅ st)។"""
    rep = Reporter(item)
    item["t0"] = time.time()
    item["state"] = "running"

    try:
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "input.mp4")
            audio_path = os.path.join(folder, "audio.mp3")
            master_path = os.path.join(folder, "master.flac")

            if item.get("path"):
                shutil.move(item["path"], source)
                item["path"] = None
            else:
                item["pct"] = 0.03
                rep.write("កំពុងទាញយកវីដេអូ...")
                download_video(item["url"], source, rep)

            item["pct"] = 0.12
            rep.write("១/៤ កំពុងរៀបចំ...")
            fonts = install_fonts(folder, fonts_data)

            item["pct"] = 0.18
            rep.write("២/៤ កំពុងដកសំឡេង...")
            extract_audio(source, audio_path, master_path)
            duration, vid_w, vid_h = probe_video(source)

            if duration > MAX_DURATION_MIN * 60:
                raise UserError(
                    f"វីដេអូវែងពេក។ សូមប្រើវីដេអូខ្លីជាង "
                    f"{MAX_DURATION_MIN} នាទី។"
                )

            speech = detect_speech(master_path, duration)

            item["pct"] = 0.25
            rep.write("៣/៤ កំពុងស្តាប់ និងបកប្រែជាភាសាខ្មែរ...")

            # លំដាប់ម៉ាស៊ីន៖ ម៉ាស៊ីនដែលបានជ្រើសមុន ហើយម៉ាស៊ីនមួយទៀតជាបម្រុង
            order = (
                ["free", "gemini"]
                if settings["engine"] == "free"
                else ["gemini", "free"]
            )
            order = [
                k for k in order
                if (k == "free" and settings["groq_key"])
                or (k == "gemini" and settings["gemini_key"])
            ]

            segments = None
            used_engine = ""
            used_model = ""
            failed_chunks = 0
            engine_errors = []

            for idx, engine in enumerate(order):
                try:
                    if engine == "free":
                        segments, used_model, failed_chunks = (
                            transcribe_free(
                                settings["groq_key"],
                                audio_path,
                                duration,
                                settings["language"],
                                rep,
                            )
                        )
                    else:
                        segments, used_model, failed_chunks = transcribe(
                            settings["gemini_key"],
                            master_path,
                            duration,
                            settings["language"],
                            rep,
                            concise=settings["dub_on"],
                            speech=speech,
                        )
                    used_engine = engine
                    break
                except UserError:
                    raise
                except Exception as e:
                    reason = f"{engine_name(engine)}: {str(e)[:400]}"
                    engine_errors.append(reason)
                    if idx + 1 < len(order):
                        item["warn"].append(
                            "ម៉ាស៊ីនទីមួយមានបញ្ហា "
                            "កម្មវិធីបានប្តូរទៅម៉ាស៊ីនបម្រុងដោយស្វ័យប្រវត្តិ។"
                            f"\n\nមូលហេតុ → {reason}"
                        )
                        rep.write("កំពុងប្តូរទៅម៉ាស៊ីនបម្រុង...")

            if segments is None:
                raise UserError(
                    "ម៉ាស៊ីនបកប្រែទាំងអស់បរាជ័យ។\n\n"
                    + "\n\n".join(engine_errors)
                )

            if failed_chunks:
                item["warn"].append(
                    "ផ្នែកខ្លះនៃវីដេអូមិនអាចបកប្រែបាន ដូច្នេះអក្សរអាចខ្វះ។ "
                    "សូមសាកម្តងទៀតពេលក្រោយ។"
                )

            item["pct"] = 0.55
            segments = snap_segments(segments, speech, duration)
            captions, sync_mode = build_captions(segments, duration)
            if not captions:
                raise UserError("រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូនេះទេ។")

            dub_ok = False
            if settings["dub_on"]:
                item["pct"] = 0.6
                rep.write("🎙 កំពុងបង្កើតសំឡេងខ្មែរ...")
                try:
                    client = (
                        genai.Client(api_key=settings["gemini_key"])
                        if used_engine == "gemini"
                        else None
                    )
                    dub_ok = make_dub(
                        folder,
                        segments,
                        settings["voice"],
                        duration,
                        settings["keep_bg"],
                        client,
                        used_model,
                    )
                except Exception:
                    dub_ok = False
                if not dub_ok:
                    item["warn"].append(
                        "បង្កើតសំឡេងអានមិនបានទេ។ វីដេអូមានតែអក្សរ។"
                    )

            item["pct"] = 0.75
            rep.write("៤/៤ កំពុងរង់ចាំដាក់អក្សរចូលវីដេអូ...")
            with job.render_slots:
                item["pct"] = 0.82
                rep.write("៤/៤ កំពុងដាក់អក្សរចូលវីដេអូ...")
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
                    rep,
                    dub=dub_ok,
                )

            item["video"] = video
            item["captions"] = [t for _, _, t in captions]
            item["debug"] = {
                "ម៉ាស៊ីន": used_engine,
                "ម៉ូដែល": used_model,
                "ការតម្រឹម": sync_mode,
                "ផ្នែកបរាជ័យ": failed_chunks,
                "Font ដែលប្រើ": used_font,
                "Dubbing": dub_ok,
                "ទំហំលទ្ធផល": f"{len(video) / (1024 * 1024):.1f}MB",
                "ការសាក Font": "\n".join(attempts),
                "fontselect": "\n".join(
                    line
                    for line in ffmpeg_log.splitlines()
                    if "fontselect" in line.lower()
                )[:1500],
                "ម៉ោងអក្សរ": "\n".join(
                    f"[{s:.1f}-{e:.1f}] {t}" for s, e, t in captions
                ),
            }
            item["pct"] = 1.0
            item["stage"] = "រួចរាល់"
            item["elapsed"] = time.time() - item["t0"]
            item["state"] = "done"

    except Exception as error:
        item["error"] = friendly_message(error)
        item["raw_error"] = str(error)
        item["elapsed"] = time.time() - (item["t0"] or time.time())
        item["state"] = "error"

    finally:
        if item["state"] == "running":
            item["error"] = "ការបង្កើតវីដេអូមិនបានសម្រេច។ សូមសាកម្តងទៀត។"
            item["state"] = "error"
        # លុបឯកសារ upload ដែលនៅសល់ (បើមាន)
        try:
            if item.get("path") and os.path.exists(item["path"]):
                os.remove(item["path"])
        except Exception:
            pass


def build_zip(items):
    ok = [it for it in items if it["state"] == "done" and it["video"]]
    if len(ok) < 2:
        return None
    total = sum(len(it["video"]) for it in ok)
    if total > MAX_ZIP_MB * 1024 * 1024:
        return None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i, it in enumerate(ok, start=1):
            z.writestr(
                f"{i:02d}_{safe_filename(it['name'])}_khmer.mp4",
                it["video"],
            )
    return buf.getvalue()


# ---------- ចំណុចប្រទាក់៖ ផ្នែកបង្ហាញលទ្ធផល ----------

def dl_button(label, data, file_name, mime, key, **kwargs):
    """ប៊ូតុងទាញយក មិនធ្វើឱ្យអេក្រង់ផ្ទុកឡើងវិញ (បើ Streamlit គាំទ្រ)។"""
    if ST_VER >= (1, 43):
        return st.download_button(
            label,
            data=data,
            file_name=file_name,
            mime=mime,
            key=key,
            on_click="ignore",
            **kwargs,
        )
    return st.download_button(
        label,
        data=data,
        file_name=file_name,
        mime=mime,
        key=key,
        **kwargs,
    )


def work_area(job, was_running):
    """ផ្នែក ③ កន្លែងធ្វើការ៖ ស្ថានភាពវីដេអូនីមួយៗ។"""
    items = job.items
    total = len(items)
    done = sum(1 for it in items if it["state"] == "done")
    failed = sum(1 for it in items if it["state"] == "error")
    working = total - done - failed

    c1, c2, c3 = st.columns(3)
    c1.metric("⏳ កំពុងធ្វើ", working)
    c2.metric("✅ រួចរាល់", done)
    c3.metric("❌ បរាជ័យ", failed)

    st.progress(
        (done + failed) / total,
        text=f"សរុប {done + failed} / {total}",
    )

    for i, it in enumerate(items, start=1):
        with st.container(border=True):
            left, right = st.columns([4, 1])
            left.markdown(f"**{i}. {it['name']}**")

            if it["t0"]:
                if it["elapsed"] is not None:
                    secs = it["elapsed"]
                else:
                    secs = time.time() - it["t0"]
                right.caption(f"⏱ {int(secs)} វិនាទី")

            if it["state"] == "done":
                st.success("✅ រួចរាល់ — ទាញយកបាននៅផ្នែកខាងក្រោម ⬇️")
            elif it["state"] == "error":
                st.error(it["error"] or "មិនបានសម្រេច។")
                if DEBUG and it["raw_error"]:
                    st.text(it["raw_error"])
            else:
                st.progress(
                    max(0.0, min(1.0, it["pct"])),
                    text=it["stage"],
                )

            for w in it["warn"]:
                st.warning(w)

    # ធ្វើការរួចទាំងអស់ → ផ្ទុកទំព័រឡើងវិញម្តង ដើម្បីបញ្ឈប់ការធ្វើបច្ចុប្បន្នភាព
    if was_running and not job.running():
        st.rerun()


def download_area(job):
    """ផ្នែក ④ កន្លែងទាញយក៖ វីដេអូណារួច ទាញយកបានភ្លាម។"""
    done = [
        (i, it)
        for i, it in enumerate(job.items, start=1)
        if it["state"] == "done"
    ]

    if job.zip:
        dl_button(
            "📦 ទាញយកទាំងអស់ (ZIP)",
            job.zip,
            "khmer_videos.zip",
            "application/zip",
            key=f"zip_{job.id}",
            use_container_width=True,
        )

    if not done:
        st.info(
            "វីដេអូណាដែលរួចរាល់ នឹងលេចឡើងនៅទីនេះភ្លាមៗ "
            "ហើយអាចទាញយកបានតែម្តង មិនបាច់រង់ចាំវីដេអូផ្សេងទេ។"
        )
        return

    for i, it in done:
        with st.container(border=True):
            st.markdown(f"**{i}. {it['name']}**")
            st.video(it["video"])
            dl_button(
                "⬇️ ទាញយកវីដេអូនេះ",
                it["video"],
                f"{safe_filename(it['name'])}_khmer.mp4",
                "video/mp4",
                key=f"dl_{job.id}_{i}",
                type="primary",
                use_container_width=True,
            )

            with st.expander("📝 មើលអត្ថបទខ្មែរ"):
                for text in it["captions"]:
                    st.write(text)

            if DEBUG:
                with st.expander("🛠 DEBUG"):
                    for key, value in it["debug"].items():
                        st.text(f"{key}: {value}")
                    st.text("\n".join(it["log"][-30:]))


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


# ---------- ចំណុចប្រទាក់៖ ទំព័រមេ ----------

GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")
GROQ_KEY = st.secrets.get("GROQ_API_KEY", "")

st.title("🎬 Khmer Auto Caption")
st.caption(
    "ដាក់វីដេអូភាសាអ្វីក៏បាន ទទួលបានអក្សររត់ជាភាសាខ្មែរដោយស្វ័យប្រវត្តិ "
    f"(ធ្វើបានរហូតដល់ {MAX_VIDEOS} វីដេអូស្មើគ្នា)"
)

if not GEMINI_KEY and not GROQ_KEY:
    st.error("កម្មវិធីមិនទាន់រួចរាល់ទេ។ សូមទាក់ទងម្ចាស់កម្មវិធី។")
    st.stop()

colors = {
    "ស": "&H00FFFFFF",
    "លឿង": "&H0000FFFF",
    "បៃតង": "&H0000FF00",
    "ខៀវ": "&H00FF0000",
}

ENGINE_FREE = "🆓 ឥតគិតថ្លៃ (Groq + Google Translate)"
ENGINE_GEMINI = "✨ Gemini (ធម្មជាតិជាង តែមានកូតា)"

current_job = st.session_state.get("job")
busy = bool(current_job and current_job.running())

# ---------- ផ្នែក ① ជ្រើសវីដេអូ ----------

st.subheader("① 🎞️ ជ្រើសវីដេអូ")

mode = st.radio(
    "វិធីបញ្ចូលវីដេអូ",
    ["📁 Upload ឯកសារ", "🔗 បិទភ្ជាប់តំណ (Link)"],
    horizontal=True,
    label_visibility="collapsed",
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

# ---------- ផ្នែក ② ការកំណត់ ----------

st.subheader("② ⚙️ ការកំណត់")

engine_options = []
if GROQ_KEY:
    engine_options.append(ENGINE_FREE)
if GEMINI_KEY:
    engine_options.append(ENGINE_GEMINI)

engine_label = st.selectbox(
    "ម៉ាស៊ីនបកប្រែ",
    engine_options,
    index=0,
    help=(
        "បើមាន Key ទាំងពីរ ហើយម៉ាស៊ីនមួយមានបញ្ហា ឬអស់កូតា "
        "កម្មវិធីនឹងប្តូរទៅម៉ាស៊ីនមួយទៀតដោយស្វ័យប្រវត្តិ។"
    ),
)
if engine_label == ENGINE_FREE:
    st.caption(
        "ឥតគិតថ្លៃ និងលឿន។ ការបកប្រែតាម Google Translate "
        "អាចមិនទន់ភ្លន់ដូច Gemini ទេ។"
    )

language_label = st.selectbox(
    "ភាសាក្នុងវីដេអូ",
    list(LANGUAGES.keys()),
    index=0,
    help=(
        "ស្វ័យប្រវត្តិ៖ AI ស្គាល់ភាសាដោយខ្លួនឯង។ "
        "បើលទ្ធផលមិនត្រឹមត្រូវ សូមជ្រើសភាសាជាក់លាក់ "
        "(ឧ. ចិន បើវីដេអូនិយាយចិន)។"
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

# ---------- រៀបចំបញ្ជីវីដេអូ ----------

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
if busy:
    st.button(
        "⏳ កំពុងធ្វើការ... សូមរង់ចាំ",
        disabled=True,
        use_container_width=True,
    )
elif not items:
    if not current_job:
        st.info("សូមជ្រើសរើសវីដេអូ ឬបិទភ្ជាប់តំណជាមុនសិន។")
else:
    label = "🚀 បង្កើតវីដេអូមានអក្សរខ្មែរ"
    if len(items) > 1:
        label += f" ({len(items)} វីដេអូ ស្មើគ្នា)"
    run = st.button(label, type="primary", use_container_width=True)

# ---------- ចាប់ផ្តើមការងារ ----------

if run:
    try:
        fonts_data = load_font_bytes()
    except Exception:
        st.error("ទាញយក Font ខ្មែរមិនបាន។ សូមសាកម្តងទៀត។")
        st.stop()

    prepare_home_font(fonts_data)

    settings = {
        "engine": "free" if engine_label == ENGINE_FREE else "gemini",
        "gemini_key": GEMINI_KEY,
        "groq_key": GROQ_KEY,
        "language": LANGUAGES[language_label],
        "quality": QUALITY[quality_label],
        "dub_on": dub_on,
        "voice": TTS_VOICES[voice_label],
        "keep_bg": keep_bg,
        "font_size": font_size,
        "outline_size": outline_size,
        "color": colors[font_color],
    }

    # លុបការងារចាស់
    old = st.session_state.get("job")
    if old:
        shutil.rmtree(old.folder, ignore_errors=True)

    job_folder = tempfile.mkdtemp(prefix="kac_")
    job_items = []
    for idx, it in enumerate(items, start=1):
        item = new_item(it["name"], url=it["url"])
        if it["file"] is not None:
            p = os.path.join(job_folder, f"upload_{idx}.bin")
            with open(p, "wb") as f:
                f.write(it["file"].getbuffer())
            item["path"] = p
        job_items.append(item)

    job = Job(job_items, job_folder)
    st.session_state["job"] = job

    # ចាប់ផ្តើមវីដេអូទាំងអស់ស្មើគ្នា
    for item in job.items:
        threading.Thread(
            target=run_worker,
            args=(job, item, settings, fonts_data),
            daemon=True,
        ).start()

    st.rerun()

# ---------- ផ្នែក ③ ④ ----------

job = st.session_state.get("job")

if job:
    running = job.running()

    # បង្កើត ZIP តែម្តង ពេលរួចទាំងអស់
    if not running and not job.zip_done:
        job.zip = build_zip(job.items)
        job.zip_done = True

    refresh = REFRESH_SECONDS if running else None

    st.divider()
    st.subheader("③ ⚙️ កន្លែងធ្វើការ")
    st.fragment(run_every=refresh)(work_area)(job, running)

    st.markdown('<div id="download-area"></div>', unsafe_allow_html=True)
    st.divider()
    st.subheader("④ ⬇️ កន្លែងទាញយក")
    st.fragment(run_every=refresh)(download_area)(job)

    if not running:
        if st.button("🗑 លុបលទ្ធផលទាំងអស់"):
            shutil.rmtree(job.folder, ignore_errors=True)
            st.session_state.pop("job", None)
            st.rerun()

        if not job.scrolled:
            job.scrolled = True
            if any(it["state"] == "done" for it in job.items):
                scroll_to_downloads()
