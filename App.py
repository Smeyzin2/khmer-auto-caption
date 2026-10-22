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
from html import escape as html_escape

import streamlit as st
import streamlit.components.v1 as components
import imageio_ffmpeg
import edge_tts
from google import genai
from google.genai import types

st.set_page_config(
    page_title="Khmer Auto Caption",
    page_icon="🎬",
    layout="wide",
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

# ល្បឿននិយាយខ្មែរ (តួអក្សរ ក្នុងមួយវិនាទី) ប្រើកំណត់ប្រវែងឃ្លាឱ្យទាន់ពេល
CHARS_PER_SEC = 11
MAX_DUB_SPEED = 1.4  # បង្កើនល្បឿនសំឡេងអានអតិបរមា (លើសនេះស្តាប់មិនធម្មជាតិ)

# ការកាត់សំឡេងជាផ្នែកៗ ដើម្បីឱ្យម៉ោងត្រឹមត្រូវ
CHUNK_TARGET = 20.0  # វិនាទី
CHUNK_MAX = 28.0
MAX_CHUNK_WORKERS = 4

# ចំនួន thread ស្មើគ្នា (ធ្វើឱ្យលឿន)
TTS_WORKERS = 6  # បង្កើតសំឡេងអានស្មើគ្នា
LLM_WORKERS = 3  # ហៅ AI បកប្រែ/កែ ស្មើគ្នា
GS_WORKERS = 4  # Google Speech ស្មើគ្នា
TRANSLATE_WORKERS = 2  # Google Translate ស្មើគ្នា (តិចជាងមុន កុំឱ្យជួប 429)

# ម៉ាស៊ីនឥតគិតថ្លៃ (Groq Whisper)
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODELS = ["whisper-large-v3", "whisper-large-v3-turbo"]

# Groq LLM សម្រាប់បកប្រែបម្រុង (ពេល Google Translate ត្រូវបានរារាំង)
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GROQ_CHAT_PREFERRED = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b",
    "llama-3.1-8b-instant",
]
_groq_chat_cache = {"models": None, "good": None, "dead": {}}

# ផ្តល់អ្នកផ្តល់សេវា (provider) ដែលអស់កូតា ឱ្យរំលងមួយរយៈ (កុំសាកម្តងទៀតឥតប្រយោជន៍)
_provider_dead = {"gemini": 0.0, "groq": 0.0}


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

# បញ្ជី Font ខ្មែរដែលអាចជ្រើសបាន
# (ឈ្មោះ, ផ្លូវឯកសារ (ឬបញ្ជីផ្លូវសាកម្តងមួយ), ពណ៌នាខ្លី)
FONT_LIBRARY = [
    ("Battambang", "battambang/Battambang-Regular.ttf",
     "ស្តង់ដារ អានងាយ (ណែនាំ)"),
    ("Noto Sans Khmer",
     "notosanskhmer/NotoSansKhmer%5Bwdth%2Cwght%5D.ttf",
     "ទំនើប ស្អាត ច្បាស់"),
    ("Kantumruy Pro",
     "kantumruypro/KantumruyPro%5Bwght%5D.ttf",
     "ទំនើប សាមញ្ញ"),
    ("Hanuman",
     ["hanuman/Hanuman-Regular.ttf", "hanuman/Hanuman%5Bwght%5D.ttf"],
     "បែបសៀវភៅ"),
    ("Content", "content/Content-Regular.ttf", "សាមញ្ញ ស្អាត"),
    ("Siemreap", "siemreap/Siemreap-Regular.ttf", "ទន់ភ្លន់"),
    ("Koulen", "koulen/Koulen-Regular.ttf", "ក្រាស់ ខ្លាំង"),
    ("Moul", "moul/Moul-Regular.ttf", "បែបចំណងជើង"),
    ("Bayon", "bayon/Bayon-Regular.ttf", "បែបសិល្បៈ"),
    ("Bokor", "bokor/Bokor-Regular.ttf", "បែបបុរាណ"),
    ("Dangrek", "dangrek/Dangrek-Regular.ttf", "បែបសិល្បៈ"),
    ("Preahvihear", "preahvihear/Preahvihear-Regular.ttf", "សាមញ្ញ"),
    ("Odor Mean Chey", "odormeanchey/OdorMeanChey-Regular.ttf",
     "បែបសិល្បៈ"),
    ("Fasthand", "fasthand/Fasthand-Regular.ttf", "បែបដៃសរសេរ"),
]

FONT_MAP = {}
for _n, _p, _d in FONT_LIBRARY:
    FONT_MAP[_n] = {
        "family": _n,
        "paths": [_p] if isinstance(_p, str) else list(_p),
        "desc": _d,
    }
FONT_NAMES = [n for n, _, _ in FONT_LIBRARY]
DEFAULT_FONT = "Battambang"

# Font បម្រុង (បើ Font ដែលបានជ្រើសមិនអាចប្រើបាន)
FALLBACK_FONTS = ["Battambang", "Content", "Siemreap"]

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

# ពណ៌អក្សរ: ឈ្មោះ → (ពណ៌ ASS, ពណ៌ HEX សម្រាប់មើលជាមុន)
COLOR_OPTIONS = {
    "⚪ ស": ("&H00FFFFFF", "#FFFFFF"),
    "🟡 លឿង": ("&H0000FFFF", "#FFE600"),
    "🟢 បៃតង": ("&H0000FF00", "#22E55A"),
    "🔵 ខៀវ": ("&H00FF0000", "#3B82F6"),
    "🔴 ក្រហម": ("&H000000FF", "#FF3B3B"),
}

# ទីតាំងអក្សរ: ឈ្មោះ → (Alignment ASS, MarginV, ឈ្មោះសម្រាប់មើលជាមុន)
POSITIONS = {
    "↓ ក្រោម": (2, 35, "bottom"),
    "⏺️ កណ្តាល": (5, 0, "middle"),
    "↑ លើ": (8, 30, "top"),
}

SAMPLE_TEXT = "សួស្តី! នេះជាអក្សរគំរូ"
SAMPLE_VOICE_TEXT = "សួស្តី! នេះគឺជាសំឡេងអានជាភាសាខ្មែរ។"

MODE_UP = "📁 Upload · ផ្ទុកវីដេអូ"
MODE_LINK = "🔗 Link · តំណ"
MODE_BATCH = "📚 Batch · ច្រើនវីដេអូ"

ENGINE_FREE = "🆓 ឥតគិតថ្លៃ (Groq + Google Translate)"
ENGINE_GEMINI = "✨ Gemini (ធម្មជាតិជាង តែមានកូតា)"


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

def font_filename(name):
    return re.sub(r"\W+", "_", name).strip("_") + ".ttf"


@st.cache_resource(show_spinner=False)
def fetch_font(name):
    """
    ទាញយក Font ខ្មែរមួយ (cache) ប្រើបានគ្រប់វីដេអូ។
    ត្រឡប់ (ឈ្មោះឯកសារ, ទិន្នន័យ, ឈ្មោះ Font)។
    """
    info = FONT_MAP[name]
    last = None
    for path in info["paths"]:
        try:
            request = urllib.request.Request(
                GF + path,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(request, timeout=25) as response:
                data = response.read()
            if len(data) < 1000:
                raise RuntimeError("ឯកសារ Font តូចពេក។")
            return (font_filename(name), data, info["family"])
        except Exception as e:
            last = e
    raise RuntimeError(f"ទាញយក Font {name} មិនបាន: {last}")


def load_fonts_for(selected):
    """
    ទាញយក Font ដែលបានជ្រើសជាមុន រួចតាមដោយ Font បម្រុង (ស្មើគ្នា)។
    ត្រឡប់ (បញ្ជី Font, សារព្រមាន)។
    """
    if selected not in FONT_MAP:
        selected = DEFAULT_FONT
    order = [selected] + [n for n in FALLBACK_FONTS if n != selected]

    def one(name):
        try:
            return fetch_font(name)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=len(order)) as ex:
        results = list(ex.map(one, order))

    out = [r for r in results if r]
    warn = ""
    if results and results[0] is None:
        warn = (
            f"ពុម្ពអក្សរ {selected} ទាញយកមិនបាន "
            "ប្រើពុម្ពអក្សរផ្សេងជំនួស។"
        )
    if not out:
        raise RuntimeError("ទាញយក Font ខ្មែរមិនបាន។")
    return out, warn


def prepare_home_font(fonts_data):
    """ដាក់ Font ក្នុង ~/.fonts តែម្តង (ធ្វើក្នុង thread មេ)។"""
    try:
        home_fonts = os.path.expanduser("~/.fonts")
        os.makedirs(home_fonts, exist_ok=True)
        for filename, data, _ in fonts_data:
            dst = os.path.join(home_fonts, filename)
            if not os.path.exists(dst):
                with open(dst, "wb") as f:
                    f.write(data)
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
                    chunk = response.read(1024 * 1024)
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
    ដកសំឡេងពីរបែបក្នុងការហៅ FFmpeg តែម្តង៖
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
              primary_color, width, height, alignment=2, margin_v=35):
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
        f"{outline_size},1,{alignment},20,20,{margin_v},1",
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
                wait = 3 * (attempt + 1)
                status.write("ប្រព័ន្ធរវល់បន្តិច កំពុងសាកម្តងទៀត...")
                dbg(status, f"[{model}] busy, wait {wait}s")
                time.sleep(wait)
                continue

            if quota and attempt < 1:
                status.write("ប្រព័ន្ធរវល់បន្តិច កំពុងសាកម្តងទៀត...")
                dbg(status, f"[{model}] quota, wait 15s")
                time.sleep(15)
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

    style_rule = ""
    if source_language != "Khmer":
        style_rule = (
            " Do NOT translate word by word. First understand what the "
            "speaker really means in that moment, then say it the way a "
            "real native Khmer person would say it out loud while "
            "thinking and talking: smooth, fluent, casual spoken Khmer "
            "with natural word order, connecting words and sentence-final "
            "particles. Rephrase idioms and slang into the Khmer "
            "equivalent instead of copying them. Never a stiff, textbook "
            "or literal translation. Keep the original tone and feeling "
            "(casual, serious, funny, emotional) and let the sentences "
            "flow naturally from one to the next. You may reorder, merge, "
            "add or drop words freely, and use natural spoken particles "
            "and pronouns, as long as the meaning and feeling stay the "
            "same. Do not use digits, symbols or emojis in the Khmer "
            "text: write numbers as Khmer words."
        )

    concise_rule = ""
    if concise:
        concise_rule = (
            "Each Khmer line must be short enough to be spoken naturally "
            f"within its own time range: at most about {CHARS_PER_SEC} "
            "Khmer characters per second of that segment. "
            "Compress by rephrasing and dropping filler, never by "
            "cutting the sentence in the middle. "
        )

    return (
        task
        + style_rule
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
                    if "per day" in text.lower():
                        break  # អស់កូតាថ្ងៃ → ម៉ូដែលបន្ទាប់ភ្លាម
                    status.write("ប្រព័ន្ធរវល់បន្តិច កំពុងសាកម្តងទៀត...")
                    time.sleep(8)
                    continue
                break
            except Exception as e:
                last = e
                break
    raise last or RuntimeError("Groq បរាជ័យ")


# Google Translate មានពីរ host (ប្តូរ host បើមួយត្រូវបានកម្រិតសំណើ)
GT_HOSTS = ["translate.googleapis.com", "translate.google.com"]


def _google_once(text, host):
    """ហៅ Google Translate ផ្ទាល់ម្តង (POST) → អត្ថបទខ្មែរ។"""
    query = urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": "km", "dt": "t"}
    )
    url = f"https://{host}/translate_a/single?" + query
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
    """ហៅ Google Translate ប្តូរ host ហើយរង់ចាំបន្តិចបើជួប 429/503។"""
    last = None
    for attempt in range(retries):
        for host in GT_HOSTS:
            try:
                return _google_once(text, host)
            except urllib.error.HTTPError as e:
                last = e
                if e.code not in (429, 503):
                    raise
            except Exception as e:
                last = e
        time.sleep(2 * (attempt + 1))
    raise last


def clean_translation(out):
    """សម្អាតលទ្ធផលបកប្រែ (លុបអក្សរចិនដែលនៅសល់)។"""
    out = str(out or "")
    out = CJK_RE.sub("", out)
    out = fix_khmer(out)
    return out or None


def http_detail(e):
    """អានមូលហេតុលម្អិតពី HTTPError។"""
    try:
        body = e.read().decode("utf-8", "ignore")[:200]
    except Exception:
        body = ""
    return f"HTTP {e.code}: {body}".strip()


def provider_alive(name):
    return time.time() >= _provider_dead.get(name, 0.0)


def mark_provider(name, error_text):
    """
    បើ provider អស់កូតាប្រចាំថ្ងៃ → រំលងវាមួយម៉ោង។
    ជួប 429 តាមនាទី → មិនសម្គាល់ថាស្លាប់ (កុំរំលងក្រុមផ្សេងឥតប្រយោជន៍)
    លើកលែង Gemini → រំលង ១ នាទី។
    """
    low = str(error_text).lower()
    if any(k in low for k in ("per day", "perday", "tpd", "daily")):
        _provider_dead[name] = time.time() + 3600
    elif name == "gemini" and (
        "429" in low or "resource_exhausted" in low
    ):
        _provider_dead[name] = time.time() + 60


def groq_chat_models(api_key):
    """សួរ Groq ថាម៉ូដែលអក្សរណាអាចប្រើបាន (ដាក់ម៉ូដែលល្អមុន)។"""
    if _groq_chat_cache["models"]:
        return _groq_chat_cache["models"]

    found = []
    try:
        request = urllib.request.Request(
            GROQ_MODELS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Mozilla/5.0",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        for m in data.get("data") or []:
            mid = str(m.get("id", ""))
            low = mid.lower()
            if not mid or m.get("active") is False:
                continue
            if any(
                x in low
                for x in (
                    "whisper", "tts", "guard", "prompt", "orpheus",
                    "allam",
                )
            ):
                continue
            found.append(mid)
    except Exception:
        pass

    if found:
        ordered = [m for m in GROQ_CHAT_PREFERRED if m in found]
        ordered += [m for m in found if m not in ordered]
    else:
        ordered = list(GROQ_CHAT_PREFERRED)

    _groq_chat_cache["models"] = ordered
    return ordered


def groq_json_list(api_key, system, user_text, count, temperature=0.5):
    """ឱ្យ Groq LLM ឆ្លើយជាបញ្ជី JSON ដែលមានចំនួនបន្ទាត់ត្រូវគ្នា។"""
    now = time.time()
    dead = _groq_chat_cache["dead"]
    models = [m for m in groq_chat_models(api_key) if dead.get(m, 0) < now]
    good = _groq_chat_cache["good"]
    if good in models:
        models = [good] + [m for m in models if m != good]

    if not models:
        raise RuntimeError("Groq: ម៉ូដែលទាំងអស់អស់កូតា (per day)")

    errs = []
    for model in models[:8]:
        body = json.dumps({
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
        }).encode("utf-8")

        for attempt in range(2):
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
                content = re.sub(
                    r"<think>.*?</think>", "", content, flags=re.S
                )
                obj = json.loads(content)
                items = obj.get("lines") or obj.get("translations") or []
                if len(items) == count:
                    _groq_chat_cache["good"] = model
                    return [
                        clean_translation(x) if isinstance(x, str) else None
                        for x in items
                    ]
                errs.append(f"{model}: ចំនួនបន្ទាត់មិនត្រូវគ្នា")
                break
            except urllib.error.HTTPError as e:
                detail = http_detail(e)
                per_day = " [per day]" if "per day" in detail.lower() else ""
                errs.append(f"{model}: {detail[:90]}{per_day}")
                if e.code == 429 and per_day:
                    dead[model] = time.time() + 3600
                    break  # អស់កូតាថ្ងៃ → ម៉ូដែលបន្ទាប់ភ្លាម
                if e.code == 429 and attempt == 0:
                    time.sleep(4)
                    continue
                break  # 404/400/ផ្សេងៗ → ម៉ូដែលបន្ទាប់
            except Exception as e:
                errs.append(f"{model}: {e}"[:90])
                break

    # ម៉ូដែលទាំងអស់អស់កូតាថ្ងៃ → រំលង Groq LLM ទាំងមូលមួយរយៈ
    if errs and all("per day" in x.lower() for x in errs):
        _provider_dead["groq"] = time.time() + 3600

    raise RuntimeError(" | ".join(errs)[:400] or "Groq LLM បរាជ័យ")


TRANSLATE_SYSTEM = (
    "You translate subtitles into natural, fluent Khmer (Khmer script "
    "only). Translate meaning, not word for word. Return JSON: "
    "{\"translations\": [...]} with exactly the same number of items, "
    "in the same order."
)


def translate_texts(texts):
    """
    បកប្រែដោយ Google Translate (ឥតគិតថ្លៃ) ជាក្រុមៗ ស្មើគ្នា។
    បើជួប 429 → ឈប់ភ្លាម ហើយទុកឃ្លាដែលនៅខ្វះឱ្យ AI បកជំនួស។
    ត្រឡប់ (លទ្ធផល, បញ្ជីមូលហេតុបរាជ័យ)។
    """
    errors = []
    outs = [None] * len(texts)
    blocked = {"v": False}

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

    def work(batch):
        if blocked["v"]:
            return
        try:
            raw = google_translate_request("\n".join(t for _, t in batch))
            lines = (raw or "").strip("\n").split("\n")
            if len(lines) == len(batch):
                for (i, _), line in zip(batch, lines):
                    outs[i] = clean_translation(line)
        except Exception as e:
            errors.append(f"google: {e}"[:200])
            blocked["v"] = True

    with ThreadPoolExecutor(max_workers=TRANSLATE_WORKERS) as ex:
        list(ex.map(work, batches))

    return outs, errors


NATURAL_SYSTEM = (
    "You are a native Khmer dubbing scriptwriter. You do NOT translate; "
    "you RE-SAY what the speaker means, the way a real Cambodian person "
    "would say it out loud in that exact moment. "
    "You receive numbered subtitle lines. For each line you get the "
    "ORIGINAL text (source language), an optional DRAFT (a literal "
    "machine translation, often stiff or wrong: use it only as a hint "
    "for the meaning and NEVER copy its wording or word order), the "
    "time available in \"seconds\" and a hard limit \"max_chars\" "
    "(Khmer characters). "
    "Rules: (1) First understand the meaning, emotion and intention of "
    "the whole sentence using previous_lines and next_lines, then "
    "express it freely. Reorder, merge, split, add or drop words as "
    "needed; the result must not mirror the original sentence "
    "structure. (2) Sound like a real person talking: casual spoken "
    "Khmer, natural connecting words and sentence-final particles "
    "(for example ណា៎, ហើយ, ទៅ, ផង, ហ្នឹង, អញ្ចឹង, នោះ) used "
    "sparingly where a native speaker would really use them, with "
    "natural pronouns (ខ្ញុំ, អ្នក, ឯង, គាត់, យើង) chosen by the "
    "relationship and tone. Avoid stiff bookish or official words "
    "unless the speaker is formal. (3) Turn idioms, slang, jokes and "
    "exclamations into the Khmer way of reacting, not a copy. "
    "(4) Keep the same tone and energy (casual, angry, funny, "
    "emotional) and make consecutive lines flow like one conversation, "
    "with consistent names and pronouns. (5) The line will be read by "
    "a text-to-speech voice and must fit the time: stay within "
    "max_chars by choosing the gist and shorter natural wording, never "
    "by cutting a sentence in the middle. (6) Khmer script only. Names "
    "may be transliterated into Khmer. No digits, symbols, emojis, "
    "parentheses or quotation marks: write numbers as Khmer words. "
    "Return JSON {\"lines\": [...]} with exactly the same number of "
    "items as the input lines, in the same order."
)

SHORTEN_SYSTEM = (
    "You edit Khmer dubbing lines so they can be spoken in time. "
    "Each input line has a \"text\" and a \"max_chars\". Rewrite every "
    "line as natural spoken Khmer, the way a real person would say it, "
    "keeping the core meaning and tone, but with at most max_chars "
    "characters. Drop filler, merge ideas and rephrase; never cut the "
    "sentence in the middle. Khmer script only. "
    "Return JSON {\"lines\": [...]} with exactly the same number of "
    "items, in the same order."
)

_gemini_models_cache = {"key": None, "models": None}


def gemini_json_list(api_key, system, user_text, count):
    """ឱ្យ Gemini ឆ្លើយជាបញ្ជី JSON ដែលមានចំនួនបន្ទាត់ត្រូវគ្នា។"""
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )
    if (
        _gemini_models_cache["key"] != api_key
        or not _gemini_models_cache["models"]
    ):
        _gemini_models_cache["models"] = get_available_models(client)
        _gemini_models_cache["key"] = api_key
    models = _gemini_models_cache["models"] or []

    last = "មិនមានម៉ូដែល"
    all_quota = bool(models)
    for model in models[:4]:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=user_text,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        temperature=0.6,
                        response_mime_type="application/json",
                    ),
                )
                raw = (getattr(response, "text", None) or "").strip()
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
                data = json.loads(raw)
                if isinstance(data, dict):
                    data = data.get("lines") or data.get("translations") or []
                if isinstance(data, list) and len(data) == count:
                    return [
                        clean_translation(x) if isinstance(x, str) else None
                        for x in data
                    ]
                all_quota = False
                last = f"{model}: ចំនួនបន្ទាត់មិនត្រូវគ្នា"
                break
            except Exception as e:
                last = f"{model}: {e}"
                low = str(e).lower()
                if not ("429" in low or "resource_exhausted" in low):
                    all_quota = False
                if ("503" in low or "unavailable" in low) and attempt == 0:
                    time.sleep(3)
                    continue
                break
    if all_quota:
        mark_provider("gemini", last)
    raise RuntimeError(last[:300])


def char_limit(seconds):
    """ចំនួនតួអក្សរខ្មែរអតិបរមា ដែលអានទាន់ក្នុងរយៈពេលដែលមាន។"""
    return max(8, int(round((max(0.0, float(seconds)) + 0.3) * CHARS_PER_SEC)))


def ask_ai_list(system, payload, count, gemini_key, groq_key, errors,
                tag, temperature=0.5):
    """សួរ Gemini មុន បើមិនបានសួរ Groq។ ត្រឡប់បញ្ជី ឬ None។"""
    res = None
    if gemini_key and provider_alive("gemini"):
        try:
            res = gemini_json_list(gemini_key, system, payload, count)
        except Exception as e:
            mark_provider("gemini", e)
            errors.append(f"gemini-{tag}: {e}"[:200])
    if res is None and groq_key and provider_alive("groq"):
        try:
            res = groq_json_list(
                groq_key, system, payload, count, temperature
            )
        except Exception as e:
            mark_provider("groq", e)
            errors.append(f"groq-{tag}: {e}"[:200])
    return res


def naturalize_lines(originals, drafts, gemini_key, groq_key,
                     durations=None):
    """
    កែ (ឬបកប្រែ បើគ្មានសេចក្តីព្រាង) ឱ្យទៅជាភាសាខ្មែរនិយាយធម្មជាតិ
    ដូចមនុស្សនិយាយពិត ហើយឱ្យខ្លីល្មមនិយាយទាន់ក្នុងម៉ោងរបស់ឃ្លានីមួយៗ។
    ក្រុមទាំងអស់ត្រូវបានហៅស្មើគ្នា (លឿនជាងមុន)។
    ត្រឡប់ (លទ្ធផល, បញ្ជីមូលហេតុបរាជ័យ)។
    """
    n = len(drafts)
    out = list(drafts)
    errors = []

    if not (gemini_key or groq_key):
        return out, errors

    if durations is None:
        durations = [4.0] * n
    limits = [char_limit(d) for d in durations]

    # ជំហានទី១៖ សរសេរឡើងវិញ ក្នុងដែនកំណត់ម៉ោង (ក្រុមស្មើគ្នា)
    batches = [list(range(k, min(n, k + 25))) for k in range(0, n, 25)]

    def run_natural(idx):
        k = idx[0]
        context = []
        for j in range(max(0, k - 3), k):
            c = drafts[j] or str(originals[j]).strip()
            if c:
                context.append(c)
        upcoming = [
            str(originals[j]).strip()
            for j in range(idx[-1] + 1, min(n, idx[-1] + 3))
        ]
        payload = json.dumps(
            {
                "previous_lines": context,
                "next_lines": upcoming,
                "lines": [
                    {
                        "original": str(originals[i]).strip(),
                        "draft": drafts[i] or "",
                        "seconds": round(float(durations[i]), 1),
                        "max_chars": limits[i],
                    }
                    for i in idx
                ],
            },
            ensure_ascii=False,
        )
        res = ask_ai_list(
            NATURAL_SYSTEM, payload, len(idx),
            gemini_key, groq_key, errors, "natural", 0.7,
        )
        return idx, res

    with ThreadPoolExecutor(max_workers=LLM_WORKERS) as ex:
        for idx, res in ex.map(run_natural, batches):
            if res:
                for i, r in zip(idx, res):
                    if r and has_khmer(r):
                        out[i] = r

    # ជំហានទី២៖ ឃ្លាណាដែលនៅវែងពេក បង្រួមម្តងទៀត (ក្រុមស្មើគ្នា)
    long_idx = [
        i for i in range(n)
        if out[i] and len(out[i]) > limits[i] * 1.2
    ]
    sbatches = [long_idx[k:k + 25] for k in range(0, len(long_idx), 25)]

    def run_short(idx):
        payload = json.dumps(
            {
                "lines": [
                    {"text": out[i], "max_chars": limits[i]}
                    for i in idx
                ]
            },
            ensure_ascii=False,
        )
        res = ask_ai_list(
            SHORTEN_SYSTEM, payload, len(idx),
            gemini_key, groq_key, errors, "shorten", 0.4,
        )
        return idx, res

    if sbatches:
        with ThreadPoolExecutor(max_workers=LLM_WORKERS) as ex:
            for idx, res in ex.map(run_short, sbatches):
                if res:
                    for i, r in zip(idx, res):
                        if r and has_khmer(r) and len(r) < len(out[i]):
                            out[i] = r

    return out, errors


def fill_missing_translations(originals, outs, gemini_key, groq_key,
                              errors):
    """ឃ្លាណាដែលនៅទទេ → បកប្រែសាមញ្ញ ដោយ Gemini/Groq (ក្រុមស្មើគ្នា)។"""
    missing = [i for i, o in enumerate(outs) if not o]
    if not missing or not (gemini_key or groq_key):
        return outs

    batches = [missing[k:k + 25] for k in range(0, len(missing), 25)]

    def run(idx):
        numbered = "\n".join(
            f"{n + 1}. {str(originals[i]).strip()}"
            for n, i in enumerate(idx)
        )
        res = ask_ai_list(
            TRANSLATE_SYSTEM, numbered, len(idx),
            gemini_key, groq_key, errors, "translate", 0.2,
        )
        return idx, res

    with ThreadPoolExecutor(max_workers=LLM_WORKERS) as ex:
        for idx, res in ex.map(run, batches):
            if res:
                for i, r in zip(idx, res):
                    if r and has_khmer(r):
                        outs[i] = r
    return outs


def retime_by_speech(segs, speech, duration, pad=0.6):
    """
    ភាសាខ្មែរ៖ Whisper ផ្តល់ម៉ោងមិនសូវត្រូវ (ឃ្លាវែង ម៉ោងរសាត់)។
    ដូច្នេះចែកអក្សរក្នុងឃ្លានីមួយៗ តាមចន្លោះដែលមានសំឡេងនិយាយពិត
    (រំលងចន្លោះស្ងាត់) ជំនួសការចែកស្មើៗ។
    """
    if not speech or duration <= 0:
        return segs

    total_all = sum(b - a for a, b in speech)
    if total_all / duration >= 0.9 or total_all < 1.0:
        return segs  # ភ្លេងខ្លាំង/រកសំឡេងមិនបាន → ទុកម៉ោងដើម

    out = []
    for s, e, text in segs:
        pieces = split_display(text)
        if not pieces:
            continue

        # ចន្លោះសំឡេងក្នុងបង្អួចរបស់ឃ្លានេះ (ពង្រីកបន្តិច)
        lo, hi = max(0.0, s - pad), min(duration, e + pad)
        win = []
        for a, b in speech:
            a2, b2 = max(a, lo), min(b, hi)
            if b2 - a2 >= 0.1:
                win.append((a2, b2))
        win_total = sum(b - a for a, b in win)

        # សំឡេងតិចពេក → ចែកស្មើតាមម៉ោងដើម
        if win_total < 0.5:
            win = [(s, max(e, s + 0.4))]
            win_total = win[0][1] - win[0][0]

        def to_real(x, is_end):
            acc = 0.0
            for a, b in win:
                d = b - a
                if (x <= acc + d) if is_end else (x < acc + d):
                    return a + max(0.0, x - acc)
                acc += d
            return win[-1][1]

        weights = [max(1, len(p)) for p in pieces]
        total_w = float(sum(weights))
        cum = 0
        for piece, w in zip(pieces, weights):
            x0 = win_total * cum / total_w
            cum += w
            x1 = win_total * cum / total_w
            ps, pe = to_real(x0, False), to_real(x1, True)
            out.append((ps, max(pe, ps + 0.3), piece))

    out.sort(key=lambda x: x[0])
    return out or segs


def plan_short_chunks(duration, speech, target=10.0, limit=14.0):
    """កាត់សំឡេងជាផ្នែកខ្លីៗ ~10 វិនាទី ត្រង់ចន្លោះស្ងាត់។"""
    cuts = []
    for (a1, b1), (a2, b2) in zip(speech or [], (speech or [])[1:]):
        if a2 - b1 >= 0.15:
            cuts.append((b1 + a2) / 2.0)

    chunks = []
    start = 0.0
    while duration - start > limit:
        want = start + target
        cands = [c for c in cuts if start + 4.0 <= c <= start + limit]
        cut = min(cands, key=lambda c: abs(c - want)) if cands else want
        chunks.append((start, cut))
        start = cut
    chunks.append((start, duration))
    return chunks


def transcribe_khmer_chunks(groq_key, audio_path, duration, speech,
                            status):
    """
    ភាសាខ្មែរ៖ ផ្ញើទៅ Whisper ម្តងមួយផ្នែកខ្លីៗ (~10 វិនាទី)
    ដូច្នេះម៉ោងមិនអាចរសាត់ឆ្ងាយបាន។ ក្នុងផ្នែកនីមួយៗ ចែកអក្សរតាម
    ចន្លោះដែលមានសំឡេងនិយាយពិត។ (ធ្វើម្តងមួយ ដើម្បីកុំលើសកូតា Groq)
    """
    folder = os.path.dirname(audio_path)
    base = os.path.basename(audio_path)
    chunks = plan_short_chunks(duration, speech)
    out = []

    for i, (a, b) in enumerate(chunks):
        if b - a < 0.5:
            continue
        t0 = time.time()
        name = f"kchunk_{i}.mp3"
        try:
            run_ffmpeg(
                [
                    "-ss", f"{a:.3f}",
                    "-t", f"{b - a:.3f}",
                    "-i", base,
                    "-c:a", "libmp3lame", "-b:a", "64k",
                    name,
                ],
                cwd=folder,
            )
            data, _ = groq_transcribe(
                groq_key, os.path.join(folder, name), "km", status
            )

            texts = []
            for sg in data.get("segments") or []:
                text = fix_khmer(sg.get("text", ""))
                if not text or not has_khmer(text):
                    continue
                if (
                    float(sg.get("no_speech_prob", 0) or 0) > 0.6
                    and float(sg.get("avg_logprob", 0) or 0) < -0.8
                ):
                    continue
                texts.append(text)

            text = fix_khmer(" ".join(texts))
            if text:
                out.extend(
                    retime_by_speech(
                        [(a, b, text)], speech, duration, pad=0.0
                    )
                )
        except Exception:
            pass

        status.write(
            f"៣/៤ កំពុងស្តាប់ភាសាខ្មែរ... ({i + 1}/{len(chunks)})"
        )
        # កុំឱ្យលើសកូតា Groq ក្នុងមួយនាទី
        wait = 3.0 - (time.time() - t0)
        if wait > 0:
            time.sleep(wait)

    out.sort(key=lambda x: x[0])
    return out


# កូនសោសាធារណៈរបស់ Google Speech (ដូចក្នុងបណ្ណាល័យ speech_recognition)
GSPEECH_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"


def google_speech_request(flac_bytes, lang="km-KH"):
    """ស្តាប់សំឡេងខ្លីៗជាភាសាខ្មែរដោយ Google Speech (ឥតគិតថ្លៃ)។"""
    query = urllib.parse.urlencode(
        {
            "client": "chromium",
            "lang": lang,
            "key": GSPEECH_KEY,
            "pFilter": "0",
        }
    )
    request = urllib.request.Request(
        "https://www.google.com/speech-api/v2/recognize?" + query,
        data=flac_bytes,
        method="POST",
        headers={
            "Content-Type": "audio/x-flac; rate=16000",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        body = response.read().decode("utf-8", "ignore")

    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        results = obj.get("result") or []
        if results:
            alts = results[0].get("alternative") or []
            if alts:
                return fix_khmer(alts[0].get("transcript", ""))
    return ""


def transcribe_khmer_google(audio_path, duration, speech, status):
    """
    ភាសាខ្មែរ៖ កាត់ជាផ្នែក ~10 វិនាទី ត្រង់ចន្លោះស្ងាត់ ស្តាប់ដោយ
    Google Speech ស្មើគ្នាច្រើនផ្នែកក្នុងពេលតែមួយ (លឿនជាងមុនច្រើន)
    រួចចែកអក្សរតាមសំឡេងពិត។ មិនប្រើ Gemini ទេ។
    """
    folder = os.path.dirname(audio_path)
    base = os.path.basename(audio_path)
    chunks = [
        c for c in plan_short_chunks(duration, speech) if c[1] - c[0] >= 0.5
    ]
    total = len(chunks)
    texts = [None] * total
    stats = {"fail": 0, "done": 0}

    def work(i):
        a, b = chunks[i]
        name = f"gs_{i}.flac"
        try:
            run_ffmpeg(
                [
                    "-ss", f"{a:.3f}",
                    "-t", f"{b - a:.3f}",
                    "-i", base,
                    "-ac", "1", "-ar", "16000",
                    "-c:a", "flac",
                    name,
                ],
                cwd=folder,
            )
            with open(os.path.join(folder, name), "rb") as f:
                data = f.read()

            text = ""
            for attempt in range(2):
                try:
                    text = google_speech_request(data)
                    break
                except urllib.error.HTTPError as e:
                    if e.code in (429, 503) and attempt == 0:
                        time.sleep(3)
                        continue
                    raise
            texts[i] = text or ""
        except Exception:
            stats["fail"] += 1
        stats["done"] += 1
        status.write(
            f"៣/៤ កំពុងស្តាប់ភាសាខ្មែរ... ({stats['done']}/{total})"
        )

    with ThreadPoolExecutor(max_workers=GS_WORKERS) as ex:
        list(ex.map(work, range(total)))

    got = [i for i, t in enumerate(texts) if t]
    if not got:
        if stats["fail"] >= 3:
            raise RuntimeError("Google Speech ត្រូវបានរារាំង")
        return []

    out = []
    for i in got:
        a, b = chunks[i]
        out.extend(
            retime_by_speech([(a, b, texts[i])], speech, duration, pad=0.0)
        )
    out.sort(key=lambda x: x[0])
    return out


def transcribe_free(groq_key, audio_path, duration, source_language,
                    status, speech=None, gemini_key=None):
    """
    ស្តាប់ដោយ Groq Whisper រួចបកដោយ Google Translate (បម្រុង Gemini/Groq LLM)។
    ត្រឡប់ (segments, ឈ្មោះម៉ូដែល, ចំនួនឃ្លាបរាជ័យ)។
    """
    code = WHISPER_LANG.get(source_language) if source_language else None

    # ភាសាខ្មែរ៖ សាក Google Speech មុន (ល្អជាង Whisper)
    if source_language == "Khmer":
        try:
            gs = transcribe_khmer_google(
                audio_path, duration, speech or [], status
            )
        except Exception:
            gs = []
        if gs:
            return gs, "Google Speech (km-KH)", 0

    if not groq_key:
        raise RuntimeError("មិនមាន Groq API Key សម្រាប់ម៉ាស៊ីនឥតគិតថ្លៃ")

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
        segs = []
        if source_language != "Khmer":
            try:
                segs = transcribe_khmer_google(
                    audio_path, duration, speech or [], status
                )
            except Exception:
                segs = []
            if segs:
                return segs, "Google Speech (km-KH)", 0

        if not segs and duration > 12:
            try:
                segs = transcribe_khmer_chunks(
                    groq_key, audio_path, duration, speech or [], status
                )
            except Exception:
                segs = []

        if not segs:
            segs = [
                (s, e, fix_khmer(t)) for s, e, t in keep if has_khmer(t)
            ]
            segs = retime_by_speech(segs, speech, duration)
    else:
        originals = [t for _, _, t in keep]
        errs = []
        outs = [None] * len(originals)

        # ១) AI សរសេរឡើងវិញជាភាសាខ្មែរនិយាយធម្មជាតិ ពីអត្ថបទដើមដោយផ្ទាល់
        #    (មិនយកការបកត្រង់ៗរបស់ Google ជាមូលដ្ឋាន ដើម្បីកុំឱ្យស្តាប់ដូចម៉ាស៊ីន)
        if gemini_key or groq_key:
            status.write("៣/៤ កំពុងសរសេរជាភាសាខ្មែរនិយាយធម្មជាតិ...")
            try:
                outs, nat_errs = naturalize_lines(
                    originals,
                    outs,
                    gemini_key,
                    groq_key,
                    durations=[e - s for s, e, _ in keep],
                )
                errs += nat_errs
            except Exception as e:
                errs.append(f"natural: {e}"[:200])

            # ឃ្លាដែលនៅទទេ → AI បកប្រែសាមញ្ញម្តងទៀត
            outs = fill_missing_translations(
                originals, outs, gemini_key, groq_key, errs
            )

        # ២) Google Translate ជាម៉ាស៊ីនបម្រុងចុងក្រោយ (សម្រាប់ឃ្លាដែលនៅខ្វះ)
        missing = [i for i, o in enumerate(outs) if not o]
        if missing:
            status.write("៣/៤ កំពុងបកប្រែជាភាសាខ្មែរ...")
            g_outs, g_errs = translate_texts([originals[i] for i in missing])
            errs += g_errs
            for i, g in zip(missing, g_outs):
                if g:
                    outs[i] = g

        segs = []
        for (s, e, _), out in zip(keep, outs):
            if out:
                segs.append((s, e, out))
            else:
                failed += 1

        if not segs or failed > len(keep) * 0.5:
            reason = " | ".join(errs[:3]) or "មិនស្គាល់មូលហេតុ"
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


def shorten_batch(gemini_key, groq_key, items, rate=CHARS_PER_SEC):
    """
    បង្រួមប្រយោគខ្មែរច្រើនឃ្លាក្នុងការហៅ AI តែម្តងក្នុងមួយក្រុម (ស្មើគ្នា)។
    items = [(អត្ថបទ, វិនាទីដែលមាន)] → បញ្ជីអត្ថបទថ្មី (ឬដដែលបើបរាជ័យ)។
    """
    out = [t for t, _ in items]
    limits = [max(6, int(sec * rate)) for _, sec in items]
    idx_all = [i for i in range(len(items)) if len(out[i]) > limits[i]]
    batches = [idx_all[k:k + 25] for k in range(0, len(idx_all), 25)]
    errors = []

    def run(idx):
        payload = json.dumps(
            {
                "lines": [
                    {"text": out[i], "max_chars": limits[i]} for i in idx
                ]
            },
            ensure_ascii=False,
        )
        res = ask_ai_list(
            SHORTEN_SYSTEM, payload, len(idx),
            gemini_key, groq_key, errors, "dubshort", 0.4,
        )
        return idx, res

    if batches:
        with ThreadPoolExecutor(max_workers=LLM_WORKERS) as ex:
            for idx, res in ex.map(run, batches):
                if res:
                    for i, r in zip(idx, res):
                        if r and has_khmer(r) and len(r) < len(out[i]):
                            out[i] = r
    return out


# ---------- ស្គាល់សំឡេងប្រុស/ស្រី តាមអ្នកនិយាយ ----------

VOICE_MALE = "km-KH-PisethNeural"
VOICE_FEMALE = "km-KH-SreymomNeural"

BIN = 0.1  # វិនាទី (ទំហំបង្អួចនៃការបែងចែកអ្នកនិយាយ)
MIN_TURN = 0.8  # អ្នកនិយាយប្តូរខ្លីជាងនេះ ត្រូវបានរួមចូលអ្នកជិតខាង


def load_pcm(path):
    """ដកសំឡេងទាំងមូលជាលេខ (16kHz mono) ដើម្បីវាស់កម្រិតសំឡេង។"""
    import numpy as np

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [exe, "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    data = np.frombuffer(result.stdout, dtype=np.int16)
    return data.astype(np.float32) / 32768.0


def pitch_track(samples, sr=16000):
    """
    វាស់កម្រិតសំឡេង (Hz) គ្រប់ ២០ms លើសំឡេងទាំងមូល។
    ត្រឡប់ (ម៉ោង, f0, ថាមពល)។ f0 = 0 ពេលមិនមែនសំឡេងមនុស្សនិយាយ។
    """
    import numpy as np

    n = int(0.04 * sr)  # ស៊ុមវែង ៤០ms
    hop = int(0.02 * sr)  # រំកិលម្តង ២០ms
    lag_min = int(sr / 400)  # 400Hz
    lag_max = int(sr / 70)  # 70Hz

    empty = np.array([])
    if len(samples) < n * 3:
        return empty, empty, empty

    count = 1 + (len(samples) - n) // hop
    times = (np.arange(count) * hop + n / 2) / sr
    f0 = np.zeros(count, dtype=np.float64)
    rms = np.zeros(count, dtype=np.float64)
    peaks = np.zeros(count, dtype=np.float64)

    lags = np.arange(n)
    overlap_fix = n / np.maximum(n - lags, 1)  # ជំនួសការធ្លាក់នៃ autocorr

    step = 1500
    for b0 in range(0, count, step):
        b1 = min(count, b0 + step)
        idx = (np.arange(b0, b1) * hop)[:, None] + np.arange(n)[None, :]
        frames = samples[idx].astype(np.float64)

        rms[b0:b1] = np.sqrt(np.mean(frames ** 2, axis=1))
        frames = frames - frames.mean(axis=1, keepdims=True)

        spec = np.fft.rfft(frames, 2 * n, axis=1)
        ac = np.fft.irfft(spec * np.conj(spec), axis=1)[:, :n]
        ac = ac / np.maximum(ac[:, :1], 1e-9)
        ac = ac * overlap_fix[None, :]

        seg = ac[:, lag_min - 1:lag_max + 2]
        core = seg[:, 1:-1]
        is_peak = (core >= seg[:, :-2]) & (core >= seg[:, 2:])
        pk = core.max(axis=1)

        # យកកំពូលតូចបំផុត (ប្រេកង់គោល) ដែលខ្លាំងជិតកំពូលធំបំផុត
        cand = is_peak & (core >= 0.9 * pk[:, None])
        first = np.argmax(cand, axis=1)
        lag = lag_min + first

        f0[b0:b1] = sr / np.maximum(lag, 1)
        peaks[b0:b1] = core[np.arange(len(first)), first]

    thr = max(0.004, 0.12 * float(np.percentile(rms, 95)))
    voiced = (rms >= thr) & (peaks >= 0.45)
    f0 = np.where(voiced, f0, 0.0)
    return times, f0, rms


def median_pitch(info, a, b):
    """កម្រិតសំឡេងកណ្តាល (Hz) ក្នុងចន្លោះម៉ោង a-b។"""
    import numpy as np

    t = info.get("times")
    f = info.get("f0")
    if t is None or len(t) == 0:
        return None
    m = (t >= a) & (t <= b) & (f > 0)
    if int(m.sum()) < 3:
        return None
    return float(np.median(f[m]))


def merge_short_runs(runs, min_len):
    """រួមចន្លោះខ្លីពេកចូលអ្នកជិតខាងដែលវែងជាង ហើយបូកចន្លោះដែលដូចគ្នា។"""
    runs = [list(r) for r in runs]
    while len(runs) > 1:
        idx = min(range(len(runs)), key=lambda k: runs[k][1] - runs[k][0])
        if runs[idx][1] - runs[idx][0] >= min_len:
            break

        left = runs[idx - 1] if idx > 0 else None
        right = runs[idx + 1] if idx < len(runs) - 1 else None
        if left is not None and right is not None:
            if (left[1] - left[0]) >= (right[1] - right[0]):
                target = left
            else:
                target = right
        else:
            target = left if left is not None else right

        if target is left:
            left[1] = runs[idx][1]
        else:
            right[0] = runs[idx][0]
        runs.pop(idx)

        merged = [runs[0]]
        for r in runs[1:]:
            if r[2] == merged[-1][2]:
                merged[-1][1] = r[1]
            else:
                merged.append(r)
        runs = merged
    return runs


def gender_timeline(pcm, duration, default_voice, sr=16000):
    """
    វិភាគសំឡេងទាំងមូល ដើម្បីដឹងថាអ្នកណានិយាយនៅពេលណា (ប្រុស M / ស្រី F)។
    ១) វាស់កម្រិតសំឡេងគ្រប់ស៊ុម
    ២) បែងជា ២ ក្រុមដោយខ្លួនឯង (k-means លើ log-pitch) មិនប្រើតួលេខថេរ
    ៣) បើមានក្រុមតែមួយ → អ្នកនិយាយម្នាក់ សំឡេងតែមួយពេញវីដេអូ
    ត្រឡប់ (runs, info)។ runs = [(ចាប់ផ្តើម, បញ្ចប់, "M"/"F")]
    """
    import numpy as np

    times, f0, _ = pitch_track(pcm, sr)
    info = {"times": times, "f0": f0, "summary": ""}

    mask = f0 > 0
    if int(mask.sum()) < 25:
        info["summary"] = (
            "វាស់កម្រិតសំឡេងមិនបាន (សំឡេងតិច ឬមានតែភ្លេង) "
            "ប្រើសំឡេងដែលបានជ្រើស"
        )
        return None, info

    tv = times[mask]
    hz = f0[mask]
    lg = np.log2(hz)

    # k-means ២ ក្រុម
    c0 = float(np.percentile(lg, 20))
    c1 = float(np.percentile(lg, 80))
    for _ in range(30):
        hi = np.abs(lg - c1) < np.abs(lg - c0)
        if hi.all() or (~hi).all():
            break
        n0 = float(lg[~hi].mean())
        n1 = float(lg[hi].mean())
        done = abs(n0 - c0) < 1e-4 and abs(n1 - c1) < 1e-4
        c0, c1 = n0, n1
        if done:
            break
    hi = np.abs(lg - c1) < np.abs(lg - c0)

    n_hi = int(hi.sum())
    n_lo = int(len(lg) - n_hi)
    hz0, hz1 = float(2 ** c0), float(2 ** c1)

    two = False
    single = None
    g0 = g1 = None
    if n_hi >= 30 and n_lo >= 30 and c1 > c0:
        s0 = float(lg[~hi].std())
        s1 = float(lg[hi].std())
        sep = (c1 - c0) / (0.5 * (s0 + s1) + 1e-6)
        if hz1 / hz0 >= 1.3 and sep >= 2.0:
            g0 = "M" if hz0 < 175 else "F"
            g1 = "F" if hz1 >= 165 else "M"
            if g0 != g1:
                two = True
            else:
                single = g0  # ទាំងពីរក្រុមភេទដូចគ្នា (ឧ. ប្រុសពីរនាក់)

    if not two and single is None:
        med = float(np.median(hz))
        if med < 150:
            single = "M"
        elif med > 190:
            single = "F"
        else:
            single = "M" if default_voice == VOICE_MALE else "F"
            info["summary"] = (
                f"កម្រិតសំឡេង ~{int(med)}Hz មិនច្បាស់ ប្រើសំឡេងដែលបានជ្រើស"
            )

    names = {"M": "ប្រុស", "F": "ស្រី"}

    if not two:
        med = float(np.median(hz))
        if not info["summary"]:
            info["summary"] = (
                f"ស្គាល់ឃើញអ្នកនិយាយ ១ នាក់៖ {names[single]} (~{int(med)}Hz)"
            )
        return [(0.0, duration + 1.0, single)], info

    # ដាក់ស្លាកក្នុងបង្អួច ០.១ វិនាទី
    nb = int(duration / BIN) + 2
    isf = np.where(
        hi,
        1 if g1 == "F" else 0,
        1 if g0 == "F" else 0,
    )
    bins = np.minimum((tv / BIN).astype(int), nb - 1)
    vf = np.zeros(nb)
    vm = np.zeros(nb)
    np.add.at(vf, bins, isf)
    np.add.at(vm, bins, 1 - isf)

    lab = np.full(nb, -1, dtype=int)
    lab[vf > vm] = 1
    lab[vm > vf] = 0

    # បំពេញបង្អួចដែលគ្មានសំឡេង ដោយយកតម្លៃជិតបំផុត
    last = -1
    for i in range(nb):
        if lab[i] >= 0:
            last = lab[i]
        elif last >= 0:
            lab[i] = last
    nxt = -1
    for i in range(nb - 1, -1, -1):
        if lab[i] >= 0:
            nxt = lab[i]
        elif nxt >= 0:
            lab[i] = nxt

    # រលោងដោយ median ៥ បង្អួច (០.៥ វិនាទី)
    pad = np.pad(lab, 2, mode="edge")
    sm = np.array([1 if pad[i:i + 5].sum() >= 3 else 0 for i in range(nb)])

    runs = []
    start = 0
    for i in range(1, nb + 1):
        if i == nb or sm[i] != sm[start]:
            runs.append([start * BIN, i * BIN, "F" if sm[start] else "M"])
            start = i

    runs = merge_short_runs(runs, MIN_TURN)
    runs[-1][1] = max(runs[-1][1], duration + 1.0)

    hz_m = hz0 if g0 == "M" else hz1
    hz_f = hz0 if g0 == "F" else hz1
    info["summary"] = (
        "ស្គាល់ឃើញអ្នកនិយាយ ២ នាក់៖ "
        f"ប្រុស (~{int(hz_m)}Hz) និងស្រី (~{int(hz_f)}Hz) "
        f"ប្តូរអ្នកនិយាយ {len(runs) - 1} ដង"
    )
    return [(a, b, g) for a, b, g in runs], info


def safe_cut(text, pos):
    """រកកន្លែងកាត់អត្ថបទជិត pos (ត្រង់ដកឃ្លា ឬមិនបំបែកព្យញ្ជនៈជើង/ស្រៈ)។"""
    n = len(text)
    pos = max(0, min(n, pos))

    for d in range(0, 9):
        for p in (pos - d, pos + d):
            if 0 < p < n and text[p] == " ":
                return p

    p = pos
    while 0 < p < n and (
        "\u17B6" <= text[p] <= "\u17D3" or text[p - 1] == "\u17D2"
    ):
        p -= 1
    return p


def split_text_by_shares(text, shares):
    """ចែកអត្ថបទជាច្រើនផ្នែក តាមសមាមាត្រពេលវេលា។"""
    text = fix_khmer(text)
    n = len(text)
    total = float(sum(shares)) or 1.0

    cuts = []
    acc = 0.0
    for sh in shares[:-1]:
        acc += sh
        cuts.append(safe_cut(text, int(round(n * acc / total))))

    pieces = []
    prev = 0
    for c in cuts + [n]:
        c = max(c, prev)
        pieces.append(fix_khmer(text[prev:c]))
        prev = c
    return pieces


def split_by_speaker(segments, runs, default_voice):
    """
    បំបែកឃ្លានីមួយៗ ត្រង់កន្លែងដែលអ្នកនិយាយប្តូរ (ប្រុស ↔ ស្រី)។
    ត្រឡប់ [(ចាប់ផ្តើម, បញ្ចប់, អត្ថបទ, សំឡេង)]
    """
    voice_of = {"M": VOICE_MALE, "F": VOICE_FEMALE}
    out = []

    for s, e, text in segments:
        parts = []
        for rs, re_, g in runs:
            a, b = max(s, rs), min(e, re_)
            if b - a > 0.01:
                parts.append([a, b, g])

        if not parts:
            out.append((s, e, text, default_voice))
            continue

        parts = merge_short_runs(parts, 0.6)

        if len(parts) == 1:
            out.append((s, e, text, voice_of[parts[0][2]]))
            continue

        shares = [p[1] - p[0] for p in parts]
        pieces = split_text_by_shares(text, shares)
        for (a, b, g), piece in zip(parts, pieces):
            if piece:
                out.append((a, b, piece, voice_of[g]))

    return out


def plan_dub_voices(segments, pcm, default_voice, duration):
    """
    ត្រឡប់ (ឃ្លាបន្ទាប់ពីបំបែក [(s,e,text,voice)], បន្ទាត់បង្ហាញ, info)។
    """
    runs, info = gender_timeline(pcm, duration, default_voice)
    if runs is None:
        return (
            [(s, e, t, default_voice) for s, e, t in segments],
            [],
            info,
        )

    dub = split_by_speaker(segments, runs, default_voice)

    lines = []
    for a, b, t, v in dub:
        hz = median_pitch(info, a, b)
        mark = "♂" if v == VOICE_MALE else "♀"
        lines.append(f"{mark} {int(hz) if hz else '?'}Hz  {t}")
    return dub, lines, info


def make_dub(folder, segments, voice, duration, keep_bg, gemini_key,
             groq_key, seg_voices=None):
    """
    បង្កើត dub.wav ពីអត្ថបទខ្មែរ ឱ្យត្រូវតាមម៉ោងនីមួយៗនៃវីដេអូដើម។
    លឿន៖ បង្កើតសំឡេងអានគ្រប់ឃ្លាស្មើគ្នា (TTS_WORKERS thread)
    ឃ្លាណាអានវែងជាងពេលដែលមាន → បង្រួមជាក្រុមតែម្តងដោយ AI
    រួចអានឡើងវិញស្មើគ្នា ហើយទើបបង្កើនល្បឿនបន្តិច (មិនលើស MAX_DUB_SPEED)។
    """
    n_seg = len(segments)
    if n_seg == 0:
        return False

    texts = [t for _, _, t in segments]
    voices_for = [
        seg_voices[i] if seg_voices else voice for i in range(n_seg)
    ]
    paths = [os.path.join(folder, f"tts_{i}.mp3") for i in range(n_seg)]
    durs = [None] * n_seg

    # ពេលវេលាដែលមានសម្រាប់ឃ្លានីមួយៗ (ប៉ាន់ស្មាន មិនទាន់គិតការជាន់គ្នា)
    nominal = []
    for i, (s, e, _) in enumerate(segments):
        next_s = segments[i + 1][0] if i + 1 < n_seg else duration
        nominal.append(max(0.5, min(next_s - 0.05, e + 0.4) - s))

    def synth(i):
        try:
            tts_segment(texts[i], voices_for[i], paths[i])
            durs[i] = probe_video(paths[i])[0]
        except Exception:
            durs[i] = None

    # ជំហានទី១៖ បង្កើតសំឡេងអានទាំងអស់ស្មើគ្នា
    with ThreadPoolExecutor(max_workers=TTS_WORKERS) as ex:
        list(ex.map(synth, range(n_seg)))

    # ជំហានទី២៖ វាស់ល្បឿនអានពិតរបស់សំឡេង AI រួចបង្រួមឃ្លាដែលវែងជាងពេលដែលមាន
    # (ធ្វើ ២ ជុំ) ដើម្បីឱ្យចប់ទាន់មាត់អ្នកនិយាយ មិនបាច់បង្កើនល្បឿនខ្លាំង
    if gemini_key or groq_key:
        for _round in range(2):
            rates = [
                len(texts[i]) / durs[i]
                for i in range(n_seg)
                if durs[i] and durs[i] > 0.4 and len(texts[i]) >= 6
            ]
            rate = (
                sorted(rates)[len(rates) // 2] if rates else CHARS_PER_SEC
            )
            rate = max(6.0, min(16.0, rate))

            long_idx = [
                i for i in range(n_seg)
                if durs[i] and durs[i] > nominal[i] * 1.05
            ]
            if not long_idx:
                break
            new = shorten_batch(
                gemini_key,
                groq_key,
                [(texts[i], nominal[i]) for i in long_idx],
                rate=rate * 0.95,
            )
            changed = []
            for i, t2 in zip(long_idx, new):
                if t2 != texts[i]:
                    texts[i] = t2
                    changed.append(i)
            if not changed:
                break
            with ThreadPoolExecutor(max_workers=TTS_WORKERS) as ex:
                list(ex.map(synth, changed))

    # ជំហានទី៣៖ រៀបម៉ោង និងលាយសំឡេង
    inputs, filters = [], []
    n = 0

    if keep_bg:
        inputs += ["-i", "audio.mp3"]
        filters.append("[0:a]volume=0.15[bg]")
        n = 1

    first_voice = n
    voices = 0
    cursor = 0.0  # ម៉ោងដែលឃ្លាមុនអានចប់ (កុំឱ្យសំឡេងជាន់គ្នា)

    for i, (s, e, _) in enumerate(segments):
        d = durs[i]
        if not d:
            continue
        next_s = segments[i + 1][0] if i + 1 < n_seg else duration
        start = max(s, cursor)
        if start >= duration - 0.3:
            break
        slot = max(0.5, min(next_s - 0.05, e + 0.4) - start)

        speed = min(MAX_DUB_SPEED, max(1.0, d / slot))
        delay = int(start * 1000)
        cursor = start + d / speed + 0.08

        inputs += ["-i", f"tts_{i}.mp3"]
        filters.append(
            f"[{n}:a]atempo={speed:.3f},adelay={delay}:all=1[a{n}]"
        )
        n += 1
        voices += 1

    if voices == 0:
        return False

    labels = "[bg]" if keep_bg else ""
    labels += "".join(f"[a{k}]" for k in range(first_voice, n))

    # កុំឱ្យកន្ទុយសំឡេងឮខ្លាំង៖ មិនបង្កើនកម្រិតពេលសំឡេងខ្លះអស់ + កម្រិតកំពូល + ស្រាលចុះចុងក្រោយ
    fade_start = max(0.0, duration - 0.6)
    tail = (
        f"alimiter=limit=0.95,afade=t=out:st={fade_start:.2f}:d=0.6[out]"
    )

    # វិធីទី១ (ត្រឹមត្រូវបំផុត): amix មិនធ្វើ normalize
    fc_a = (
        ";".join(filters)
        + f";{labels}amix=inputs={n}:dropout_transition=0:normalize=0,{tail}"
    )
    # វិធីទី២ (ជំនួយ ffmpeg ចាស់): បន្ថែមស្ងាត់ឱ្យគ្រប់ឆានែលវែងស្មើគ្នា
    padded = [
        re.sub(
            r"\[(\w+)\]$",
            f",apad=whole_dur={duration:.2f}[\\1]",
            f_,
        )
        for f_ in filters
    ]
    fc_b = (
        ";".join(padded)
        + f";{labels}amix=inputs={n}:dropout_transition=0,"
        f"volume={n},{tail}"
    )

    ok = False
    for fc in (fc_a, fc_b):
        try:
            run_ffmpeg(
                inputs + [
                    "-filter_complex", fc,
                    "-map", "[out]",
                    "-t", f"{duration:.2f}",
                    "dub.wav",
                ],
                cwd=folder,
            )
            ok = True
            break
        except RuntimeError:
            continue
    return ok and os.path.exists(os.path.join(folder, "dub.wav"))


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
                      color, vid_w, vid_h, quality, status, dub=False,
                      alignment=(2, 35)):
    """
    Render វីដេអូ ហើយពិនិត្យថា Font ខ្មែរត្រូវបានប្រើពិតឬទេ។
    បើមិនបាន សាកវិធី ឬ Font ផ្សេងបន្ត។
    លឿន៖ ប្រើ fontconfig ផ្ទាល់ខ្លួនតាំងពីដំបូង (កុំ render ទ្វេដង)
    """
    ass_path = os.path.join(folder, "captions.ass")
    output_path = os.path.join(folder, "output.mp4")
    max_side, crf, preset = quality
    align, margin_v = alignment

    conf_env = make_fontconfig_env(folder)

    # (លេខ Font, ប្រើ fontconfig ផ្ទាល់ខ្លួនឬទេ)
    plan = [(0, True)]
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
            color, vid_w, vid_h, align, margin_v,
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
            "-threads", "0",
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
        "voice_lines": [],
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
                                speech=speech,
                                gemini_key=settings["gemini_key"],
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
                        if DEBUG:
                            item["warn"].append(
                                "ម៉ាស៊ីនទីមួយមានបញ្ហា "
                                "កម្មវិធីបានប្តូរទៅម៉ាស៊ីនបម្រុងដោយស្វ័យប្រវត្តិ។"
                                f"\n\nមូលហេតុ → {reason}"
                            )
                        rep.write("កំពុងប្តូរទៅម៉ាស៊ីនបម្រុង...")

            if segments is None:
                joined = "\n\n".join(engine_errors)
                low = joined.lower()
                if any(
                    k in low
                    for k in ("429", "quota", "per day", "resource_exhausted")
                ):
                    msg = (
                        "កូតាឥតគិតថ្លៃនៃសេវាបកប្រែអស់ជាបណ្តោះអាសន្ន។ "
                        "សូមរង់ចាំ ១០-៣០ នាទី រួចសាកម្តងទៀត "
                        "ឬប្តូរទៅម៉ាស៊ីន Gemini។"
                    )
                else:
                    msg = (
                        "ការបង្កើតវីដេអូមិនបានសម្រេច។ "
                        "សូមរង់ចាំមួយភ្លែត រួចសាកម្តងទៀត។"
                    )
                err = UserError(msg)
                err.detail = joined
                raise err

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
                    dub_segments = segments
                    seg_voices = None

                    if settings["auto_gender"]:
                        try:
                            rep.write("🔍 កំពុងស្គាល់អ្នកនិយាយប្រុស/ស្រី...")
                            pcm = load_pcm(master_path)
                            planned, lines, voice_info = plan_dub_voices(
                                segments,
                                pcm,
                                settings["voice"],
                                duration,
                            )
                            dub_segments = [
                                (s, e, t) for s, e, t, _ in planned
                            ]
                            seg_voices = [v for _, _, _, v in planned]
                            item["voice_lines"] = (
                                [voice_info.get("summary", "")] + lines
                            )
                        except Exception:
                            dub_segments = segments
                            seg_voices = None
                            item["warn"].append(
                                "ស្គាល់សំឡេងប្រុស/ស្រីមិនបាន "
                                "ប្រើសំឡេងតែមួយតាមដែលបានជ្រើស។"
                            )
                        rep.write("🎙 កំពុងបង្កើតសំឡេងខ្មែរ...")

                    dub_ok = make_dub(
                        folder,
                        dub_segments,
                        settings["voice"],
                        duration,
                        settings["keep_bg"],
                        settings["gemini_key"],
                        settings["groq_key"],
                        seg_voices=seg_voices,
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
                    alignment=settings["alignment"],
                )

            # ព្រមានបើ Font ដែលបានជ្រើសមិនត្រូវបានប្រើ
            if settings.get("font_warn"):
                item["warn"].append(settings["font_warn"])
            else:
                wanted = get_font_family(*fonts[0])
                if used_font != wanted:
                    item["warn"].append(
                        f"ពុម្ពអក្សរ {settings['font_name']} "
                        f"មិនអាចប្រើក្នុងវីដេអូបានទេ ប្រើ {used_font} ជំនួស។"
                    )

            item["video"] = video
            item["captions"] = [t for _, _, t in captions]
            item["debug"] = {
                "ម៉ាស៊ីន": used_engine,
                "ម៉ូដែល": used_model,
                "ការតម្រឹម": sync_mode,
                "ផ្នែកបរាជ័យ": failed_chunks,
                "Font ដែលជ្រើស": settings.get("font_name", ""),
                "Font ដែលប្រើ": used_font,
                "Dubbing": dub_ok,
                "អ្នកនិយាយ": (
                    item["voice_lines"][0] if item["voice_lines"] else ""
                ),
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
        item["raw_error"] = getattr(error, "detail", None) or str(error)
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


# ---------- សំឡេងគំរូ (សាកស្តាប់) ----------

@st.cache_data(show_spinner=False, max_entries=20)
def voice_sample(text, voice):
    """បង្កើតសំឡេងគំរូខ្លីៗ ដើម្បីសាកស្តាប់ មុនជ្រើសសំឡេង Dubbing។"""
    path = os.path.join(tempfile.gettempdir(), f"vs_{uuid.uuid4().hex}.mp3")
    try:
        tts_segment(text, voice, path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


# ---------- រចនាប័ទ្ម (CSS) ----------

CSS = """
html body .stApp,
html body .stApp button,
html body .stApp input,
html body .stApp textarea {
  font-family: 'Noto Sans Khmer', 'Inter', system-ui, sans-serif;
}
:root {
  --bg: #070b26;
  --card: #0d1236;
  --card2: #131a4a;
  --line: #1e2a66;
  --blue: #2f6bff;
  --blue2: #4f8cff;
  --txt: #e8ecff;
  --mut: #8f9ac8;
}
.stApp {
  background: radial-gradient(1200px 600px at 20% -10%, #14205f 0%, #070b26 55%) fixed;
  color: var(--txt);
}
header[data-testid="stHeader"] { background: transparent; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stToolbar"] { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
.stDeployButton { display: none; }
.block-container {
  max-width: 1180px;
  padding-top: 1.2rem;
  padding-bottom: 4rem;
}
.stApp p, .stApp label, .stApp li { color: var(--txt); }
[data-testid="stCaptionContainer"] { color: var(--mut); }

/* ក្បាលកម្មវិធី */
.hero {
  background: linear-gradient(180deg, #131b52 0%, #0d1438 100%);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 14px 20px 12px 20px;
  margin-bottom: 14px;
}
.hero-t {
  font-size: 1.9rem;
  font-weight: 800;
  line-height: 1.5;
  background: linear-gradient(90deg, #3a74ff, #8fb4ff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.hero-s { color: var(--mut); font-size: 0.9rem; }

/* ប្រអប់ណែនាំ + ប៊ូតុងពេញអេក្រង់ (ខាងលើ) */
.tip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  background: #0f1744;
  border: 1px solid #26327f;
  border-radius: 14px;
  padding: 10px 16px;
  margin: 0 0 12px 0;
}
.tip-t {
  color: #cfd6ff;
  font-size: 0.92rem;
  line-height: 1.7;
  flex: 1 1 320px;
}
.tip-t b { color: #ffffff; }
#kac-fs-slot { flex: 0 0 auto; }

/* ផ្ទាំងម៉ឺនុយ (tabs) */
[data-baseweb="tab-list"] {
  gap: 10px;
  flex-wrap: wrap;
  background: transparent;
  border: 0;
  padding-bottom: 6px;
}
button[data-baseweb="tab"] {
  background: #10174a;
  border: 1px solid #232f78;
  border-radius: 12px;
  padding: 10px 16px;
  height: auto;
  color: #cfd6ff;
}
button[data-baseweb="tab"][aria-selected="true"] {
  background: linear-gradient(180deg, #3b78ff, #2457e6);
  border-color: #5b92ff;
  color: #ffffff;
}
button[data-baseweb="tab"] p { color: inherit; }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {
  display: none;
}

/* ក្បាលផ្នែក */
.sec {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 18px 0 10px 0;
}
.sec .bar {
  width: 5px;
  height: 26px;
  border-radius: 4px;
  background: var(--blue);
}
.sec .sec-th { font-size: 1.25rem; font-weight: 800; color: #ffffff; }
.sec .sec-en { font-size: 1.1rem; font-weight: 600; color: var(--mut); }
.ct { font-size: 1.05rem; font-weight: 800; color: #ffffff; margin-bottom: 6px; }

/* កាត (cards) */
div[class*="st-key-card_"] {
  background: var(--card);
  border: 1px solid var(--line) !important;
  border-radius: 16px;
  padding: 8px 6px;
}

/* ប៊ូតុងជ្រើស (radio) ជារាងថ្នាំ */
div[role="radiogroup"] { gap: 10px !important; flex-wrap: wrap; }
div[role="radiogroup"] > label {
  background: #121a4d;
  border: 1px solid #26327f;
  border-radius: 12px;
  padding: 8px 16px 8px 12px;
  margin: 0 !important;
}
div[role="radiogroup"] > label:has(input:checked) {
  background: linear-gradient(180deg, #3b78ff, #2557e8);
  border-color: #5b92ff;
}

/* ប្រអប់បញ្ចូល */
[data-baseweb="select"] > div,
.stTextArea textarea,
.stTextInput input {
  background: #0a1030 !important;
  border: 1px solid var(--line) !important;
  border-radius: 10px !important;
  color: var(--txt) !important;
}
[data-baseweb="popover"] ul, [data-baseweb="menu"] { background: #10174a; }
[data-testid="stFileUploaderDropzone"] {
  background: #0a1030;
  border: 1.5px dashed #3a5bff;
  border-radius: 14px;
}

/* ប៊ូតុង */
button[data-testid="stBaseButton-primary"], button[kind="primary"] {
  background: linear-gradient(180deg, #3b78ff, #2457e6);
  border: 1px solid #5b92ff;
  color: #ffffff;
  border-radius: 12px;
  font-weight: 700;
}
button[data-testid="stBaseButton-secondary"], button[kind="secondary"] {
  background: #131a4a;
  border: 1px solid #26327f;
  color: var(--txt);
  border-radius: 12px;
}
button:disabled { opacity: 0.7; }

/* ស្ថានភាពបង្រួម */
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 2px 0 8px 0; }
.chip {
  background: #10174a;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 0.95rem;
  color: #cfd6ff;
}
.chip b { color: #ffffff; margin-left: 4px; font-size: 1.05rem; }
.chip.ok { border-color: #1f6b46; }
.chip.bad { border-color: #7a2a3a; }

/* មើលជាមុន (Preview) */
.pv {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 12px;
  overflow: hidden;
  background: linear-gradient(180deg, #27418f 0%, #1a2a66 60%, #0f1a45 100%);
  container-type: size;
}
.pv-sun {
  position: absolute;
  left: 50%;
  top: 14%;
  width: 18%;
  aspect-ratio: 1;
  border-radius: 50%;
  transform: translateX(-50%);
  background: radial-gradient(circle at 35% 30%, #ffd36b, #f59e0b);
}
.pv-cap {
  position: absolute;
  left: 0;
  right: 0;
  text-align: center;
  line-height: 1.4;
  padding: 0 6%;
}

/* ជម្រើស Font */
.fp {
  font-size: 1.5rem;
  line-height: 1.7;
  padding: 10px 12px;
  margin: 6px 0 10px 0;
  border-radius: 10px;
  background: #0a1030;
  border: 1px solid var(--line);
  color: #ffffff;
  text-align: center;
}
.fn { font-weight: 800; color: #ffffff; }
.fd { color: var(--mut); font-size: 0.85rem; }
"""


def inject_css():
    imports = "".join(
        "@import url('https://fonts.googleapis.com/css2?family="
        + n.replace(" ", "+")
        + "&display=swap');"
        for n in FONT_NAMES
    )
    base = (
        "@import url('https://fonts.googleapis.com/css2?"
        "family=Noto+Sans+Khmer:wght@400;600;800&display=swap');"
    )
    st.markdown(
        "<style>" + base + imports + CSS + "</style>",
        unsafe_allow_html=True,
    )


def section(th, en):
    st.markdown(
        '<div class="sec"><span class="bar"></span>'
        f'<span class="sec-th">{th}</span>'
        f'<span class="sec-en">{en}</span></div>',
        unsafe_allow_html=True,
    )


def card_title(icon, th, en):
    st.markdown(
        f'<div class="ct">{icon} {th} · {en}</div>',
        unsafe_allow_html=True,
    )


def card(name):
    return st.container(border=True, key="card_" + name)


def preview_html(text, family, font_size, outline, color_hex, pos):
    size = font_size / 288 * 100
    stroke = outline * 0.7
    place = {
        "bottom": "bottom:9%;",
        "middle": "top:50%;transform:translateY(-50%);",
        "top": "top:9%;",
    }.get(pos, "bottom:9%;")
    return (
        '<div class="pv"><div class="pv-sun"></div>'
        f'<div class="pv-cap" style="font-family:\'{family}\',sans-serif;'
        f"font-size:{size:.2f}cqh;color:{color_hex};"
        f"-webkit-text-stroke:{stroke:.2f}cqh #000;"
        f'paint-order:stroke fill;{place}">{html_escape(text)}</div></div>'
    )


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


def short_name(name, limit=34):
    name = str(name)
    return name if len(name) <= limit else name[: limit - 1] + "…"


def work_area(job, was_running):
    """ផ្នែកកន្លែងធ្វើការ៖ ស្ថានភាព (បង្រួម) មើលវីដេអូ និងប៊ូតុងទាញយកភ្លាមៗ។"""
    items = job.items
    total = len(items)
    done = sum(1 for it in items if it["state"] == "done")
    failed = sum(1 for it in items if it["state"] == "error")
    working = total - done - failed

    st.markdown(
        '<div class="chips">'
        f'<span class="chip">⏳ កំពុងធ្វើ <b>{working}</b></span>'
        f'<span class="chip ok">✅ រួចរាល់ <b>{done}</b></span>'
        f'<span class="chip bad">❌ បរាជ័យ <b>{failed}</b></span>'
        "</div>",
        unsafe_allow_html=True,
    )

    st.progress(
        (done + failed) / total,
        text=f"សរុប {done + failed} / {total}",
    )

    if job.zip:
        dl_button(
            "📦 ទាញយកទាំងអស់ (ZIP)",
            job.zip,
            "khmer_videos.zip",
            "application/zip",
            key=f"wzip_{job.id}",
            use_container_width=True,
        )

    for i, it in enumerate(items, start=1):
        with st.container(border=True):
            tail = ""
            if it["t0"]:
                if it["elapsed"] is not None:
                    secs = it["elapsed"]
                else:
                    secs = time.time() - it["t0"]
                tail = f" · ⏱ {int(secs)} វិនាទី"
            st.markdown(f"**{i}. {short_name(it['name'])}**{tail}")

            if it["state"] == "done":
                # មើលវីដេអូជាមុន មុនទាញយក
                st.caption("▶️ មើលវីដេអូជាមុន មុនទាញយក")
                st.video(it["video"])
                dl_button(
                    "⬇️ ទាញយកវីដេអូនេះ",
                    it["video"],
                    f"{safe_filename(it['name'])}_khmer.mp4",
                    "video/mp4",
                    key=f"wdl_{job.id}_{i}",
                    type="primary",
                    use_container_width=True,
                )
            elif it["state"] == "error":
                st.error(it["error"] or "មិនបានសម្រេច។")
                if DEBUG and it["raw_error"]:
                    st.text(it["raw_error"])
            else:
                st.progress(
                    max(0.0, min(1.0, it["pct"])),
                    text=it["stage"],
                )

            if DEBUG:
                for w in it["warn"]:
                    st.warning(w)

    # ធ្វើការរួចទាំងអស់ → ផ្ទុកទំព័រឡើងវិញម្តង ដើម្បីបញ្ឈប់ការធ្វើបច្ចុប្បន្នភាព
    if was_running and not job.running():
        st.rerun()


def queue_area(job):
    """ផ្ទាំងច្រើនវីដេអូ៖ ជួររង់ចាំ និងស្ថានភាពវីដេអូនីមួយៗ។"""
    icons = {"done": "✅", "error": "❌", "running": "⏳", "queued": "🕒"}
    for i, it in enumerate(job.items, start=1):
        if it["state"] == "done":
            pct, text = 1.0, "រួចរាល់"
        elif it["state"] == "error":
            pct, text = 1.0, "បរាជ័យ"
        else:
            pct, text = it["pct"], it["stage"]
        st.markdown(f"{icons.get(it['state'], '🕒')} **{i}. {it['name']}**")
        st.progress(max(0.0, min(1.0, pct)), text=text)


def download_area(job):
    """ផ្នែកទាញយក៖ វីដេអូណារួច ទាញយកបានភ្លាម។"""
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

            if it.get("voice_lines"):
                with st.expander("👫 សំឡេងអានដែលបានជ្រើស (ប្រុស/ស្រី)"):
                    for line in it["voice_lines"]:
                        st.write(line)

            if DEBUG:
                with st.expander("🛠 DEBUG"):
                    for key, value in it["debug"].items():
                        st.text(f"{key}: {value}")
                    st.text("\n".join(it["log"][-30:]))


def fullscreen_button():
    """
    ដាក់ប៊ូតុងពេញអេក្រង់ ក្នុងប្រអប់ណែនាំខាងលើ (#kac-fs-slot)។
    មាន timer ពិនិត្យរាល់ ០.៨ វិនាទី ដើម្បីដាក់ឡើងវិញ បើអេក្រង់ត្រូវបានគូរឡើងវិញ។
    """
    components.html(
        """
        <script>
        (function () {
          try {
            var win = window.parent;
            var doc = win.document;

            function make() {
              try {
                var slot = doc.getElementById('kac-fs-slot');
                if (!slot || doc.getElementById('kac-fs')) return;
                var b = doc.createElement('button');
                b.id = 'kac-fs';
                b.textContent = '⛶ ពេញអេក្រង់';
                b.style.cssText =
                  'padding:8px 16px;border-radius:12px;' +
                  'border:1px solid #5b92ff;' +
                  'background:linear-gradient(180deg,#3b78ff,#2457e6);' +
                  'color:#ffffff;font-size:14px;font-weight:700;' +
                  'cursor:pointer;font-family:inherit;';
                b.setAttribute(
                  'onclick',
                  "var d=document;" +
                  "if(d.fullscreenElement){d.exitFullscreen();}" +
                  "else{d.documentElement.requestFullscreen();}"
                );
                slot.appendChild(b);
              } catch (e) {}
            }

            make();
            if (win.__kacFsTimer) win.clearInterval(win.__kacFsTimer);
            win.__kacFsTimer = win.setInterval(make, 800);
          } catch (e) {}
        })();
        </script>
        """,
        height=0,
    )


def set_font(name):
    st.session_state["font"] = name


# ---------- ចំណុចប្រទាក់៖ ទំព័រមេ ----------

inject_css()

GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")
GROQ_KEY = st.secrets.get("GROQ_API_KEY", "")

if not GEMINI_KEY and not GROQ_KEY:
    st.error("កម្មវិធីមិនទាន់រួចរាល់ទេ។ សូមទាក់ទងម្ចាស់កម្មវិធី។")
    st.stop()

# ---------- របៀបជួសជុល៖ មានតែម្ចាស់ដែលចូលប្រើបាន ----------
if st.secrets.get("MAINTENANCE", False):
    owner_pw = str(st.secrets.get("OWNER_PASSWORD", ""))
    if not st.session_state.get("owner_ok"):
        st.markdown(
            '<div class="hero"><div class="hero-t">🛠 កំពុងជួសជុល</div>'
            '<div class="hero-s">កម្មវិធីបិទជាបណ្តោះអាសន្ន។ '
            "សូមត្រឡប់មកវិញពេលក្រោយ។</div></div>",
            unsafe_allow_html=True,
        )
        with st.expander("🔑 សម្រាប់ម្ចាស់កម្មវិធី"):
            pw = st.text_input("ពាក្យសម្ងាត់", type="password", key="owner_pw")
            if pw and owner_pw and pw == owner_pw:
                st.session_state["owner_ok"] = True
                st.rerun()
        st.stop()

st.markdown(
    '<div class="hero">'
    '<div class="hero-t">បកប្រែរឿងមកនិយាយភាសាខ្មែរ</div>'
    '<div class="hero-s">បង្កើតវីដេអូមានអក្សរខ្មែរ និងសំឡេងអាន AI · '
    f"ធ្វើបានរហូតដល់ {MAX_VIDEOS} វីដេអូស្មើគ្នា</div>"
    "</div>",
    unsafe_allow_html=True,
)

# ប្រអប់ណែនាំ + ប៊ូតុងពេញអេក្រង់ (នៅខាងលើ)
st.markdown(
    '<div class="tip">'
    '<div class="tip-t">💡 <b>ណែនាំ៖</b> ចុចប៊ូតុង <b>«ពេញអេក្រង់»</b> '
    "ដើម្បីបើកកម្មវិធីឱ្យធំពេញអេក្រង់ ស្រួលមើល និងស្រួលប្រើ។ "
    "ចុចម្តងទៀត ឬចុច <b>Esc</b> ដើម្បីចេញ។ "
    "ពេលវីដេអូរួចរាល់ អ្នកអាច <b>មើលវីដេអូជាមុន</b> "
    "មុនចុចទាញយក។</div>"
    '<div id="kac-fs-slot"></div>'
    "</div>",
    unsafe_allow_html=True,
)
fullscreen_button()

# បង្កើត ZIP តែម្តង ពេលរួចទាំងអស់
job = st.session_state.get("job")
if job and not job.running() and not job.zip_done:
    job.zip = build_zip(job.items)
    job.zip_done = True

running = bool(job and job.running())
busy = running
refresh = REFRESH_SECONDS if running else None

(
    tab_home,
    tab_font,
    tab_voice,
    tab_batch,
    tab_my,
    tab_help,
) = st.tabs(
    [
        "🏠 ទំព័រដើម",
        "💬 អក្សរខ្មែរ",
        "🎙️ សំឡេង AI",
        "📚 ច្រើនវីដេអូ",
        "🎞️ វីដេអូខ្ញុំ",
        "❓ ជំនួយ",
    ]
)

run = False
items = []

# =====================================================================
# ទំព័រដើម
# =====================================================================
with tab_home:
    left, right = st.columns([1.55, 1], gap="large")

    # ---------------- ជួរឈរខាងឆ្វេង ----------------
    with left:
        section("ផ្ទុកវីដេអូ", "Upload")

        uploaded_files = []
        link_text = ""

        with card("upload"):
            mode = st.radio(
                "វិធីបញ្ចូលវីដេអូ",
                [MODE_UP, MODE_LINK, MODE_BATCH],
                horizontal=True,
                label_visibility="collapsed",
                key="src_mode",
            )

            if mode == MODE_UP:
                one = st.file_uploader(
                    "ទាញវីដេអូមកទីនេះ ឬចុចជ្រើសរើស",
                    type=["mp4", "mov", "mkv", "avi", "webm"],
                    accept_multiple_files=False,
                    key="up_one",
                    help="បើអ៊ីនធឺណិតយឺត សូមប្រើវីដេអូតូច ឬជម្រើស Link",
                )
                uploaded_files = [one] if one else []
            elif mode == MODE_LINK:
                link_text = st.text_input(
                    "តំណវីដេអូ (.mp4 ផ្ទាល់ ឬ Google Drive សាធារណៈ)",
                    placeholder="https://...",
                    key="link_one",
                )
            else:
                uploaded_files = st.file_uploader(
                    "ជ្រើសរើសវីដេអូ (ជ្រើសបានច្រើន)",
                    type=["mp4", "mov", "mkv", "avi", "webm"],
                    accept_multiple_files=True,
                    key="up_many",
                ) or []
                link_text = st.text_area(
                    "ឬតំណវីដេអូ — មួយបន្ទាត់ ១ តំណ",
                    placeholder="https://...\nhttps://...",
                    height=100,
                    key="links_many",
                )

            st.caption(
                "MP4, MOV, MKV, AVI, WEBM · "
                f"វែងបំផុត {MAX_DURATION_MIN} នាទី"
            )

        with card("output"):
            card_title("⚙", "លទ្ធផល", "Output")

            engine_options = []
            if GROQ_KEY:
                engine_options.append(ENGINE_FREE)
            if GEMINI_KEY:
                engine_options.append(ENGINE_GEMINI)

            quality_label = st.selectbox(
                "គុណភាពវីដេអូ",
                list(QUALITY.keys()),
                index=1,
                key="quality",
            )
            language_label = st.selectbox(
                "ភាសាក្នុងវីដេអូ",
                list(LANGUAGES.keys()),
                index=0,
                key="lang",
                help=(
                    "ស្វ័យប្រវត្តិ៖ AI ស្គាល់ភាសាដោយខ្លួនឯង។ "
                    "បើលទ្ធផលមិនត្រឹមត្រូវ សូមជ្រើសភាសាជាក់លាក់ "
                    "(ឧ. ចិន បើវីដេអូនិយាយចិន)។"
                ),
            )
            engine_label = st.selectbox(
                "ម៉ាស៊ីនបកប្រែ",
                engine_options,
                index=0,
                key="engine",
                help=(
                    "បើមាន Key ទាំងពីរ ហើយម៉ាស៊ីនមួយមានបញ្ហា ឬអស់កូតា "
                    "កម្មវិធីនឹងប្តូរទៅម៉ាស៊ីនមួយទៀតដោយស្វ័យប្រវត្តិ។"
                ),
            )
            if engine_label == ENGINE_FREE:
                st.caption(
                    "ឥតគិតថ្លៃ និងលឿន។ ការបកប្រែតាម Google Translate "
                    "នឹងត្រូវ AI កែឱ្យជាភាសានិយាយធម្មជាតិ និងខ្លីល្មមនិយាយទាន់ម៉ោង។"
                )

        # ---------- រៀបចំបញ្ជីវីដេអូ ----------
        for f in uploaded_files:
            items.append({"name": f.name, "file": f, "url": None})

        link_lines = [
            ln.strip()
            for ln in (link_text or "").splitlines()
            if ln.strip().lower().startswith(("http://", "https://"))
        ]
        for i, url in enumerate(link_lines, start=1):
            tail = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
            items.append({
                "name": tail or f"តំណទី {i}",
                "file": None,
                "url": url,
            })

        too_many = len(items) > MAX_VIDEOS
        items = items[:MAX_VIDEOS]

        if too_many:
            st.warning(
                f"អាចធ្វើបានត្រឹម {MAX_VIDEOS} វីដេអូម្តង។ "
                f"កម្មវិធីនឹងធ្វើតែ {MAX_VIDEOS} ដំបូង។"
            )

        # ---------- ប៊ូតុងចាប់ផ្តើម ----------
        if busy:
            st.button(
                "⏳ កំពុងធ្វើការ... សូមរង់ចាំ",
                disabled=True,
                use_container_width=True,
            )
        elif not items:
            st.button(
                "✨ ចាប់ផ្តើមដំណើរការ",
                disabled=True,
                use_container_width=True,
            )
            st.caption("សូមជ្រើសរើសវីដេអូ ឬបិទភ្ជាប់តំណជាមុនសិន។")
        else:
            label = "✨ ចាប់ផ្តើមដំណើរការ"
            if len(items) > 1:
                label += f" ({len(items)} វីដេអូ ស្មើគ្នា)"
            run = st.button(label, type="primary", use_container_width=True)

        # ---------- កំពុងដំណើរការ ----------
        section("កំពុងដំណើរការ", "Processing")
        if job:
            st.fragment(run_every=refresh)(work_area)(job, running)
        else:
            st.caption(
                "នៅទីនេះ ជ្រើសវីដេអូ រួចចុច «ចាប់ផ្តើមដំណើរការ»។"
            )

    # ---------------- ជួរឈរខាងស្តាំ ----------------
    with right:
        s_fs = st.session_state.get("fs", 22)
        s_ol = st.session_state.get("ol", 2)
        s_font = st.session_state.get("font", DEFAULT_FONT)
        if s_font not in FONT_MAP:
            s_font = DEFAULT_FONT
        s_col = st.session_state.get("col", "⚪ ស")
        if s_col not in COLOR_OPTIONS:
            s_col = "⚪ ស"
        s_pos = st.session_state.get("pos", "↓ ក្រោម")
        if s_pos not in POSITIONS:
            s_pos = "↓ ក្រោម"
        s_text = (st.session_state.get("sample_text") or "").strip()

        with card("preview"):
            card_title("🎬", "មើលជាមុន", "Preview")
            st.markdown(
                preview_html(
                    s_text or SAMPLE_TEXT,
                    FONT_MAP[s_font]["family"],
                    s_fs,
                    s_ol,
                    COLOR_OPTIONS[s_col][1],
                    POSITIONS[s_pos][2],
                ),
                unsafe_allow_html=True,
            )

        with card("subtitle"):
            card_title("🅰", "កំណត់អក្សរ", "Subtitle")
            font_size = st.slider("ទំហំអក្សរ", 16, 36, 22, key="fs")
            outline_size = st.slider("កម្រាស់គែមអក្សរ", 1, 5, 2, key="ol")
            font_name = st.selectbox(
                "ពុម្ពអក្សរខ្មែរ (Font)",
                FONT_NAMES,
                index=0,
                key="font",
                format_func=lambda n: f"{n} — {FONT_MAP[n]['desc']}",
            )
            font_color = st.radio(
                "ពណ៌អក្សរ",
                list(COLOR_OPTIONS.keys()),
                horizontal=True,
                key="col",
            )
            position_label = st.radio(
                "ទីតាំងអក្សរ",
                list(POSITIONS.keys()),
                horizontal=True,
                key="pos",
            )

        with card("dubbing"):
            card_title("🎙️", "សំឡេង AI", "Dubbing")
            dub_on = st.checkbox(
                "បន្ថែមសំឡេងអានជាភាសាខ្មែរ (Dubbing)",
                key="dub_on",
            )
            voice_label = list(TTS_VOICES.keys())[0]
            keep_bg = False
            auto_gender = False
            if dub_on:
                voice_label = st.selectbox(
                    "សំឡេង",
                    list(TTS_VOICES.keys()),
                    key="voice",
                )
                auto_gender = st.checkbox(
                    "👫 ជ្រើសសំឡេងប្រុស/ស្រី តាមអ្នកនិយាយដោយស្វ័យប្រវត្តិ",
                    key="auto_gender",
                    help=(
                        "វិភាគកម្រិតសំឡេងដើមទាំងមូល ដើម្បីដឹងថាអ្នកណានិយាយពេលណា។ "
                        "ប្រុសនិយាយ → AI ប្រុស, ស្រីនិយាយ → AI ស្រី "
                        "ហើយបំបែកឃ្លាត្រង់កន្លែងដែលអ្នកនិយាយប្តូរ។ "
                        "បើមានអ្នកនិយាយម្នាក់ វាប្រើសំឡេងតែមួយពេញវីដេអូ។"
                    ),
                )
                keep_bg = st.checkbox(
                    "រក្សាសំឡេងដើមតិចៗ",
                    key="keep_bg",
                )

# ---------- ចាប់ផ្តើមការងារ ----------

if run:
    try:
        fonts_data, font_warn = load_fonts_for(font_name)
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
        "auto_gender": auto_gender,
        "font_size": font_size,
        "outline_size": outline_size,
        "color": COLOR_OPTIONS[font_color][0],
        "alignment": POSITIONS[position_label][:2],
        "font_name": font_name,
        "font_warn": font_warn,
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

    new_job = Job(job_items, job_folder)
    st.session_state["job"] = new_job

    # ចាប់ផ្តើមវីដេអូទាំងអស់ស្មើគ្នា
    for item in new_job.items:
        threading.Thread(
            target=run_worker,
            args=(new_job, item, settings, fonts_data),
            daemon=True,
        ).start()

    st.rerun()

# =====================================================================
# ផ្ទាំងអក្សរខ្មែរ (ជម្រើស Font)
# =====================================================================
with tab_font:
    section("ពុម្ពអក្សរខ្មែរ", "Fonts")
    st.caption(
        "ជ្រើសពុម្ពអក្សរសម្រាប់អក្សររត់ក្នុងវីដេអូ។ "
        "ពុម្ពអក្សរបែបសិល្បៈ អាចអានពិបាកក្នុងវីដេអូ "
        "— ណែនាំ Battambang ឬ Noto Sans Khmer។"
    )
    st.text_input(
        "សាកសរសេរអក្សរមើល",
        value=SAMPLE_TEXT,
        key="sample_text",
    )

    sample = html_escape(
        (st.session_state.get("sample_text") or "").strip() or SAMPLE_TEXT
    )
    current_font = st.session_state.get("font", DEFAULT_FONT)

    cols = st.columns(2, gap="medium")
    for i, name in enumerate(FONT_NAMES):
        with cols[i % 2]:
            with card(f"font_{i}"):
                selected = name == current_font
                st.markdown(
                    f'<div class="fn">{name}</div>'
                    f'<div class="fd">{FONT_MAP[name]["desc"]}</div>'
                    f'<div class="fp" style="font-family:\'{name}\','
                    f'sans-serif">{sample}</div>',
                    unsafe_allow_html=True,
                )
                st.button(
                    "✅ កំពុងប្រើ" if selected else "ប្រើពុម្ពអក្សរនេះ",
                    key=f"usefont_{i}",
                    on_click=set_font,
                    args=(name,),
                    type="primary" if selected else "secondary",
                    disabled=selected,
                    use_container_width=True,
                )

# =====================================================================
# ផ្ទាំងសំឡេង AI (សាកស្តាប់)
# =====================================================================
with tab_voice:
    section("សំឡេង AI", "Voice")
    st.caption(
        "សាកស្តាប់សំឡេងអានខ្មែរ មុនបើក Dubbing។ "
        "ជ្រើសសំឡេងពិតប្រាកដនៅក្នុងផ្នែក «សំឡេង AI · Dubbing» ក្នុងទំព័រដើម។"
    )
    voice_text = st.text_input(
        "អត្ថបទសាកស្តាប់",
        value=SAMPLE_VOICE_TEXT,
        key="tts_text",
    )

    vcols = st.columns(2, gap="medium")
    for i, (vname, vid) in enumerate(TTS_VOICES.items()):
        with vcols[i]:
            with card(f"voice_{i}"):
                st.markdown(
                    f'<div class="fn">{"👩" if "ស្រី" in vname else "👨"} '
                    f"{vname}</div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "▶️ សាកស្តាប់",
                    key=f"play_{i}",
                    use_container_width=True,
                ):
                    text_to_say = (voice_text or "").strip()
                    if not text_to_say:
                        st.warning("សូមសរសេរអត្ថបទជាមុនសិន។")
                    else:
                        try:
                            with st.spinner("កំពុងបង្កើតសំឡេង..."):
                                audio = voice_sample(text_to_say, vid)
                            st.audio(audio, format="audio/mp3")
                        except Exception:
                            st.error(
                                "បង្កើតសំឡេងមិនបានទេ។ សូមសាកម្តងទៀត។"
                            )

# =====================================================================
# ផ្ទាំងច្រើនវីដេអូ (ជួររង់ចាំ)
# =====================================================================
with tab_batch:
    section("ច្រើនវីដេអូ", "Batch")
    st.caption(
        f"ធ្វើបានរហូតដល់ {MAX_VIDEOS} វីដេអូស្មើគ្នា។ "
        "នៅទំព័រដើម ជ្រើស «Batch · ច្រើនវីដេអូ» "
        "ដើម្បីដាក់ឯកសារច្រើន ឬតំណច្រើន (មួយបន្ទាត់ ១ តំណ)។"
    )
    if job:
        st.fragment(run_every=refresh)(queue_area)(job)
    else:
        st.info("មិនទាន់មានវីដេអូក្នុងជួររង់ចាំទេ។")

# =====================================================================
# ផ្ទាំងវីដេអូខ្ញុំ (ទាញយក)
# =====================================================================
with tab_my:
    section("វីដេអូខ្ញុំ", "My videos")
    if job:
        st.fragment(run_every=refresh)(download_area)(job)
        if not running:
            if st.button("🗑 លុបលទ្ធផលទាំងអស់", key="clear_job"):
                shutil.rmtree(job.folder, ignore_errors=True)
                st.session_state.pop("job", None)
                st.rerun()
    else:
        st.info("មិនទាន់មានវីដេអូទេ។ សូមបង្កើតវីដេអូនៅទំព័រដើមជាមុនសិន។")

# =====================================================================
# ផ្ទាំងជំនួយ
# =====================================================================
with tab_help:
    section("ជំនួយ", "Help")
    st.markdown(
        f"""
**របៀបប្រើ**

1. ចុចប៊ូតុង **ពេញអេក្រង់** នៅខាងលើ ដើម្បីមើលកម្មវិធីឱ្យធំ (ចុច Esc ដើម្បីចេញ)
2. នៅទំព័រដើម ជ្រើស **Upload** (ឯកសារ) **Link** (តំណ) ឬ **Batch** (ច្រើនវីដេអូ)
3. ជ្រើសគុណភាព ភាសាក្នុងវីដេអូ និងម៉ាស៊ីនបកប្រែ
4. កំណត់អក្សរ៖ ទំហំ គែម ពុម្ពអក្សរ ពណ៌ និងទីតាំង (មើលជាមុនបានភ្លាមៗ)
5. ចង់បានសំឡេងអានខ្មែរ ដាក់ ✔ ត្រង់ **Dubbing**
6. ចុច **ចាប់ផ្តើមដំណើរការ** ហើយរង់ចាំ
7. ពេលរួច **មើលវីដេអូជាមុន** នៅក្រោម «កំពុងដំណើរការ» ភ្លាម
   រួចចុចប៊ូតុង **ទាញយកវីដេអូ** (ឬនៅផ្ទាំង **វីដេអូខ្ញុំ** ក៏បាន)

**ដែនកំណត់**

- វីដេអូម្តងបានអតិបរមា {MAX_VIDEOS}
- វីដេអូនីមួយៗវែងបំផុត {MAX_DURATION_MIN} នាទី
- វីដេអូពីតំណធំបំផុត {MAX_DOWNLOAD_MB}MB

**គន្លឹះ**

- បើអ៊ីនធឺណិតយឺត សូមប្រើវីដេអូតូច ឬជម្រើស Link
- បើលទ្ធផលបកប្រែមិនត្រឹមត្រូវ សូមជ្រើសភាសាក្នុងវីដេអូឱ្យជាក់លាក់
- ការបកប្រែត្រូវបានកែឱ្យជាភាសានិយាយធម្មជាតិ ដូចមនុស្សខ្មែរនិយាយពិត
  ហើយខ្លីល្មមនិយាយទាន់ម៉ោងវីដេអូដើម
- ពុម្ពអក្សរបែបសិល្បៈ (Moul, Bayon, Fasthand...) សមសម្រាប់ចំណងជើង
  តែអាចអានពិបាកជាអក្សររត់
"""
    )
