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
from concurrent.futures import ThreadPoolExecutor
from html import escape as html_escape

import streamlit as st
import imageio_ffmpeg
import edge_tts
from google import genai
from google.genai import types

st.set_page_config(page_title="Khmer Auto Caption", page_icon="🎬", layout="wide")

# ---------------------------------------------------------------------
# ការកំណត់
# ---------------------------------------------------------------------
MAX_CAPTION_CHARS = 26
MAX_DOWNLOAD_MB = 300
MAX_VIDEOS = 5
MAX_ZIP_MB = 250
REFRESH_SECONDS = 2
MAX_RENDER_AT_ONCE = 3
MAX_DURATION_MIN = 15
CHARS_PER_SEC = 11      # Dubbing
CAPTION_CPS = 16        # អក្សរធម្មតា
MAX_DUB_SPEED = 1.4
MERGE_GAP = 0.7
MERGE_MAX_SEC = 9.0
MERGE_MAX_CHARS = 140
END_PUNCT = tuple("。！？.!?…")
TTS_WORKERS = 6
LLM_WORKERS = 3
TRANSLATE_WORKERS = 2
REQUEST_TIMEOUT_MS = 120000

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODELS = ["whisper-large-v3", "whisper-large-v3-turbo"]
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_CHAT_MODELS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"]

WHISPER_LANG = {
    "Khmer": "km", "English": "en", "Thai": "th", "Vietnamese": "vi",
    "Chinese": "zh", "Japanese": "ja", "Korean": "ko", "French": "fr",
}
LANGUAGES = {
    "🌐 ស្វ័យប្រវត្តិ": None,
    "ខ្មែរ": "Khmer",
    "អង់គ្លេស": "English",
    "ថៃ": "Thai",
    "វៀតណាម": "Vietnamese",
    "ចិន": "Chinese",
    "ជប៉ុន": "Japanese",
    "កូរ៉េ": "Korean",
    "បារាំង": "French",
}

CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
THAI_LAO_RE = re.compile(r"[\u0E00-\u0EFF]")
LATIN_RE = re.compile(r"[A-Za-z]")
KH_DIGITS = str.maketrans("0123456789", "០១២៣៤៥៦៧៨៩")

GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONTS = {
    "Battambang": ["battambang/Battambang-Regular.ttf"],
    "Noto Sans Khmer": ["notosanskhmer/NotoSansKhmer%5Bwdth%2Cwght%5D.ttf"],
    "Kantumruy Pro": ["kantumruypro/KantumruyPro%5Bwght%5D.ttf"],
    "Hanuman": ["hanuman/Hanuman-Regular.ttf", "hanuman/Hanuman%5Bwght%5D.ttf"],
}
FONT_NAMES = list(FONTS.keys())
DEFAULT_FONT = "Battambang"

QUALITY = {
    "⚡ លឿន": (480, 28, "ultrafast"),
    "✨ ល្អ (ណែនាំ)": (720, 24, "veryfast"),
    "💎 គុណភាពខ្ពស់": (0, 20, "veryfast"),
}
TTS_VOICES = {
    "ស្រី (Sreymom)": "km-KH-SreymomNeural",
    "ប្រុស (Piseth)": "km-KH-PisethNeural",
}
COLOR_OPTIONS = {
    "⚪ ស": ("&H00FFFFFF", "#FFFFFF"),
    "🟡 លឿង": ("&H0000FFFF", "#FFE600"),
    "🟢 បៃតង": ("&H0000FF00", "#22E55A"),
    "🔵 ខៀវ": ("&H00FF0000", "#3B82F6"),
    "🔴 ក្រហម": ("&H000000FF", "#FF3B3B"),
}
POSITIONS = {
    "↓ ក្រោម": (2, 35, "bottom"),
    "⏺️ កណ្តាល": (5, 0, "middle"),
    "↑ លើ": (8, 30, "top"),
}
SAMPLE_TEXT = "សួស្តី! នេះជាអក្សរគំរូ"

MODE_UP = "📁 Upload"
MODE_LINK = "🔗 Link"
MODE_BATCH = "📚 Batch"


class UserError(RuntimeError):
    """សារកំហុសដែលបង្ហាញដល់អ្នកប្រើផ្ទាល់។"""


def friendly_message(error):
    if isinstance(error, UserError):
        return str(error)
    low = str(error).lower()
    if "429" in low or "quota" in low or "resource_exhausted" in low:
        return "មានអ្នកប្រើច្រើនពេក។ សូមរង់ចាំមួយភ្លែត រួចសាកម្តងទៀត។"
    if "503" in low or "unavailable" in low or "timeout" in low or "timed out" in low:
        return "ប្រព័ន្ធ AI កំពុងរវល់។ សូមសាកម្តងទៀតក្នុងមួយភ្លែត។"
    if "api key" in low or "api_key" in low or "permission" in low:
        return "សេវា AI មានបញ្ហា។ សូមទាក់ទងម្ចាស់កម្មវិធី។"
    return "ការបង្កើតវីដេអូមិនបានសម្រេច។ សូមសាកម្តងទៀត។"


# ---------------------------------------------------------------------
# ឧបករណ៍ទូទៅ
# ---------------------------------------------------------------------
def fix_khmer(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    text = re.sub(r"(\u17D2)\s+", r"\1", text)
    text = re.sub(r"\s+([\u17B6-\u17D3])", r"\1", text)
    text = re.sub(r"([\u17B6-\u17D3])\s+([\u17B6-\u17D3])", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def has_khmer(text):
    return bool(re.search(r"[\u1780-\u17FF]", text or ""))


def safe_filename(name):
    base = os.path.splitext(str(name))[0]
    base = re.sub(r"[^\w\-]+", "_", base).strip("_")[:40]
    return base or "video"


def short_name(name, limit=34):
    name = str(name)
    return name if len(name) <= limit else name[: limit - 1] + "…"


def run_ffmpeg(args, cwd=None, env=None):
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y"] + args
    full_env = None
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=True, cwd=cwd, env=full_env,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", "ignore")[-1500:]
        raise RuntimeError("FFmpeg បរាជ័យ:\n" + err)
    return (result.stderr or b"").decode("utf-8", "ignore")


def probe_video(path):
    """អានរយៈពេល និងទំហំវីដេអូ។"""
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-i", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    err = result.stderr
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not match:
        raise UserError("មិនអាចអានវីដេអូនេះបានទេ។ សូមសាកវីដេអូ MP4 ផ្សេង។")
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


# ---------------------------------------------------------------------
# Font
# ---------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def fetch_font(name):
    """ទាញយក Font ខ្មែរ (cache)។ ត្រឡប់ (ឈ្មោះឯកសារ, ទិន្នន័យ)។"""
    last = None
    for path in FONTS[name]:
        try:
            req = urllib.request.Request(GF + path, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            if len(data) < 1000:
                raise RuntimeError("ឯកសារ Font តូចពេក។")
            return re.sub(r"\W+", "_", name).strip("_") + ".ttf", data
        except Exception as e:
            last = e
    raise RuntimeError(f"ទាញយក Font {name} មិនបាន: {last}")


def load_font(selected):
    """ត្រឡប់ (ឈ្មោះឯកសារ, ទិន្នន័យ, ឈ្មោះ Font, សារព្រមាន)។"""
    if selected not in FONTS:
        selected = DEFAULT_FONT
    for name in [selected] + [n for n in FONT_NAMES if n != selected]:
        try:
            fname, data = fetch_font(name)
            warn = "" if name == selected else (
                f"ពុម្ពអក្សរ {selected} ទាញយកមិនបាន ប្រើ {name} ជំនួស។"
            )
            return fname, data, name, warn
        except Exception:
            continue
    raise RuntimeError("ទាញយក Font ខ្មែរមិនបាន។")


def get_font_family(path, default):
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
    """fontconfig ផ្ទាល់ខ្លួន ដើម្បីឱ្យ FFmpeg រក Font ក្នុងថតនេះឃើញ។"""
    cache_dir = os.path.join(folder, "fc-cache")
    os.makedirs(cache_dir, exist_ok=True)
    conf_path = os.path.join(folder, "fonts.conf")
    conf = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        "<fontconfig>\n"
        '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
        f"  <dir>{folder}</dir>\n"
        f"  <cachedir>{cache_dir}</cachedir>\n"
        "</fontconfig>\n"
    )
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(conf)
    return {"FONTCONFIG_FILE": conf_path, "FONTCONFIG_PATH": folder}


# ---------------------------------------------------------------------
# ទាញយកវីដេអូ និងដកសំឡេង
# ---------------------------------------------------------------------
def normalize_link(url):
    url = url.strip()
    m = re.search(r"drive\.google\.com/file/d/([\w-]+)", url) or re.search(
        r"drive\.google\.com/open\?id=([\w-]+)", url
    )
    if m:
        return "https://drive.google.com/uc?export=download&id=" + m.group(1)
    return url


def download_video(url, path, rep):
    url = normalize_link(url)
    limit = MAX_DOWNLOAD_MB * 1024 * 1024
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype:
                raise UserError(
                    "តំណនេះមិនមែនជាវីដេអូផ្ទាល់ទេ។ សូមប្រើតំណ .mp4 ផ្ទាល់ "
                    "ឬ Google Drive ដែលចែករំលែកជាសាធារណៈ។"
                )
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            with open(path, "wb") as f:
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if done > limit:
                        raise UserError(f"វីដេអូធំជាង {MAX_DOWNLOAD_MB}MB។")
                    if total:
                        rep.progress(min(1.0, done / total))
    except UserError:
        raise
    except Exception:
        raise UserError("ទាញយកវីដេអូពីតំណមិនបានទេ។ សូមពិនិត្យតំណ ឬសាកម្តងទៀត។")
    if os.path.getsize(path) < 1000:
        raise UserError("ទាញយកវីដេអូមិនបាន។ សូមពិនិត្យតំណ។")


def extract_audio(video_path, audio_path):
    try:
        run_ffmpeg([
            "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
            "-b:a", "64k", audio_path,
        ])
    except RuntimeError:
        raise UserError("មិនអាចដកសំឡេងពីវីដេអូនេះបានទេ។ វីដេអូអាចគ្មានសំឡេង។")


# ---------------------------------------------------------------------
# Groq Whisper (ស្តាប់)
# ---------------------------------------------------------------------
def groq_request(api_key, audio_path, model, language):
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
            (f"--{boundary}\r\nContent-Disposition: form-data; "
             f'name="{name}"\r\n\r\n{value}\r\n').encode("utf-8")
        )
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    parts.append(
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
         'filename="audio.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n').encode("utf-8")
    )
    parts.append(audio_data)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        GROQ_URL, data=b"".join(parts), method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:500]
        raise RuntimeError(f"Groq HTTP {e.code}: {detail}")


def groq_transcribe(api_key, audio_path, language, rep):
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
                        break
                    rep.write("ប្រព័ន្ធរវល់បន្តិច កំពុងសាកម្តងទៀត...")
                    time.sleep(8)
                    continue
                break
            except Exception as e:
                last = e
                break
    raise last or RuntimeError("Groq បរាជ័យ")


# ---------------------------------------------------------------------
# បកប្រែ៖ Google Translate + AI (Gemini / Groq)
# ---------------------------------------------------------------------
GT_HOSTS = ["translate.googleapis.com", "translate.google.com"]


def _google_once(text, host):
    query = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "km", "dt": "t"})
    req = urllib.request.Request(
        f"https://{host}/translate_a/single?" + query,
        data=urllib.parse.urlencode({"q": text}).encode("utf-8"),
        method="POST",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.loads(r.read().decode("utf-8"))
    return "".join(p[0] for p in (data[0] or []) if p and p[0])


def google_translate_request(text, retries=3):
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
    out = str(out or "")
    out = CJK_RE.sub("", out)
    out = THAI_LAO_RE.sub("", out)
    out = re.sub(r"[\"“”«»()\[\]{}*_#]", "", out)
    return fix_khmer(out) or None


def accept_khmer(text):
    """ទទួលតែឃ្លាខ្មែរល្អ ហើយបំលែងលេខជាលេខខ្មែរ។"""
    t = clean_translation(text)
    if not t or not has_khmer(t):
        return None
    k = len(re.findall(r"[\u1780-\u17FF]", t))
    if len(LATIN_RE.findall(t)) > k * 0.3:
        return None
    return t.translate(KH_DIGITS)


def translate_texts(texts):
    """Google Translate ជាក្រុមៗ (បម្រុង)។ ត្រឡប់ (លទ្ធផល, កំហុស)។"""
    errors = []
    outs = [None] * len(texts)
    blocked = {"v": False}

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


KHMER_STYLE = (
    "Write casual spoken Khmer (Khmer script only) that sounds good when "
    "read aloud by a text-to-speech voice. Start from the meaning, then say "
    "it the way a native speaker naturally would; reorder, merge, split, add "
    "or drop words freely. Khmer drops subjects and pronouns when obvious. "
    "Prefer short sentences joined by natural connectors. Avoid "
    "translationese and stiff bookish words. Turn idioms, slang and jokes "
    "into the Khmer way of reacting. Keep the same emotion and energy. Stay "
    "within max_chars by choosing the gist, never by cutting a sentence in "
    "the middle. Put a space between phrases. No digits, symbols, emojis, "
    "parentheses or quotes: write numbers as Khmer words. Names may be "
    "transliterated into Khmer."
)
NATURAL_SYSTEM = (
    "You are a native Khmer dubbing scriptwriter. You do NOT translate "
    "word by word; you re-say what the speaker means, the way a real "
    "Cambodian would say it. Each input line has: original (source "
    "language, may contain recognition errors), seconds and max_chars "
    "(Khmer characters). Use whole_script to understand the situation and "
    "keep names and pronouns consistent. " + KHMER_STYLE +
    ' Return JSON {"lines": [...]} with exactly the same number of items '
    "as the input lines, in the same order."
)
TRANSLATE_SYSTEM = (
    "You translate subtitles into natural, fluent Khmer (Khmer script only). "
    'Return JSON {"lines": [...]} with exactly the same number of items, '
    "in the same order."
)


def gemini_json_list(api_key, system, text, count):
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )
    last = "មិនមានម៉ូដែល"
    for model in GEMINI_MODELS:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=text,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        temperature=0.6,
                        response_mime_type="application/json",
                    ),
                )
                raw = (getattr(resp, "text", None) or "").strip()
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
                data = json.loads(raw)
                if isinstance(data, dict):
                    data = data.get("lines") or data.get("translations") or []
                if isinstance(data, list) and len(data) == count:
                    return [clean_translation(x) if isinstance(x, str) else None for x in data]
                last = f"{model}: ចំនួនបន្ទាត់មិនត្រូវគ្នា"
                break
            except Exception as e:
                last = f"{model}: {e}"
                low = str(e).lower()
                if ("503" in low or "unavailable" in low) and attempt == 0:
                    time.sleep(3)
                    continue
                break
    raise RuntimeError(last[:300])


def groq_json_list(api_key, system, text, count):
    errs = []
    for model in GROQ_CHAT_MODELS:
        body = json.dumps({
            "model": model,
            "temperature": 0.5,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            GROQ_CHAT_URL, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
            obj = json.loads(content)
            items = obj.get("lines") or obj.get("translations") or []
            if len(items) == count:
                return [clean_translation(x) if isinstance(x, str) else None for x in items]
            errs.append(f"{model}: ចំនួនបន្ទាត់មិនត្រូវគ្នា")
        except Exception as e:
            errs.append(f"{model}: {e}"[:90])
    raise RuntimeError(" | ".join(errs)[:400])


def ask_ai_list(system, payload, count, gemini_key, groq_key, errors):
    """សួរ Gemini មុន បើមិនបានសួរ Groq។ ត្រឡប់បញ្ជី ឬ None។"""
    if gemini_key:
        try:
            return gemini_json_list(gemini_key, system, payload, count)
        except Exception as e:
            errors.append(f"gemini: {e}"[:200])
    if groq_key:
        try:
            return groq_json_list(groq_key, system, payload, count)
        except Exception as e:
            errors.append(f"groq: {e}"[:200])
    return None


def char_limit(seconds, cps):
    return max(8, int(round((max(0.0, float(seconds)) + 0.3) * cps)))


def naturalize(originals, durations, dub, gemini_key, groq_key, errors):
    """អត្ថបទដើម → ខ្មែរនិយាយធម្មជាតិ ខ្លីល្មមទាន់ម៉ោង។"""
    n = len(originals)
    cps = CHARS_PER_SEC if dub else CAPTION_CPS
    outs = [None] * n
    overview = " ".join(str(o).strip() for o in originals)[:3000]
    batches = [list(range(k, min(n, k + 20))) for k in range(0, n, 20)]

    def run(idx):
        payload = json.dumps({
            "whole_script": overview,
            "lines": [
                {
                    "original": str(originals[i]).strip(),
                    "seconds": round(float(durations[i]), 1),
                    "max_chars": char_limit(durations[i], cps),
                }
                for i in idx
            ],
        }, ensure_ascii=False)
        return idx, ask_ai_list(
            NATURAL_SYSTEM, payload, len(idx), gemini_key, groq_key, errors
        )

    with ThreadPoolExecutor(max_workers=LLM_WORKERS) as ex:
        for idx, res in ex.map(run, batches):
            if res:
                for i, r in zip(idx, res):
                    outs[i] = accept_khmer(r) if r else None
    return outs


def merge_thoughts(keep):
    """ផ្សំឃ្លាដែលដាច់កណ្តាលប្រយោគ ឱ្យទៅជាប្រយោគពេញ មុនបកប្រែ។"""
    out = []
    for s, e, t in keep:
        t = str(t).strip()
        if out:
            ps, pe, pt = out[-1]
            if (
                s - pe <= MERGE_GAP
                and not pt.rstrip().endswith(END_PUNCT)
                and (e - ps) <= MERGE_MAX_SEC
                and len(pt) + len(t) <= MERGE_MAX_CHARS
            ):
                sep = "" if CJK_RE.search(pt[-1:]) else " "
                out[-1] = (ps, e, pt + sep + t)
                continue
        out.append((s, e, t))
    return out


def transcribe(groq_key, gemini_key, audio_path, duration, language, dub, rep):
    """ស្តាប់ដោយ Groq Whisper រួចបកជាខ្មែរ។ ត្រឡប់ (segments, failed)។"""
    code = WHISPER_LANG.get(language) if language else None
    data, _ = groq_transcribe(groq_key, audio_path, code, rep)
    detected = str(data.get("language", "") or "").lower()

    keep = []
    for sg in data.get("segments") or []:
        text = str(sg.get("text", "")).strip()
        if not text:
            continue
        if (
            float(sg.get("no_speech_prob", 0) or 0) > 0.6
            and float(sg.get("avg_logprob", 0) or 0) < -0.8
        ):
            continue
        try:
            s, e = float(sg.get("start", 0)), float(sg.get("end", 0))
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
    if language == "Khmer" or detected in ("khmer", "km"):
        segs = [(s, e, fix_khmer(t)) for s, e, t in keep if has_khmer(t)]
    else:
        keep = merge_thoughts(keep)
        originals = [t for _, _, t in keep]
        errs = []
        outs = [None] * len(originals)

        if gemini_key or groq_key:
            rep.write("៣/៤ កំពុងសរសេរជាភាសាខ្មែរនិយាយធម្មជាតិ...")
            outs = naturalize(
                originals, [e - s for s, e, _ in keep], dub,
                gemini_key, groq_key, errs,
            )

        missing = [i for i, o in enumerate(outs) if not o]
        if missing:
            rep.write("៣/៤ កំពុងបកប្រែជាភាសាខ្មែរ...")
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
            raise RuntimeError(f"ការបកប្រែបរាជ័យ។ {reason}")

    if not segs:
        raise UserError("រកមិនឃើញអត្ថបទខ្មែរក្នុងសំឡេងនេះទេ។")
    segs.sort(key=lambda x: x[0])

    # កុំឱ្យអក្សរជាន់គ្នា
    segs = [list(x) for x in segs]
    for i in range(len(segs) - 1):
        if segs[i][1] > segs[i + 1][0]:
            segs[i][1] = max(segs[i][0] + 0.2, segs[i + 1][0] - 0.02)
    return [(s, e, t) for s, e, t in segs], failed


# ---------------------------------------------------------------------
# អក្សររត់ (Captions)
# ---------------------------------------------------------------------
def safe_split(word, n):
    """កាត់ពាក្យវែងដោយមិនបំបែកព្យញ្ជនៈជើង ឬស្រៈ។"""
    chunks = []
    while len(word) > n:
        cut = n
        while cut > 1 and ("\u17B6" <= word[cut] <= "\u17D3" or word[cut - 1] == "\u17D2"):
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
    pieces, current = [], ""
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


def build_captions(segments):
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
    return items


def write_ass(path, captions, family, font_size, outline, color, width, height,
              alignment=2, margin_v=35):
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
        f"Style: Default,{family},{font_size},{color},&H000000FF,&H00000000,"
        f"&H64000000,0,0,0,0,100,100,0,0,1,{outline},1,{alignment},20,20,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events = []
    for start, end, text in captions:
        clean = fix_khmer(text).replace("{", "").replace("}", "").replace("\n", " ")
        events.append(
            f"Dialogue: 0,{time_ass(start)},{time_ass(max(start + 0.25, end))},"
            f"Default,,0,0,0,,{clean}"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + events) + "\n")


# ---------------------------------------------------------------------
# សំឡេងអានខ្មែរ (Dubbing)
# ---------------------------------------------------------------------
def tts_segment(text, voice, path):
    async def _go():
        await edge_tts.Communicate(text, voice).save(path)

    asyncio.run(_go())


def make_dub(folder, segments, voice, duration, keep_bg):
    """បង្កើត dub.wav ឱ្យត្រូវតាមម៉ោងនីមួយៗនៃវីដេអូដើម។"""
    n_seg = len(segments)
    if n_seg == 0:
        return False

    paths = [os.path.join(folder, f"tts_{i}.mp3") for i in range(n_seg)]
    durs = [None] * n_seg

    def synth(i):
        try:
            tts_segment(segments[i][2], voice, paths[i])
            durs[i] = probe_video(paths[i])[0]
        except Exception:
            durs[i] = None

    with ThreadPoolExecutor(max_workers=TTS_WORKERS) as ex:
        list(ex.map(synth, range(n_seg)))

    inputs, filters = [], []
    n = 0
    if keep_bg:
        inputs += ["-i", "audio.mp3"]
        filters.append("[0:a]volume=0.15[bg]")
        n = 1

    first_voice = n
    voices = 0
    cursor = 0.0
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
        cursor = start + d / speed + 0.08
        inputs += ["-i", f"tts_{i}.mp3"]
        filters.append(
            f"[{n}:a]atempo={speed:.3f},adelay={int(start * 1000)}:all=1[a{n}]"
        )
        n += 1
        voices += 1

    if voices == 0:
        return False

    labels = ("[bg]" if keep_bg else "") + "".join(
        f"[a{k}]" for k in range(first_voice, n)
    )
    fade_start = max(0.0, duration - 0.6)
    tail = f"alimiter=limit=0.95,afade=t=out:st={fade_start:.2f}:d=0.6[out]"

    fc_a = ";".join(filters) + f";{labels}amix=inputs={n}:dropout_transition=0:normalize=0,{tail}"
    padded = [
        re.sub(r"\[(\w+)\]$", f",apad=whole_dur={duration:.2f}[\\1]", f_)
        for f_ in filters
    ]
    fc_b = (
        ";".join(padded)
        + f";{labels}amix=inputs={n}:dropout_transition=0,volume={n},{tail}"
    )

    for fc in (fc_a, fc_b):
        try:
            run_ffmpeg(
                inputs + ["-filter_complex", fc, "-map", "[out]",
                          "-t", f"{duration:.2f}", "dub.wav"],
                cwd=folder,
            )
            return os.path.exists(os.path.join(folder, "dub.wav"))
        except RuntimeError:
            continue
    return False


# ---------------------------------------------------------------------
# Render វីដេអូ
# ---------------------------------------------------------------------
def build_video_filter(max_side):
    ass = "ass=filename=captions.ass:fontsdir=."
    if max_side and max_side > 0:
        scale = (
            f"scale=w='if(gt(iw,ih),-2,min({max_side},iw))':"
            f"h='if(gt(iw,ih),min({max_side},ih),-2)'"
        )
        return f"{scale},{ass},format=yuv420p"
    return f"{ass},format=yuv420p"


def render_video(folder, font_path, default_name, captions, settings,
                 vid_w, vid_h, dub):
    max_side, crf, preset = settings["quality"]
    align, margin_v = settings["alignment"]
    family = get_font_family(font_path, default_name)

    write_ass(
        os.path.join(folder, "captions.ass"), captions, family,
        settings["font_size"], settings["outline_size"], settings["color"],
        vid_w, vid_h, align, margin_v,
    )

    args = ["-i", "input.mp4"]
    if dub:
        args += ["-i", "dub.wav"]
    args += ["-vf", build_video_filter(max_side)]
    if dub:
        args += ["-map", "0:v:0", "-map", "1:a:0"]
    args += [
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-threads", "0", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", "output.mp4",
    ]
    run_ffmpeg(args, cwd=folder, env=make_fontconfig_env(folder))

    with open(os.path.join(folder, "output.mp4"), "rb") as f:
        return f.read()


# ---------------------------------------------------------------------
# ការងារ (Job) ដំណើរការស្មើគ្នា
# ---------------------------------------------------------------------
class Reporter:
    """ផ្ញើស្ថានភាពពី thread ទៅអេក្រង់ (មិនប្រើ st ក្នុង thread)។"""

    def __init__(self, item):
        self.item = item

    def write(self, message):
        self.item["stage"] = message

    def progress(self, value):
        self.item["pct"] = 0.03 + 0.09 * max(0.0, min(1.0, value))


def new_item(name, path=None, url=None):
    return {
        "name": name, "path": path, "url": url,
        "state": "queued", "stage": "ក្នុងជួររង់ចាំ...", "pct": 0.0,
        "warn": [], "video": None, "captions": [],
        "error": None, "t0": None, "elapsed": None,
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


def run_worker(job, item, settings, font):
    """ដំណើរការវីដេអូមួយ ក្នុង thread ផ្ទាល់ខ្លួន (គ្មានការហៅ st)។"""
    rep = Reporter(item)
    item["t0"] = time.time()
    item["state"] = "running"
    font_file, font_data, font_name = font

    try:
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "input.mp4")
            audio_path = os.path.join(folder, "audio.mp3")

            if item.get("path"):
                shutil.move(item["path"], source)
                item["path"] = None
            else:
                item["pct"] = 0.03
                rep.write("កំពុងទាញយកវីដេអូ...")
                download_video(item["url"], source, rep)

            item["pct"] = 0.12
            rep.write("១/៤ កំពុងរៀបចំ...")
            font_path = os.path.join(folder, font_file)
            with open(font_path, "wb") as f:
                f.write(font_data)

            item["pct"] = 0.18
            rep.write("២/៤ កំពុងដកសំឡេង...")
            extract_audio(source, audio_path)
            duration, vid_w, vid_h = probe_video(source)
            if duration > MAX_DURATION_MIN * 60:
                raise UserError(
                    f"វីដេអូវែងពេក។ សូមប្រើវីដេអូខ្លីជាង {MAX_DURATION_MIN} នាទី។"
                )

            item["pct"] = 0.25
            rep.write("៣/៤ កំពុងស្តាប់ និងបកប្រែជាភាសាខ្មែរ...")
            try:
                segments, failed = transcribe(
                    settings["groq_key"], settings["gemini_key"], audio_path,
                    duration, settings["language"], settings["dub_on"], rep,
                )
            except UserError:
                raise
            except Exception as e:
                low = str(e).lower()
                if any(k in low for k in ("429", "quota", "per day", "resource_exhausted")):
                    raise UserError(
                        "កូតាឥតគិតថ្លៃនៃសេវាបកប្រែអស់ជាបណ្តោះអាសន្ន។ "
                        "សូមរង់ចាំ ១០-៣០ នាទី រួចសាកម្តងទៀត។"
                    )
                raise

            if failed:
                item["warn"].append(
                    "ផ្នែកខ្លះនៃវីដេអូមិនអាចបកប្រែបាន ដូច្នេះអក្សរអាចខ្វះ។"
                )

            item["pct"] = 0.55
            captions = build_captions(segments)
            if not captions:
                raise UserError("រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូនេះទេ។")

            dub_ok = False
            if settings["dub_on"]:
                item["pct"] = 0.6
                rep.write("🎙 កំពុងបង្កើតសំឡេងខ្មែរ...")
                try:
                    dub_ok = make_dub(
                        folder, segments, settings["voice"], duration,
                        settings["keep_bg"],
                    )
                except Exception:
                    dub_ok = False
                if not dub_ok:
                    item["warn"].append("បង្កើតសំឡេងអានមិនបានទេ។ វីដេអូមានតែអក្សរ។")

            item["pct"] = 0.75
            rep.write("៤/៤ កំពុងរង់ចាំដាក់អក្សរចូលវីដេអូ...")
            with job.render_slots:
                item["pct"] = 0.82
                rep.write("៤/៤ កំពុងដាក់អក្សរចូលវីដេអូ...")
                video = render_video(
                    folder, font_path, font_name, captions, settings,
                    vid_w, vid_h, dub_ok,
                )

            if settings.get("font_warn"):
                item["warn"].append(settings["font_warn"])

            item["video"] = video
            item["captions"] = [t for _, _, t in captions]
            item["pct"] = 1.0
            item["stage"] = "រួចរាល់"
            item["elapsed"] = time.time() - item["t0"]
            item["state"] = "done"

    except Exception as error:
        item["error"] = friendly_message(error)
        item["elapsed"] = time.time() - (item["t0"] or time.time())
        item["state"] = "error"
    finally:
        if item["state"] == "running":
            item["error"] = "ការបង្កើតវីដេអូមិនបានសម្រេច។ សូមសាកម្តងទៀត។"
            item["state"] = "error"
        try:
            if item.get("path") and os.path.exists(item["path"]):
                os.remove(item["path"])
        except Exception:
            pass


def build_zip(items):
    ok = [it for it in items if it["state"] == "done" and it["video"]]
    if len(ok) < 2:
        return None
    if sum(len(it["video"]) for it in ok) > MAX_ZIP_MB * 1024 * 1024:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i, it in enumerate(ok, start=1):
            z.writestr(f"{i:02d}_{safe_filename(it['name'])}_khmer.mp4", it["video"])
    return buf.getvalue()


# ---------------------------------------------------------------------
# រចនាប័ទ្ម (CSS) និងមើលជាមុន
# ---------------------------------------------------------------------
CSS = """
.stApp { background: radial-gradient(1100px 600px at 20% -10%, #14205f 0%, #070b26 55%) fixed; color: #e8ecff; }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.block-container { max-width: 1180px; padding-top: 1.2rem; padding-bottom: 4rem; }
.hero { background: linear-gradient(180deg, #131b52, #0d1438); border: 1px solid #1e2a66;
  border-radius: 18px; padding: 14px 20px; margin-bottom: 14px; }
.hero-t { font-size: 1.8rem; font-weight: 800; line-height: 1.5;
  background: linear-gradient(90deg, #3a74ff, #8fb4ff); -webkit-background-clip: text;
  background-clip: text; color: transparent; }
.hero-s { color: #8f9ac8; font-size: 0.9rem; }
.sec { font-size: 1.2rem; font-weight: 800; color: #fff; margin: 16px 0 8px 0;
  border-left: 5px solid #2f6bff; padding-left: 10px; }
div[role="radiogroup"] { gap: 8px !important; flex-wrap: wrap; }
.pv { position: relative; width: 100%; aspect-ratio: 16 / 9; border-radius: 12px;
  overflow: hidden; container-type: size;
  background: linear-gradient(180deg, #27418f, #1a2a66 60%, #0f1a45); }
.pv-cap { position: absolute; left: 0; right: 0; text-align: center; line-height: 1.4; padding: 0 6%; }
"""


def inject_css():
    imports = "".join(
        "@import url('https://fonts.googleapis.com/css2?family="
        + n.replace(" ", "+") + "&display=swap');"
        for n in FONT_NAMES
    )
    st.markdown("<style>" + imports + CSS + "</style>", unsafe_allow_html=True)


def section(title):
    st.markdown(f'<div class="sec">{title}</div>', unsafe_allow_html=True)


def preview_html(text, family, font_size, outline, color_hex, pos):
    size = font_size / 288 * 100
    place = {
        "bottom": "bottom:9%;",
        "middle": "top:50%;transform:translateY(-50%);",
        "top": "top:9%;",
    }.get(pos, "bottom:9%;")
    return (
        '<div class="pv">'
        f'<div class="pv-cap" style="font-family:\'{family}\',sans-serif;'
        f"font-size:{size:.2f}cqh;color:{color_hex};"
        f"-webkit-text-stroke:{outline * 0.7:.2f}cqh #000;"
        f'paint-order:stroke fill;{place}">{html_escape(text)}</div></div>'
    )


try:
    ST_VER = tuple(int(x) for x in re.findall(r"\d+", st.__version__)[:2])
except Exception:
    ST_VER = (1, 0)


def dl_button(label, data, file_name, mime, key, **kwargs):
    extra = {"on_click": "ignore"} if ST_VER >= (1, 43) else {}
    return st.download_button(
        label, data=data, file_name=file_name, mime=mime, key=key, **extra, **kwargs
    )


def work_area(job, was_running):
    """ស្ថានភាព មើលវីដេអូ និងប៊ូតុងទាញយក។"""
    items = job.items
    total = len(items)
    done = sum(1 for it in items if it["state"] == "done")
    failed = sum(1 for it in items if it["state"] == "error")

    st.progress((done + failed) / total, text=f"សរុប {done + failed} / {total}")

    if job.zip:
        dl_button(
            "📦 ទាញយកទាំងអស់ (ZIP)", job.zip, "khmer_videos.zip",
            "application/zip", key=f"zip_{job.id}", use_container_width=True,
        )

    for i, it in enumerate(items, start=1):
        with st.container(border=True):
            tail = ""
            if it["t0"]:
                secs = it["elapsed"] if it["elapsed"] is not None else time.time() - it["t0"]
                tail = f" · ⏱ {int(secs)} វិនាទី"
            st.markdown(f"**{i}. {short_name(it['name'])}**{tail}")

            if it["state"] == "done":
                st.video(it["video"])
                dl_button(
                    "⬇️ ទាញយកវីដេអូនេះ", it["video"],
                    f"{safe_filename(it['name'])}_khmer.mp4", "video/mp4",
                    key=f"dl_{job.id}_{i}", type="primary", use_container_width=True,
                )
                with st.expander("📝 មើលអត្ថបទខ្មែរ"):
                    for text in it["captions"]:
                        st.write(text)
            elif it["state"] == "error":
                st.error(it["error"] or "មិនបានសម្រេច។")
            else:
                st.progress(max(0.0, min(1.0, it["pct"])), text=it["stage"])

    if was_running and not job.running():
        st.rerun()


# ---------------------------------------------------------------------
# ទំព័រមេ
# ---------------------------------------------------------------------
inject_css()

GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")
GROQ_KEY = st.secrets.get("GROQ_API_KEY", "")

if not GROQ_KEY:
    st.error("កម្មវិធីមិនទាន់រួចរាល់ទេ។ សូមទាក់ទងម្ចាស់កម្មវិធី។")
    st.stop()

st.markdown(
    '<div class="hero"><div class="hero-t">បកប្រែរឿងមកនិយាយភាសាខ្មែរ</div>'
    '<div class="hero-s">បង្កើតវីដេអូមានអក្សរខ្មែរ និងសំឡេងអាន AI · '
    f"ធ្វើបានរហូតដល់ {MAX_VIDEOS} វីដេអូស្មើគ្នា</div></div>",
    unsafe_allow_html=True,
)

job = st.session_state.get("job")
if job and not job.running() and not job.zip_done:
    job.zip = build_zip(job.items)
    job.zip_done = True

running = bool(job and job.running())
refresh = REFRESH_SECONDS if running else None

run = False
items = []
left, right = st.columns([1.55, 1], gap="large")

with left:
    section("ផ្ទុកវីដេអូ · Upload")
    uploaded_files = []
    link_text = ""

    with st.container(border=True):
        mode = st.radio(
            "វិធីបញ្ចូលវីដេអូ", [MODE_UP, MODE_LINK, MODE_BATCH],
            horizontal=True, label_visibility="collapsed", key="src_mode",
        )
        if mode == MODE_UP:
            one = st.file_uploader(
                "ទាញវីដេអូមកទីនេះ ឬចុចជ្រើសរើស",
                type=["mp4", "mov", "mkv", "avi", "webm"], key="up_one",
            )
            uploaded_files = [one] if one else []
        elif mode == MODE_LINK:
            link_text = st.text_input(
                "តំណវីដេអូ (.mp4 ផ្ទាល់ ឬ Google Drive សាធារណៈ)",
                placeholder="https://...", key="link_one",
            )
        else:
            uploaded_files = st.file_uploader(
                "ជ្រើសរើសវីដេអូ (ជ្រើសបានច្រើន)",
                type=["mp4", "mov", "mkv", "avi", "webm"],
                accept_multiple_files=True, key="up_many",
            ) or []
            link_text = st.text_area(
                "ឬតំណវីដេអូ — មួយបន្ទាត់ ១ តំណ",
                placeholder="https://...\nhttps://...", height=100, key="links_many",
            )
        st.caption(f"MP4, MOV, MKV, AVI, WEBM · វែងបំផុត {MAX_DURATION_MIN} នាទី")

    with st.container(border=True):
        quality_label = st.selectbox(
            "គុណភាពវីដេអូ", list(QUALITY.keys()), index=1, key="quality"
        )
        language_label = st.selectbox(
            "ភាសាក្នុងវីដេអូ", list(LANGUAGES.keys()), index=0, key="lang",
            help="បើលទ្ធផលមិនត្រឹមត្រូវ សូមជ្រើសភាសាជាក់លាក់ (ឧ. ចិន)។",
        )

    for f in uploaded_files:
        items.append({"name": f.name, "file": f, "url": None})
    link_lines = [
        ln.strip() for ln in (link_text or "").splitlines()
        if ln.strip().lower().startswith(("http://", "https://"))
    ]
    for i, url in enumerate(link_lines, start=1):
        tail = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
        items.append({"name": tail or f"តំណទី {i}", "file": None, "url": url})

    too_many = len(items) > MAX_VIDEOS
    items = items[:MAX_VIDEOS]
    if too_many:
        st.warning(f"អាចធ្វើបានត្រឹម {MAX_VIDEOS} វីដេអូម្តង។")

    if running:
        st.button("⏳ កំពុងធ្វើការ... សូមរង់ចាំ", disabled=True, use_container_width=True)
    elif not items:
        st.button("✨ ចាប់ផ្តើមដំណើរការ", disabled=True, use_container_width=True)
        st.caption("សូមជ្រើសរើសវីដេអូ ឬបិទភ្ជាប់តំណជាមុនសិន។")
    else:
        label = "✨ ចាប់ផ្តើមដំណើរការ"
        if len(items) > 1:
            label += f" ({len(items)} វីដេអូ ស្មើគ្នា)"
        run = st.button(label, type="primary", use_container_width=True)

    section("កំពុងដំណើរការ · Processing")
    if job:
        st.fragment(run_every=refresh)(work_area)(job, running)
    else:
        st.caption("ជ្រើសវីដេអូ រួចចុច «ចាប់ផ្តើមដំណើរការ»។")
        if st.session_state.get("job_cleared"):
            st.session_state.pop("job_cleared", None)

with right:
    s_font = st.session_state.get("font", DEFAULT_FONT)
    if s_font not in FONTS:
        s_font = DEFAULT_FONT
    s_col = st.session_state.get("col", "⚪ ស")
    if s_col not in COLOR_OPTIONS:
        s_col = "⚪ ស"
    s_pos = st.session_state.get("pos", "↓ ក្រោម")
    if s_pos not in POSITIONS:
        s_pos = "↓ ក្រោម"

    with st.container(border=True):
        st.markdown("**🎬 មើលជាមុន · Preview**")
        st.markdown(
            preview_html(
                SAMPLE_TEXT, s_font, st.session_state.get("fs", 22),
                st.session_state.get("ol", 2), COLOR_OPTIONS[s_col][1],
                POSITIONS[s_pos][2],
            ),
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        st.markdown("**🅰 កំណត់អក្សរ · Subtitle**")
        font_size = st.slider("ទំហំអក្សរ", 16, 36, 22, key="fs")
        outline_size = st.slider("កម្រាស់គែមអក្សរ", 1, 5, 2, key="ol")
        font_name = st.selectbox("ពុម្ពអក្សរខ្មែរ (Font)", FONT_NAMES, index=0, key="font")
        font_color = st.radio("ពណ៌អក្សរ", list(COLOR_OPTIONS.keys()), horizontal=True, key="col")
        position_label = st.radio("ទីតាំងអក្សរ", list(POSITIONS.keys()), horizontal=True, key="pos")

    with st.container(border=True):
        st.markdown("**🎙️ សំឡេង AI · Dubbing**")
        dub_on = st.checkbox("បន្ថែមសំឡេងអានជាភាសាខ្មែរ (Dubbing)", key="dub_on")
        voice_label = list(TTS_VOICES.keys())[0]
        keep_bg = False
        if dub_on:
            voice_label = st.selectbox("សំឡេង", list(TTS_VOICES.keys()), key="voice")
            keep_bg = st.checkbox("រក្សាសំឡេងដើមតិចៗ", key="keep_bg")

# ---------- ចាប់ផ្តើមការងារ ----------
if run:
    try:
        font_file, font_data, used_font_name, font_warn = load_font(font_name)
    except Exception:
        st.error("ទាញយក Font ខ្មែរមិនបាន។ សូមសាកម្តងទៀត។")
        st.stop()

    settings = {
        "gemini_key": GEMINI_KEY,
        "groq_key": GROQ_KEY,
        "language": LANGUAGES[language_label],
        "quality": QUALITY[quality_label],
        "dub_on": dub_on,
        "voice": TTS_VOICES[voice_label],
        "keep_bg": keep_bg,
        "font_size": font_size,
        "outline_size": outline_size,
        "color": COLOR_OPTIONS[font_color][0],
        "alignment": POSITIONS[position_label][:2],
        "font_warn": font_warn,
    }

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

    for item in new_job.items:
        threading.Thread(
            target=run_worker,
            args=(new_job, item, settings, (font_file, font_data, used_font_name)),
            daemon=True,
        ).start()

    st.rerun()
