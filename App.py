
import os
import io
import re
import json
import sqlite3
import time
import uuid
import shutil
import asyncio
import zipfile
import tempfile
import threading
import statistics
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
    layout="wide",
)

# =====================================================================
#  THEME (Khmer Video AI — dark)
# =====================================================================
for _k, _v in {
    "theme.base": "dark",
    "theme.primaryColor": "#B13CFF",
    "theme.backgroundColor": "#0A0F2E",
    "theme.secondaryBackgroundColor": "#111842",
    "theme.textColor": "#E8ECFF",
}.items():
    try:
        st._config.set_option(_k, _v)
    except Exception:
        pass

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Kantumruy+Pro:wght@400;500;600;700;800&family=Battambang:wght@400;700&family=Noto+Sans+Khmer:wght@400;500;600;700;800&display=swap');

:root {
  --ink: #E8ECFF;
  --soft: #9AA3D0;
  --bg: #0A0F2E;
  --card: #111842;
  --card2: #0D1438;
  --line: rgba(125,145,255,.22);
  --p1: #B13CFF;
  --p2: #3C6BFF;
  --gold: #F5B72E;
  --r-lg: 20px;
  --r-md: 14px;
  --r-sm: 12px;
}

#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
.stDeployButton, [data-testid="stStatusWidget"], [class*="viewerBadge"],
[data-testid="manage-app-button"] { display: none !important; }

html, body, .stApp, [data-testid="stAppViewContainer"] {
  background: radial-gradient(900px 480px at 15% -8%, #2B1B72 0%, rgba(10,15,46,0) 60%), #0A0F2E !important;
  color: var(--ink);
  font-family: 'Kantumruy Pro', 'Noto Sans Khmer', 'Battambang', system-ui, sans-serif !important;
  color-scheme: dark;
}
.stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp li, .stApp small,
.stApp textarea, .stApp input, .stApp button p, .stApp a,
.stApp [data-baseweb="select"] div, .stApp [data-testid="stMarkdownContainer"] {
  font-family: 'Kantumruy Pro', 'Battambang', system-ui, sans-serif;
}
[data-testid="stIconMaterial"], [class*="material-symbols"], .material-icons {
  font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}
[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 1240px; padding: 1rem 1.2rem 4rem; }

.stMarkdown, .stMarkdown p, [data-testid="stText"], h1, h2, h3,
label, [data-testid="stWidgetLabel"] p, [data-testid="stCheckbox"] p,
[data-testid="stToggle"] p {
  color: var(--ink) !important;
}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--soft) !important; }

/* ---------- Header ---------- */
.kvai-head { display: flex; align-items: center; gap: 14px; margin: 4px 0 16px; flex-wrap: wrap; }
.kvai-logo {
  width: 54px; height: 54px; border-radius: 16px;
  background: linear-gradient(135deg, #3C6BFF, #B13CFF);
  display: flex; align-items: center; justify-content: center; font-size: 28px;
  box-shadow: 0 8px 22px rgba(60,107,255,.45);
}
.kvai-title { flex: 1; min-width: 190px; }
.kvai-title h1 {
  margin: 0 !important; padding: 0 !important;
  font-size: clamp(1.5rem, 6vw, 2rem) !important;
  font-weight: 800 !important; line-height: 1.2 !important; color: #fff !important;
}
.kvai-title h1 span {
  background: linear-gradient(90deg, #B13CFF, #3C6BFF);
  -webkit-background-clip: text; background-clip: text;
  color: transparent !important; -webkit-text-fill-color: transparent;
}
.kvai-title p { margin: 2px 0 0; color: var(--soft) !important; font-size: .9rem; }
.kvai-badge {
  border: 1.5px solid var(--p2); color: var(--gold) !important;
  padding: 8px 14px; border-radius: 999px; font-weight: 700; font-size: .9rem;
  background: rgba(60,107,255,.12);
}

/* ---------- Nav ---------- */
.kvai-nav {
  display: flex; gap: 4px; padding: 4px; margin-bottom: 8px; overflow-x: auto;
  background: var(--card); border: 1px solid var(--line); border-radius: 16px;
}
.kvai-nav a {
  flex: 1; text-align: center; padding: 11px 14px; border-radius: 12px; white-space: nowrap;
  color: var(--soft) !important; text-decoration: none !important; font-weight: 600;
}
.kvai-nav a.on { background: linear-gradient(135deg, var(--p1), var(--p2)); color: #fff !important; }
.kvai-nav a:hover { color: #fff !important; }

/* ---------- Tabs ---------- */
[data-baseweb="tab-list"] {
  background: var(--card); border: 1px solid var(--line);
  border-radius: 16px; padding: 4px; gap: 2px;
}
button[data-baseweb="tab"] {
  flex: 1; height: 46px; border-radius: 12px;
  background: transparent !important; color: var(--soft) !important;
}
button[data-baseweb="tab"] [data-testid="stMarkdownContainer"] p { color: inherit !important; font-weight: 600; }
button[data-baseweb="tab"][aria-selected="true"] {
  background: linear-gradient(135deg, var(--p1), var(--p2)) !important;
  color: #fff !important;
}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none !important; }

/* ---------- Section headings ---------- */
[data-testid="stHeading"] h3, .stApp h3 {
  font-size: 1.1rem !important; font-weight: 600 !important;
  margin: 1.4rem 0 .6rem !important; padding: 0 !important; border: none !important;
}
[data-testid="stHeading"] h3::after {
  content: ""; display: block; width: 34px; height: 4px; border-radius: 4px;
  background: linear-gradient(90deg, var(--p1), var(--p2)); margin-top: 6px;
}

/* ---------- Cards ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: rgba(17,24,66,.85) !important;
  border: 1px solid var(--line) !important;
  border-radius: var(--r-lg) !important;
  box-shadow: 0 6px 22px rgba(0,0,0,.25);
  padding: 6px 4px;
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlockBorderWrapper"] {
  box-shadow: none; background: rgba(13,20,56,.9) !important;
}

/* ---------- Select ---------- */
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-baseweb="select"] > div {
  background-color: var(--card2) !important;
  border: 1.5px solid var(--line) !important;
  border-radius: var(--r-sm) !important;
  color: var(--ink) !important;
  min-height: 48px;
}
[data-baseweb="select"] > div:focus-within, [data-baseweb="select"] > div:hover {
  border-color: var(--p2) !important;
  box-shadow: 0 0 0 3px rgba(60,107,255,.2) !important;
}
[data-baseweb="select"] * { color: var(--ink) !important; }
[data-baseweb="select"] svg { fill: var(--ink) !important; }
[data-baseweb="popover"] ul, [data-baseweb="popover"] li, [data-baseweb="menu"] {
  background: #121A4A !important; color: var(--ink) !important;
}
[data-baseweb="popover"] li:hover { background: rgba(177,60,255,.25) !important; }

/* ---------- Text area ---------- */
.stTextArea textarea, [data-baseweb="textarea"], [data-baseweb="textarea"] > div {
  background: var(--card2) !important;
  border: 1.5px solid var(--line) !important;
  border-radius: var(--r-sm) !important;
  color: var(--ink) !important;
}
.stTextArea textarea:focus { border-color: var(--p2) !important; box-shadow: 0 0 0 3px rgba(60,107,255,.2) !important; }

/* ---------- Radio => pills ---------- */
[data-testid="stRadio"] [role="radiogroup"] { gap: 8px; flex-wrap: wrap; width: 100%; }
[data-testid="stRadio"] label {
  flex: 1 1 auto;
  justify-content: center;
  background: var(--card2);
  border: 1.5px solid var(--line);
  border-radius: 999px;
  padding: 8px 14px !important;
  margin: 0 !important;
  cursor: pointer;
}
[data-testid="stRadio"] label > div:first-child { display: none !important; }
[data-testid="stRadio"] label:has(input:checked) {
  background: linear-gradient(135deg, var(--p1), var(--p2));
  border-color: transparent;
  box-shadow: 0 4px 14px rgba(60,107,255,.35);
}
[data-testid="stRadio"] label:has(input:checked) *,
[data-testid="stRadio"] label:has(input:checked) p { color: #fff !important; }
.st-key-pos [role="radiogroup"] {
  display: grid !important; grid-template-columns: repeat(3, 1fr); max-width: 260px;
}

/* ---------- Checkbox / Toggle ---------- */
[data-testid="stCheckbox"] label > span:first-child,
[data-baseweb="checkbox"] > span:first-child {
  border-radius: 7px !important;
  border: 1.5px solid #5560A8 !important;
  background-color: var(--card2) !important;
}
[data-testid="stCheckbox"] label:has(input:checked) > span:first-child,
[data-baseweb="checkbox"]:has(input:checked) > span:first-child {
  background: linear-gradient(135deg, var(--p1), var(--p2)) !important;
  border-color: transparent !important;
}
[data-testid="stToggle"] label > div:first-child { background: #2A3166 !important; }
[data-testid="stToggle"] label:has(input:checked) > div:first-child {
  background: linear-gradient(90deg, var(--p1), var(--p2)) !important;
}

/* ---------- Slider ---------- */
[data-testid="stSlider"] [role="slider"] { background: #fff !important; border-color: var(--p1) !important; }
[data-testid="stSlider"] [data-testid="stThumbValue"] { color: var(--ink) !important; }
[data-testid="stSlider"] [data-testid="stTickBarMin"], [data-testid="stSlider"] [data-testid="stTickBarMax"] { color: var(--soft) !important; }

/* ---------- Uploader ---------- */
[data-testid="stFileUploaderDropzone"] {
  background: rgba(20,30,90,.35);
  border: 2px dashed var(--p2);
  border-radius: var(--r-lg);
  padding: 22px 16px;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--p1); background: rgba(40,30,110,.45); }
[data-testid="stFileUploaderDropzone"] * { color: var(--ink) !important; }
[data-testid="stFileUploaderDropzone"] button {
  background: linear-gradient(135deg, var(--p1), var(--p2)) !important; color: #fff !important;
  border-radius: var(--r-sm) !important; border: none !important;
}
[data-testid="stFileUploaderDropzone"] button * { color: #fff !important; }
[data-testid="stFileUploaderFile"] * { color: var(--ink) !important; }

/* ---------- Buttons ---------- */
.stButton > button, .stDownloadButton > button {
  border-radius: var(--r-md);
  border: 1.5px solid var(--line);
  background: var(--card);
  color: var(--ink);
  font-weight: 700;
  min-height: 50px;
  transition: transform .12s ease, box-shadow .12s ease;
}
.stButton > button *, .stDownloadButton > button * { color: inherit !important; }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(90deg, var(--p1), var(--p2)) !important;
  border: none !important;
  color: #fff !important;
  min-height: 58px;
  font-size: 1.08rem;
  box-shadow: 0 10px 26px rgba(120,60,255,.4);
}
.stButton > button[kind="primary"] *, .stDownloadButton > button[kind="primary"] * { color: #fff !important; }
.stButton > button:hover, .stDownloadButton > button:hover { transform: translateY(-1px); border-color: var(--p2); }
.stButton > button:focus-visible { outline: 3px solid var(--gold); outline-offset: 2px; }
.stButton > button:disabled { background: #1B2250 !important; color: #6E77A8 !important; box-shadow: none; transform: none; }

/* ---------- Progress ---------- */
[data-testid="stProgress"] > div > div { background: #1B2250 !important; border-radius: 999px; }
[data-testid="stProgress"] > div > div > div { background: linear-gradient(90deg, var(--p1), var(--p2)) !important; border-radius: 999px; }

/* ---------- Metrics ---------- */
[data-testid="stMetric"] {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 12px 14px;
}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * { font-weight: 800; color: #fff !important; }
[data-testid="stMetricLabel"] p { color: var(--soft) !important; font-weight: 500; }

/* ---------- Alerts ---------- */
[data-testid="stAlert"] { border-radius: var(--r-md); border: none; }
[data-testid="stAlert"] * { color: var(--ink) !important; }

/* ---------- Expander ---------- */
[data-testid="stExpander"] {
  background: rgba(13,20,56,.9);
  border: 1.5px solid var(--line) !important;
  border-radius: var(--r-md);
}
[data-testid="stExpander"] * { color: var(--ink) !important; }

[data-testid="stVideo"] video { border-radius: var(--r-md); background: #000; }
hr { border-color: var(--line) !important; margin: 1.6rem 0 !important; }

/* ---------- Subtitle preview ---------- */
.kvai-prev {
  height: 300px; border-radius: 16px; border: 1px solid var(--line);
  background: linear-gradient(160deg, #3A2C6E 0%, #1B2A5E 60%, #0E1636 100%);
  display: flex; padding: 14px 18px; margin: 6px 0 10px;
}
.kvai-prev span {
  font-family: 'Battambang', 'Kantumruy Pro', sans-serif;
  padding: 3px 10px; border-radius: 6px; line-height: 1.5;
}
</style>
"""

COMPACT_CSS = """
<style>
.block-container { padding: .6rem .8rem 5.5rem !important; }
[data-testid="stVerticalBlock"] { gap: .55rem; }

/* header តូច */
.kvai-head { margin: 0 0 8px; gap: 10px; flex-wrap: nowrap; }
.kvai-logo { width: 42px; height: 42px; font-size: 22px; border-radius: 13px; }
.kvai-title { min-width: 0; }
.kvai-title h1 { font-size: 1.35rem !important; }
.kvai-title p { font-size: .75rem; margin: 0; }
.kvai-badge { padding: 5px 10px; font-size: .75rem; white-space: nowrap; }

/* tabs */
[data-baseweb="tab-list"] { overflow-x: auto; }
button[data-baseweb="tab"] { height: 40px; padding: 0 4px !important; min-width: 0; }
button[data-baseweb="tab"] p { font-size: .8rem !important; white-space: nowrap; }

/* ជួរឈរមិនបត់ចុះក្រោមលើទូរស័ព្ទ */
[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .6rem !important; }
[data-testid="stColumn"] { min-width: 0 !important; }

/* សមាសភាគតូចជាង */
[data-testid="stWidgetLabel"] p { font-size: .85rem; }
[data-testid="stSelectbox"] [data-baseweb="select"] > div { min-height: 42px; }
[data-testid="stRadio"] label { padding: 5px 10px !important; font-size: .85rem; }
[data-testid="stFileUploaderDropzone"] { padding: 10px; }
[data-testid="stVideo"] video { max-height: 150px; }
div[data-testid="stVerticalBlockBorderWrapper"] { padding: 4px 2px; }
.kvai-prev { height: 120px; padding: 8px 12px; margin: 0; }
.st-key-pos [role="radiogroup"] { max-width: 100%; }

/* ប៊ូតុងចាប់ផ្តើមជាប់ខាងក្រោម */
.st-key-startbar {
  position: fixed; bottom: 0; left: 50%; transform: translateX(-50%);
  width: min(100%, 1240px); z-index: 999;
  padding: 18px 12px calc(10px + env(safe-area-inset-bottom));
  background: linear-gradient(180deg, rgba(10,15,46,0), #0A0F2E 35%);
}
.st-key-startbar .stButton > button { min-height: 52px; }
</style>
"""


def apply_theme():
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    st.markdown(COMPACT_CSS, unsafe_allow_html=True)


def render_header():
    st.markdown(
        """
        <div class="kvai-head">
          <div class="kvai-logo">🎬</div>
          <div class="kvai-title">
            <h1>Khmer Video <span>AI</span></h1>
            <p>បកប្រែវីដេអូ និងបង្កើតអក្សរ/សំឡេងខ្មែរ ដោយ AI</p>
          </div>
          <div class="kvai-badge">👑 Free AI</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ទីតាំងអក្សរ (ASS alignment: 1-9 តាមលេខក្តារចុច)
POS_MAP = {
    "↖": 7, "↑": 8, "↗": 9,
    "←": 4, "●": 5, "→": 6,
    "↙": 1, "↓": 2, "↘": 3,
}
# (ឈ្មោះ, ពណ៌ ASS (BGR), ពណ៌ HTML)
COLOR_OPTIONS = {
    "⚪ ស": ("&H00FFFFFF", "#FFFFFF"),
    "🟡 លឿង": ("&H0000FFFF", "#FFE600"),
    "🟢 បៃតង": ("&H0000FF00", "#00E640"),
    "🔵 ខៀវ": ("&H00FF6B2F", "#2F6BFF"),
    "🔴 ក្រហម": ("&H000000FF", "#FF2D2D"),
    "🟣 ស្វាយ": ("&H00FF3CB1", "#B13CFF"),
    "🟠 ទឹកក្រូច": ("&H000095FF", "#FF9500"),
    "⚫ ខ្មៅ": ("&H00000000", "#000000"),
}
BOX_OPTIONS = {
    "🚫 គ្មាន": "none",
    "◼ ស្រអាប់": "soft",
    "⬛ ខ្មៅ": "black",
    "⬜ ស": "white",
}
STYLE_OPTIONS = {
    "ធម្មតា": (False, False),
    "ដិត": (True, False),
    "ទ្រេត": (False, True),
    "ដិត+ទ្រេត": (True, True),
}
PREVIEW_TEXT = "ខ្ញុំមិនអាចបាត់បង់អ្នកបានទេ"


def render_preview(font_size, color_hex, align, bold, italic, box):
    jc = {1: "flex-start", 2: "center", 3: "flex-end", 4: "flex-start", 5: "center",
          6: "flex-end", 7: "flex-start", 8: "center", 9: "flex-end"}[align]
    ai = {1: "flex-end", 2: "flex-end", 3: "flex-end", 4: "center", 5: "center",
          6: "center", 7: "flex-start", 8: "flex-start", 9: "flex-start"}[align]
    px = max(10, int(font_size * 300 / 288))
    bg = {"none": "transparent", "soft": "rgba(0,0,0,.6)", "black": "#000", "white": "#fff"}[box]
    shadow = ""
    if box == "none":
        shadow = "text-shadow:-1px -1px 0 #000,1px -1px 0 #000,-1px 1px 0 #000,1px 1px 0 #000;"
    weight = 700 if bold else 400
    fstyle = "italic" if italic else "normal"
    st.markdown(
        f'<div class="kvai-prev" style="justify-content:{jc};align-items:{ai}">'
        f'<span style="font-size:{px}px;color:{color_hex};background:{bg};'
        f'font-weight:{weight};font-style:{fstyle};{shadow}">{PREVIEW_TEXT}</span></div>',
        unsafe_allow_html=True,
    )


def srt_time(sec):
    ms = max(0, int(round(float(sec) * 1000)))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def make_srt(captions):
    out = []
    for i, (s, e, t) in enumerate(captions, start=1):
        out.append(f"{i}\n{srt_time(s)} --> {srt_time(max(s + 0.25, e))}\n{fix_khmer(t)}\n")
    return "\n".join(out)

apply_theme()


def get_secret(name, default=""):
    """អាន secret ពី Environment Variable (Hugging Face Spaces) ឬ Streamlit secrets។"""
    val = os.environ.get(name)
    if val:
        return val
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


# =====================================================================
#  MAINTENANCE MODE — ដាក់ True = បិទកម្មវិធីសម្រាប់អ្នកប្រើ / False = បើកធម្មតា
#  ម្ចាស់កម្មវិធីអាចចូលបាន ដោយបញ្ចូលលេខសម្ងាត់ OWNER_KEY
# =====================================================================
MAINTENANCE = True
OWNER_KEY = str(get_secret("OWNER_KEY", "")).strip()

if MAINTENANCE and not st.session_state.get("owner_ok"):
    render_header()
    st.markdown(
        """
        <div style="max-width:560px;margin:40px auto 16px;padding:36px 24px;text-align:center;
                    background:rgba(17,24,66,.85);border:1px solid rgba(125,145,255,.22);
                    border-radius:24px;box-shadow:0 6px 22px rgba(0,0,0,.25);">
          <div style="font-size:64px;line-height:1;">🛠️</div>
          <h2 style="margin:16px 0 8px;color:#fff;font-weight:800;">កំពុងជួសជុល</h2>
          <p style="color:#9AA3D0;font-size:1.05rem;margin:0;">
            កម្មវិធីបិទជាបណ្ដោះអាសន្នដើម្បីកែលម្អ។<br>
            សូមអភ័យទោស និងសូមត្រឡប់មកវិញនៅពេលក្រោយ 🙏
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("🔑 សម្រាប់ម្ចាស់កម្មវិធី"):
        _pw = st.text_input("លេខសម្ងាត់ម្ចាស់", type="password", key="owner_pw")
        if st.button("ចូល", key="owner_go", use_container_width=True):
            if OWNER_KEY and _pw.strip() == OWNER_KEY:
                st.session_state["owner_ok"] = True
                st.rerun()
            else:
                st.error("លេខសម្ងាត់មិនត្រឹមត្រូវ ឬមិនទាន់កំណត់ OWNER_KEY។")
    st.stop()

# បង្ហាញព័ត៌មានលម្អិត (DEBUG) ជានិច្ច ដល់អ្នកប្រើទាំងអស់
DEBUG = True

REQUEST_TIMEOUT_MS = 120000
TRANSLATE_TIMEOUT_MS = 40000   # ការបកប្រែអត្ថបទ: មិនរង់ចាំលើសពី ៤០ វិនាទី
MAX_CAPTION_CHARS = 26
MAX_DOWNLOAD_MB = 1024
MAX_VIDEOS = 5
MAX_ZIP_MB = 250
REFRESH_SECONDS = 2
MAX_RENDER_AT_ONCE = 2
MAX_DURATION_MIN = 300

# Shared gallery: all users of the same running app instance can see saved videos.
# For durable storage across app restarts/redeploys, set KAC_PUBLIC_STORAGE_DIR
# to a persistent mounted directory (for example a volume).
PUBLIC_STORAGE_DIR = os.environ.get(
    "KAC_PUBLIC_STORAGE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "public_video_storage"),
)
PUBLIC_VIDEO_DIR = os.path.join(PUBLIC_STORAGE_DIR, "videos")
PUBLIC_DB_PATH = os.path.join(PUBLIC_STORAGE_DIR, "gallery.sqlite3")
_gallery_lock = threading.Lock()


def init_public_gallery():
    os.makedirs(PUBLIC_VIDEO_DIR, exist_ok=True)
    with _gallery_lock:
        with sqlite3.connect(PUBLIC_DB_PATH, timeout=30) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS public_videos (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    size_bytes INTEGER NOT NULL
                )
            """)
            db.commit()


def save_to_public_gallery(name, video_bytes):
    """Persist a finished video into the app-wide gallery."""
    if not video_bytes:
        return False
    init_public_gallery()
    video_id = uuid.uuid4().hex
    filename = f"{video_id}_{safe_filename(name)}.mp4"
    full_path = os.path.join(PUBLIC_VIDEO_DIR, filename)
    try:
        with open(full_path, "wb") as f:
            f.write(video_bytes)
        with _gallery_lock:
            with sqlite3.connect(PUBLIC_DB_PATH, timeout=30) as db:
                db.execute(
                    "INSERT INTO public_videos (id, name, filename, created_at, size_bytes) VALUES (?, ?, ?, ?, ?)",
                    (video_id, safe_filename(name), filename, time.time(), len(video_bytes)),
                )
                db.commit()
        return True
    except Exception:
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception:
            pass
        return False


def read_public_gallery():
    init_public_gallery()
    with _gallery_lock:
        with sqlite3.connect(PUBLIC_DB_PATH, timeout=30) as db:
            rows = db.execute(
                "SELECT id, name, filename, created_at, size_bytes FROM public_videos ORDER BY created_at DESC"
            ).fetchall()
    return rows


CHUNK_TARGET = 20.0
CHUNK_MAX = 28.0
MAX_CHUNK_WORKERS = 3

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODELS = ["whisper-large-v3", "whisper-large-v3-turbo"]

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
_groq_chat_cache = {"models": None, "good": None}

WHISPER_LANG = {
    "Khmer": "km", "English": "en", "Thai": "th", "Vietnamese": "vi",
    "Chinese": "zh", "Japanese": "ja", "Korean": "ko", "French": "fr",
}

CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")

try:
    ST_VER = tuple(int(x) for x in re.findall(r"\d+", st.__version__)[:2])
except Exception:
    ST_VER = (1, 0)

PREFERRED_MODELS = [
    "gemini-3.8-flash", "gemini-3-flash", "gemini-flash-latest",
    "gemini-2.5-flash", "gemini-2.5-pro", "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
]

GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"

FONT_SOURCES = [
    ("Battambang.ttf", GF + "battambang/Battambang-Regular.ttf", "Battambang"),
    ("Content.ttf", GF + "content/Content-Regular.ttf", "Content"),
    ("Siemreap.ttf", GF + "siemreap/Siemreap-Regular.ttf", "Siemreap"),
    ("Bokor.ttf", GF + "bokor/Bokor-Regular.ttf", "Bokor"),
]

QUALITY = {
    "⚡ លឿន 480p": (480, 28, "ultrafast"),
    "✨ ល្អ 720p": (720, 24, "veryfast"),
    "💎 ខ្ពស់ (ដើម)": (0, 20, "veryfast"),
}

LANGUAGES = {
    "🌐 ស្វ័យប្រវត្តិ (ភាសាអ្វីក៏បាន)": None,
    "ខ្មែរ": "Khmer", "អង់គ្លេស": "English", "ថៃ": "Thai",
    "វៀតណាម": "Vietnamese", "ចិន": "Chinese", "ជប៉ុន": "Japanese",
    "កូរ៉េ": "Korean", "បារាំង": "French",
}

TTS_VOICES = {
    "👩 ស្រី (Sreymom)": "km-KH-SreymomNeural",
    "👨 ប្រុស (Piseth)": "km-KH-PisethNeural",
}


class UserError(RuntimeError):
    pass


def friendly_message(error):
    if isinstance(error, UserError):
        return str(error)
    low = str(error).lower()
    if "429" in low or "resource_exhausted" in low or "quota" in low:
        return "មានអ្នកប្រើច្រើនពេក។ សូមរង់ចាំមួយភ្លែត។"
    if any(x in low for x in ("503", "unavailable", "high demand", "overloaded", "timeout", "timed out")):
        return "ប្រព័ន្ធ AI កំពុងរវល់។ សូមសាកម្តងទៀត។"
    if "api key" in low or "api_key" in low or "permission" in low:
        return "សេវា AI មានបញ្ហា។ សូមទាក់ទងម្ចាស់កម្មវិធី។"
    return "ការបង្កើតវីដេអូមិនបានសម្រេច។ សូមសាកម្តងទៀត។"


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


def khmer_ratio(segments):
    if not segments:
        return 0.0
    return sum(1 for _, _, t in segments if has_khmer(t)) / len(segments)


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
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=True, cwd=cwd, env=full_env,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", "ignore")[-1500:]
        raise RuntimeError("FFmpeg បរាជ័យ:\n" + err)
    return (result.stderr or b"").decode("utf-8", "ignore")


def probe_media(path):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [exe, "-i", path], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    err = result.stderr
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not match:
        raise UserError("មិនអាចអានឯកសារនេះបានទេ។")
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


def probe_video(path):
    return probe_media(path)


def time_ass(seconds):
    cs = max(0, int(round(float(seconds) * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


@st.cache_resource(show_spinner=False)
def load_font_bytes():
    out = []
    for i, (filename, url, default_name) in enumerate(FONT_SOURCES):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
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
    fonts = []
    for filename, data, default_name in fonts_data:
        path = os.path.join(folder, filename)
        with open(path, "wb") as f:
            f.write(data)
        fonts.append((path, default_name))
    return fonts


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
    return {"FONTCONFIG_FILE": conf_path, "FONTCONFIG_PATH": folder}


def font_was_used(log, keys):
    lines = [l for l in log.splitlines() if "fontselect" in l.lower()]
    if not lines:
        return True
    for line in lines:
        right = line.split("->", 1)[-1].lower()
        if any(k in right for k in keys):
            return True
    return False


def normalize_link(url):
    url = url.strip()
    match = re.search(r"drive\.google\.com/file/d/([\w-]+)", url)
    if not match:
        match = re.search(r"drive\.google\.com/open\?id=([\w-]+)", url)
    if match:
        return "https://drive.google.com/uc?export=download&id=" + match.group(1)
    return url


def download_video(url, path, progress):
    url = normalize_link(url)
    limit = MAX_DOWNLOAD_MB * 1024 * 1024
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            ctype = (response.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype:
                raise UserError("តំណនេះមិនមែនជាវីដេអូផ្ទាល់ទេ។")
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
                        raise UserError(f"វីដេអូធំជាង {MAX_DOWNLOAD_MB}MB។")
                    if total:
                        progress.progress(min(1.0, done / total))
    except UserError:
        raise
    except Exception:
        raise UserError("ទាញយកវីដេអូពីតំណមិនបានទេ។")
    if os.path.getsize(path) < 1000:
        raise UserError("ទាញយកវីដេអូមិនបាន។")
    progress.progress(1.0)


def extract_audio(video_path, audio_path, master_path):
    try:
        run_ffmpeg([
            "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", audio_path,
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac", master_path,
        ])
    except RuntimeError:
        raise UserError("មិនអាចដកសំឡេងពីវីដេអូនេះបានទេ។")


# =====================================================================
#  Gemini ច្រើន Key: ប្តូរស្វ័យប្រវត្តិពេល Key មួយអស់កូតា ឬមិនត្រឹមត្រូវ
# =====================================================================
_GEM_COOL = {}          # key -> ម៉ោងដែលអាចប្រើបានវិញ
_GEM_LOCK = threading.Lock()
GEM_COOLDOWN = 65       # វិនាទី


def split_keys(value):
    if isinstance(value, (list, tuple)):
        value = "\n".join("\n".join(split_keys(v)) for v in value)
    elif value is not None and not isinstance(value, str) and hasattr(value, "__iter__"):
        value = "\n".join("\n".join(split_keys(v)) for v in value)
    out = []
    for k in re.split(r"[\s,;]+", str(value or "")):
        k = k.strip().strip('"').strip("'")
        if k and k not in out:
            out.append(k)
    return out


def _gem_retryable(err):
    low = str(err).lower()
    return any(x in low for x in ("429", "resource_exhausted", "quota", "rate limit",
                                  "api key not valid", "api_key_invalid", "permission_denied", "403"))


class _RotModels:
    def __init__(self, clients):
        self.clients = clients  # [(key, client)]

    def _order(self):
        now = time.time()
        with _GEM_LOCK:
            ready = [kc for kc in self.clients if _GEM_COOL.get(kc[0], 0) <= now]
            cooling = [kc for kc in self.clients if _GEM_COOL.get(kc[0], 0) > now]
        cooling.sort(key=lambda kc: _GEM_COOL.get(kc[0], 0))
        return ready + cooling

    def _call(self, name, *args, **kwargs):
        last = None
        order = self._order()
        for n, (key, client) in enumerate(order):
            try:
                return getattr(client.models, name)(*args, **kwargs)
            except Exception as e:
                last = e
                if _gem_retryable(e) and n < len(order) - 1:
                    with _GEM_LOCK:
                        _GEM_COOL[key] = time.time() + GEM_COOLDOWN
                    continue
                raise
        raise last

    def generate_content(self, *args, **kwargs):
        return self._call("generate_content", *args, **kwargs)

    def list(self, *args, **kwargs):
        return self._call("list", *args, **kwargs)


class RotatingGemini:
    def __init__(self, keys, http_options=None):
        self.models = _RotModels([(k, genai.Client(api_key=k, http_options=http_options)) for k in keys])


def make_gemini_client(api_key, http_options=None):
    keys = split_keys(api_key)
    if len(keys) <= 1:
        return genai.Client(api_key=(keys[0] if keys else api_key), http_options=http_options)
    return RotatingGemini(keys, http_options)


_GROQ_COOL = {}
GROQ_COOLDOWN = 60


def groq_first(api_key):
    keys = split_keys(api_key)
    return keys[0] if keys else str(api_key or "")


def groq_urlopen(request, api_key, timeout=60):
    """urlopen សម្រាប់ Groq: ប្តូរ key ស្វ័យប្រវត្តិពេល 429/401/403 (ពេលមាន key ច្រើន)។"""
    keys = split_keys(api_key)
    if len(keys) <= 1:
        return urllib.request.urlopen(request, timeout=timeout)
    now = time.time()
    with _GEM_LOCK:
        ready = [k for k in keys if _GROQ_COOL.get(k, 0) <= now]
        cooling = sorted([k for k in keys if _GROQ_COOL.get(k, 0) > now], key=lambda k: _GROQ_COOL[k])
    order = ready + cooling
    last = None
    for n, key in enumerate(order):
        request.headers["Authorization"] = f"Bearer {key}"
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 401, 403) and n < len(order) - 1:
                with _GEM_LOCK:
                    _GROQ_COOL[key] = time.time() + GROQ_COOLDOWN
                continue
            raise
    raise last


_MODEL_COOL = {}     # model -> ម៉ោងដែលអាចសាកម្តងទៀត
_MODEL_GOOD = {}     # provider -> ម៉ូដែលដែលបានជោគជ័យចុងក្រោយ


def model_cool(model, error_text):
    """កត់ត្រាថ្នាក់ម៉ូដែលខូច/ពេញកូតា ដើម្បីប្តូរទៅម៉ូដែលផ្សេងដោយស្វ័យប្រវត្តិ។"""
    low = str(error_text).lower()
    if any(x in low for x in ("404", "not found", "decommission", "does not exist", "no longer", "deprecated", "model_not_found", "not supported")):
        secs = 3600
    elif any(x in low for x in ("per day", "daily", "tokens per day", "requests per day")):
        secs = 1800
    elif "429" in low or "quota" in low or "resource_exhausted" in low or "rate limit" in low:
        secs = 90
    elif any(x in low for x in ("500", "502", "503", "504", "overloaded", "unavailable", "timeout", "timed out", "high demand")):
        secs = 30
    else:
        secs = 15
    with _GEM_LOCK:
        _MODEL_COOL[model] = time.time() + secs


def model_order(models, provider=None):
    """ម៉ូដែលល្អនៅមុខ ម៉ូដែលកំពុងសម្រាកនៅក្រោយ (មិនលុបចោលទាំងស្រុង)។"""
    now = time.time()
    models = list(models)
    with _GEM_LOCK:
        ready = [m for m in models if _MODEL_COOL.get(m, 0) <= now]
        cooling = sorted([m for m in models if _MODEL_COOL.get(m, 0) > now], key=lambda m: _MODEL_COOL[m])
        good = _MODEL_GOOD.get(provider)
    if good in ready:
        ready = [good] + [m for m in ready if m != good]
    return ready + cooling


def model_good(provider, model):
    with _GEM_LOCK:
        _MODEL_GOOD[provider] = model
        _MODEL_COOL.pop(model, None)


_MODELS_CACHE = {"t": 0.0, "v": None}


def get_available_models(client):
    if _MODELS_CACHE["v"] and time.time() - _MODELS_CACHE["t"] < 600:
        return list(_MODELS_CACHE["v"])
    res = _get_available_models_uncached(client)
    if res:
        _MODELS_CACHE["v"], _MODELS_CACHE["t"] = list(res), time.time()
    return res


def _get_available_models_uncached(client):
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
            if any(x in low for x in ("tts", "live", "embedding", "image", "imagen", "veo", "robotics")):
                continue
            found.append(name)
    except Exception:
        pass
    ordered = [m for m in PREFERRED_MODELS if m in found]
    rest = [m for m in found if m not in ordered]
    rest.sort(key=lambda m: ("lite" in m.lower(), "flash" not in m.lower()))
    ordered += rest
    ordered = (
        [m for m in ordered if "lite" not in m.lower()]
        + [m for m in ordered if "lite" in m.lower()]
    )
    return ordered[:6]


def parse_segments(raw, duration):
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
    for i in range(len(segments) - 1):
        if segments[i][1] > segments[i + 1][0]:
            segments[i][1] = max(segments[i][0] + 0.2, segments[i + 1][0] - 0.02)
    return [(s, e, t) for s, e, t in segments]


def plain_to_segments(text, duration):
    text = fix_khmer(text)
    if not text:
        return []
    sentences = [fix_khmer(p) for p in re.split(r"(?<=[។.!?])\s+|\n+", text) if fix_khmer(p)]
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


def safe_split(word, n):
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
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [exe, "-i", audio_path, "-af", "silencedetect=noise=-32dB:d=0.35", "-f", "null", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        err = result.stderr
        starts = [max(0.0, float(x)) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", err)]
        ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", err)]
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
    segs = sorted([[s, e, t] for s, e, t in segments], key=lambda x: x[0])
    total_speech = sum(b - a for a, b in speech)
    if not speech or duration <= 0 or total_speech / duration >= 0.9:
        return [(s, e, t) for s, e, t in segs]
    for sg in segs:
        s, e = sg[0], sg[1]
        near_starts = [a for a, b in speech if abs(a - s) <= 0.8]
        ns = min(near_starts, key=lambda a: abs(a - s)) if near_starts else s
        near_ends = [b for a, b in speech if abs(b - e) <= 0.8 and b > ns + 0.3]
        ne = min(near_ends, key=lambda b: abs(b - e)) if near_ends else e
        sg[0], sg[1] = ns, max(ne, ns + 0.4)
    segs.sort(key=lambda x: x[0])
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


def write_ass(path, captions, font_family, font_size, outline_size, primary_color, width, height, style=None):
    play_res_y = 288
    play_res_x = max(100, int(round(play_res_y * width / max(1, height))))
    style = style or {}
    align = int(style.get("align", 2))
    bold = -1 if style.get("bold") else 0
    italic = -1 if style.get("italic") else 0
    box = style.get("box", "none")
    box_cols = {"soft": "&H99000000", "black": "&H00000000", "white": "&H00FFFFFF"}
    if box in box_cols:
        border_style, outline_col, back_col, shadow = 3, box_cols[box], "&H00000000", 0
    else:
        border_style, outline_col, back_col, shadow = 1, "&H00000000", "&H64000000", 1
    header = [
        "[Script Info]", "ScriptType: v4.00+",
        f"PlayResX: {play_res_x}", f"PlayResY: {play_res_y}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_family},{font_size},{primary_color},"
        f"&H000000FF,{outline_col},{back_col},{bold},{italic},0,0,100,100,0,0,{border_style},"
        f"{outline_size},{shadow},{align},20,20,35,1", "",
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


class Reporter:
    def __init__(self, item):
        self.item = item
    def write(self, message):
        self.item["stage"] = message
        self.item["log"].append(message)
        m = re.search(r"(\d+)/(\d+) ឃ្លា", str(message))
        if m and int(m.group(2)) > 0:
            frac = min(1.0, int(m.group(1)) / int(m.group(2)))
            self.item["pct"] = max(self.item.get("pct", 0.0), 0.25 + 0.28 * frac)
    def progress(self, value):
        self.item["pct"] = 0.03 + 0.09 * max(0.0, min(1.0, value))


def dbg(status, message):
    if DEBUG:
        status.write(message)


def call_with_retry(client, model, prompt, audio_bytes, mime, config, status):
    for attempt in range(3):
        try:
            kwargs = dict(
                model=model,
                contents=[prompt, types.Part.from_bytes(data=audio_bytes, mime_type=mime)],
            )
            if config is not None:
                kwargs["config"] = config
            return client.models.generate_content(**kwargs)
        except Exception as e:
            low = str(e).lower()
            busy = any(x in low for x in ("503", "unavailable", "high demand", "overloaded", "timeout", "timed out"))
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
    if source_language == "Khmer":
        task = (
            "The speech or singing is in Khmer (Cambodian). Transcribe it "
            "faithfully, word for word, in Khmer script with correct "
            "standard Khmer spelling. Do not translate, summarize or "
            "paraphrase. Do not confuse Khmer with Thai or Lao. "
            "If a word is unclear, choose the most likely Khmer word from the context."
        )
    elif source_language:
        task = (
            f"The speech or singing is in {source_language}. "
            "Listen very carefully. First write exactly what is said in "
            "the original language, then translate the meaning into "
            "natural, fluent, easy-to-understand Khmer, written in Khmer script. "
            "Translate the meaning, not word for word."
        )
    else:
        task = (
            "First detect the spoken or sung language. "
            "If it is Khmer (Cambodian), transcribe it faithfully, word "
            "for word, in Khmer script with correct standard Khmer "
            "spelling, and do not confuse it with Thai or Lao. "
            "If it is any other language, first write exactly what is "
            "said in the original language, then translate the meaning "
            "into natural, fluent, easy-to-understand Khmer written in Khmer script."
        )
    concise_rule = ""
    if concise:
        concise_rule = (
            "Each Khmer line must be short enough to be spoken naturally "
            "within its own time range: at most about 11 Khmer "
            "characters per second of that segment. Prefer concise wording. "
        )
    return (
        task
        + " The field \"text\" of every segment MUST be written only in "
        "Khmer script (names of people, places, brands may stay as they "
        "are or be transliterated into Khmer). Never put romanization or "
        "explanations in \"text\". "
        "Put a normal space between Khmer phrases so lines can wrap. "
        "Split into short subtitle segments, each about 1.5 to 4 seconds "
        "long, and the Khmer \"text\" of each segment at most 26 characters. "
        + concise_rule
        + "Timestamps are in seconds, measured from the very beginning "
        f"of THIS audio clip (0 to {clip_duration:.1f}). "
        "Each segment must start exactly when its first word is heard "
        "and end exactly when its last word ends. "
        "Return ONLY a JSON array. Each item must be an object: "
        '{"start": <seconds as number>, "end": <seconds as number>, '
        '"original": "<what was said in the original language>", '
        '"text": "<Khmer text>"}. '
        "If there is no speech or singing, return an empty array []."
    )


def plan_chunks(duration, speech):
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
    return bool(re.fullmatch(r"\s*(```(?:json)?)?\s*\[\s*\]\s*(```)?\s*", raw or ""))


def transcribe_clip(client, models, audio_bytes, mime, clip_duration, source_language, concise, status):
    prompt = build_prompt(clip_duration, source_language, concise)
    configs = [
        types.GenerateContentConfig(temperature=0, response_mime_type="application/json"),
        types.GenerateContentConfig(
            temperature=0, response_mime_type="application/json",
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
                response = call_with_retry(client, model, prompt, audio_bytes, mime, config, status)
            except Exception as e:
                message = str(e)
                low = message.lower()
                errors.append(f"{model}: {message}")
                if "400" in message or "invalid_argument" in low:
                    continue
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
            if is_empty_json(raw):
                return [], model, []
            plain = fix_khmer(re.sub(r"[\[\]{}\"]", " ", raw))
            if plain and has_khmer(plain):
                return plain_to_segments(plain, clip_duration), model, errors
            errors.append(f"{model}: មិនមានអត្ថបទ")
            break
    if weak:
        return weak[0], weak[1], errors
    return [], None, errors


def transcribe(api_key, audio_path, duration, source_language, status, concise=False, speech=None):
    client = make_gemini_client(api_key, types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
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
        run_ffmpeg(["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", base, "-c:a", "flac", out_name], cwd=folder)
        with open(os.path.join(folder, out_name), "rb") as f:
            data = f.read()
        if len(data) > 15 * 1024 * 1024:
            raise UserError("សំឡេងធំពេក។")
        segs, model, errors = transcribe_clip(client, models, data, "audio/flac", end - start, source_language, concise, status)
        done_counter["n"] += 1
        if total > 1:
            status.write(f"៣/៤ កំពុងស្តាប់ និងបកប្រែ... ({done_counter['n']}/{total})")
        return start, segs, model, errors
    all_segments = []
    used_models = []
    failed = 0
    fatal_errors = []
    fatal_keys = ("429", "503", "404", "500", "resource_exhausted")
    workers = max(1, min(MAX_CHUNK_WORKERS, total))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, i, s, e) for i, (s, e) in enumerate(chunks)]
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
                    all_segments.append((min(s + start, duration), min(e + start, duration + 0.5), t))
            elif any(k in err.lower() for err in errors for k in fatal_keys):
                failed += 1
                fatal_errors.extend(errors)
    if not all_segments:
        if fatal_errors:
            raise RuntimeError("ម៉ូដែលទាំងអស់បរាជ័យ។\n\n" + "\n\n".join(fatal_errors))
        raise UserError("រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូនេះទេ។")
    all_segments.sort(key=lambda x: x[0])
    main_model = Counter(used_models).most_common(1)[0][0]
    return all_segments, main_model, failed


def groq_request(api_key, audio_path, model, language):
    boundary = "----kac" + uuid.uuid4().hex
    fields = [
        ("model", model), ("response_format", "verbose_json"),
        ("temperature", "0"), ("timestamp_granularities[]", "segment"),
    ]
    if language:
        fields.append(("language", language))
    parts = []
    for name, value in fields:
        parts.append((f"--{boundary}\r\n" f'Content-Disposition: form-data; name="{name}"\r\n\r\n' f"{value}\r\n").encode("utf-8"))
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    parts.append((f"--{boundary}\r\n" 'Content-Disposition: form-data; name="file"; ' 'filename="audio.mp3"\r\n' "Content-Type: audio/mpeg\r\n\r\n").encode("utf-8"))
    parts.append(audio_data)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    request = urllib.request.Request(
        GROQ_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {groq_first(api_key)}", "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with groq_urlopen(request, api_key, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:500]
        raise RuntimeError(f"Groq HTTP {e.code}: {detail}")


def groq_transcribe(api_key, audio_path, language, status):
    last = None
    for model in model_order(GROQ_MODELS, "whisper"):
        for attempt in range(2):
            try:
                res_ = groq_request(api_key, audio_path, model, language)
                model_good("whisper", model)
                return res_, model
            except RuntimeError as e:
                last = e
                text = str(e)
                if ("429" in text or "503" in text) and attempt == 0:
                    status.write("ប្រព័ន្ធរវល់បន្តិច កំពុងសាកម្តងទៀត...")
                    time.sleep(12)
                    continue
                model_cool(model, text)
                break
            except Exception as e:
                last = e
                break
    raise last or RuntimeError("Groq បរាជ័យ: មិនដឹងមូលហេតុ")


def _google_once(text):
    query = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "km", "dt": "t"})
    url = "https://translate.googleapis.com/translate_a/single?" + query
    body = urllib.parse.urlencode({"q": text}).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"), "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    return "".join(part[0] for part in (data[0] or []) if part and part[0])


def google_translate_request(text, retries=3):
    for attempt in range(retries):
        try:
            return _google_once(text)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def clean_translation(out):
    out = str(out or "")
    out = CJK_RE.sub("", out)
    out = fix_khmer(out)
    return out or None


def http_detail(e):
    try:
        body = e.read().decode("utf-8", "ignore")[:200]
    except Exception:
        body = ""
    return f"HTTP {e.code}: {body}".strip()


def groq_chat_models(api_key):
    if _groq_chat_cache["models"]:
        return _groq_chat_cache["models"]
    found = []
    try:
        request = urllib.request.Request(GROQ_MODELS_URL, headers={"Authorization": f"Bearer {groq_first(api_key)}", "User-Agent": "Mozilla/5.0"})
        with groq_urlopen(request, api_key, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        for m in data.get("data") or []:
            mid = str(m.get("id", ""))
            low = mid.lower()
            if not mid or m.get("active") is False:
                continue
            if any(x in low for x in ("whisper", "tts", "guard", "prompt", "orpheus", "allam", "safeguard")):
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


TRANS_SYSTEM = (
    "You are an expert Cambodian Khmer dubbing translator and script editor. Translate the dialogue into natural, "
    "everyday SPOKEN Khmer exactly as a native Phnom Penh speaker would say it in a film or drama, not written/news Khmer "
    "and not word-for-word. The numbered lines are consecutive lines from ONE video: read ALL of them first to understand "
    "the story, who is speaking to whom, relationships, mood and running jokes, then translate each line with that context. "
    "Rules: (1) Keep the exact meaning, names, numbers and facts; never add or drop information. "
    "(2) Choose pronouns and politeness that fit the relationship (friends: ឯង/អ្នក/ខ្ញុំ; elders: ទូលបង្គំ/លោក/អ្នកស្រី etc.) and keep them consistent across lines. "
    "(3) Keep the speaker's emotion: anger, sadness, fear, joy, sarcasm, tenderness must be audible in word choice "
    "(use natural particles such as ណា, ហើយ, ទេ, ហ្នឹង, នែ៎ where a native would) and keep ! ? … punctuation. "
    "(4) Translate idioms, slang and jokes by their intended meaning, never literally. "
    "(5) Short, clear sentences a voice actor can say in one breath; no stiff foreign word order; no repeated words; "
    "no word salad. Write numbers and units the way Khmer speakers say them. Transliterate foreign names naturally. "
    "(6) If a line is garbled or uncertain, keep the closest clear meaning, do not invent dialogue. "
    "(7) When a [max N chars] limit is given, keep the full meaning and shorten only by removing filler; never output the tag. "
    "Output Khmer script only (no English, no Chinese, no romanization). "
    "Return JSON {\"translations\": [...]} with exactly one item per input, same order."
)


def groq_translate_chunk(api_key, texts, budgets=None, system=None, to_english=False):
    numbered = "\n".join(
        f"{i + 1}. " + (f"[max {budgets[i]} chars] " if budgets and budgets[i] else "") + str(t)
        for i, t in enumerate(texts)
    )
    models = groq_chat_models(api_key)
    models = model_order(models, "groq")
    last = "មិនមានម៉ូដែល"
    for model in models[:8]:
        body = json.dumps({
            "model": model, "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system or TRANS_SYSTEM},
                {"role": "user", "content": numbered},
            ],
        }).encode("utf-8")
        for attempt in range(2):
            request = urllib.request.Request(GROQ_CHAT_URL, data=body, method="POST", headers={"Authorization": f"Bearer {groq_first(api_key)}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
            try:
                with groq_urlopen(request, api_key, timeout=60) as r:
                    data = json.loads(r.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
                items = json.loads(content).get("translations") or []
                if len(items) == len(texts):
                    _groq_chat_cache["good"] = model
                    model_good("groq", model)
                    return [((str(x).strip() or None) if to_english else clean_translation(x)) for x in items]
                last = f"{model}: ចំនួនបន្ទាត់មិនត្រូវគ្នា"
                model_cool(model, last)
                break
            except urllib.error.HTTPError as e:
                last = f"{model}: {http_detail(e)}"
                if e.code == 429 and attempt == 0:
                    time.sleep(6)
                    continue
                model_cool(model, last)
                break
            except Exception as e:
                last = f"{model}: {e}"
                model_cool(model, last)
                break
    _groq_chat_cache["models"] = None  # បញ្ជីម៉ូដែលអាចហួសសម័យ ទាញថ្មីលើកក្រោយ
    raise RuntimeError(last[:300])


EN_SYSTEM = (
    "You are a careful transcription-correction and meaning bridge for dubbing. The numbered lines are consecutive lines from ONE video; "
    "use surrounding context to resolve only obvious Whisper errors, speaker references, slang, and idioms. Render each line as clear, "
    "faithful English that preserves every meaningful detail, emotion and tone (anger, sarcasm, sadness, affection). Do not translate beyond what the audio supports, add explanations, "
    "embellish, or guess at unclear words; mark genuinely unclear audio as [unclear]. "
    "mark genuinely unclear audio as [unclear] rather than making up dialogue. Keep exactly one output for each input line, same order. "
    "Return JSON {\"translations\": [...]} only."
)


def gemini_translate_khmer(api_key, texts, english=None, budgets=None, story=None):
    client = make_gemini_client(api_key, types.HttpOptions(timeout=TRANSLATE_TIMEOUT_MS))
    models = model_order(get_available_models(client)[:5], "gemini")
    rows = []
    for i, t in enumerate(texts):
        row = f"{i + 1}. {t}"
        if english and english[i]:
            row += f"\n   (English meaning: {english[i]})"
        if budgets and budgets[i]:
            row += f"\n   [max {budgets[i]} chars]"
        rows.append(row)
    prompt = (
        TRANS_SYSTEM
        + " Some items include an English meaning to help you understand; translate the true meaning into Khmer. "
        "Never output the English text or the tags.\n\n"
        + (("STORY SO FAR (for context only, do NOT translate this):\n" + story + "\n\n") if story else "")
        + "LINES TO TRANSLATE:\n" + "\n".join(rows)
    )
    last = None
    for model in models:
        try:
            resp = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(temperature=0.25, response_mime_type="application/json"),
            )
            raw = (getattr(resp, "text", "") or "").strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
            data = json.loads(raw)
            items = data.get("translations") if isinstance(data, dict) else data
            if isinstance(items, list) and len(items) == len(texts):
                model_good("gemini", model)
                return [clean_translation(x) for x in items]
            last = f"{model}: ចំនួនបន្ទាត់មិនត្រូវគ្នា"
            model_cool(model, last)
        except Exception as e:
            last = f"{model}: {e}"
            model_cool(model, last)
    raise RuntimeError(str(last)[:300])


def translate_texts(texts, groq_key=None, budgets=None, gemini_key=None, progress=None):
    n = len(texts)
    errors = []
    outs = [None] * n
    english = [None] * n
    # បកជាបាច់តូច ដើម្បីកុំឱ្យ AI ខកឃ្លា ឬច្រឡំលំដាប់
    batches = [list(range(k, min(k + 8, n))) for k in range(0, n, 8)]
    def _say(msg):
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    # ជំហាន ១: បកទៅអង់គ្លេសជាមុន (ធ្វើស្របគ្នា ៣ បាច់ក្នុងពេលតែមួយ)
    if groq_key:
        def _en(idxs):
            try:
                return idxs, groq_translate_chunk(groq_key, [str(texts[i]).strip() for i in idxs], None, system=EN_SYSTEM, to_english=True), None
            except Exception as e:
                return idxs, None, e
        done = 0
        with ThreadPoolExecutor(max_workers=3) as pool:
            for idxs, res, err in pool.map(_en, batches):
                if err:
                    errors.append(f"groq-en: {err}"[:200])
                else:
                    for i, r in zip(idxs, res):
                        english[i] = r
                done += len(idxs)
                _say(f"កំពុងស្ដាប់អត្ថន័យ {done}/{n} ឃ្លា...")
    # ជំហាន ២: ពីអង់គ្លេស/ដើម → ខ្មែរ ដោយ Gemini (ស្របគ្នា ៣ បាច់)
    if gemini_key:
        def _km(idxs):
            try:
                prev_ctx = [english[j] or str(texts[j]) for j in range(max(0, idxs[0] - 6), idxs[0])]
                story = " / ".join(str(x).strip() for x in prev_ctx if x) or None
                return idxs, gemini_translate_khmer(
                    gemini_key, [str(texts[i]).strip() for i in idxs],
                    [english[i] for i in idxs], [budgets[i] for i in idxs] if budgets else None,
                    story=story,
                ), None
            except Exception as e:
                return idxs, None, e
        done = 0
        with ThreadPoolExecutor(max_workers=3) as pool:
            for idxs, res, err in pool.map(_km, batches):
                if err:
                    errors.append(f"gemini: {err}"[:200])
                else:
                    for i, r in zip(idxs, res):
                        outs[i] = r
                done += len(idxs)
                _say(f"កំពុងបកជាខ្មែរ {done}/{n} ឃ្លា...")
    # បម្រុងទី១: Groq LLM បកជាខ្មែរ ដោយមានបរិបទសាច់រឿង (ល្អជាង Google Translate បកម្តងមួយឃ្លាៗ)
    missing = [i for i, o in enumerate(outs) if o is None]
    if missing and groq_key:
        _say(f"កំពុងបកជាខ្មែរតាមសាច់រឿង (Groq) 0/{len(missing)} ឃ្លា...")
        groups = [missing[k:k + 10] for k in range(0, len(missing), 10)]
        def _gkm(idxs):
            try:
                prev = [english[j] or str(texts[j]) for j in range(max(0, idxs[0] - 6), idxs[0])]
                story = " / ".join(str(x).strip() for x in prev if x)
                lines_ = []
                for i in idxs:
                    row = str(texts[i]).strip()
                    if english[i]:
                        row += f" (English meaning: {english[i]})"
                    lines_.append(row)
                sys_ = (
                    TRANS_SYSTEM
                    + " Some lines include an English meaning in parentheses to help you understand; translate the true meaning "
                    "into Khmer and never output the English text or any tags."
                    + ((" STORY SO FAR (context only, do NOT translate): " + story) if story else "")
                )
                bud_ = [budgets[i] for i in idxs] if budgets else None
                return idxs, groq_translate_chunk(groq_key, lines_, bud_, system=sys_), None
            except Exception as e:
                return idxs, None, e
        done_ = 0
        with ThreadPoolExecutor(max_workers=2) as pool:
            for idxs, res, err in pool.map(_gkm, groups):
                if err:
                    errors.append(f"groq-km-ctx: {err}"[:200])
                else:
                    for i, r in zip(idxs, res):
                        if r and has_khmer(str(r)):
                            outs[i] = r
                done_ += len(idxs)
                _say(f"កំពុងបកជាខ្មែរតាមសាច់រឿង (Groq) {done_}/{len(missing)} ឃ្លា...")
    # បម្រុង: Google Translate លើអត្ថបទអង់គ្លេស (ត្រឹមត្រូវជាងបកពីចិន/ថៃ/វៀតណាមផ្ទាល់)
    missing = [i for i, o in enumerate(outs) if o is None]
    if missing:
        src = [english[i] or str(texts[i]) for i in missing]
        g_outs, g_errs = _translate_texts_old(src, None)
        errors += g_errs
        for i, o in zip(missing, g_outs):
            outs[i] = o
    # ជំហាន ៣: សាកបកប្រែឡើងវិញសម្រាប់ឃ្លាដែលលទ្ធផលទទេ/មិនមានអក្សរខ្មែរ
    missing = [i for i, o in enumerate(outs) if not o or not has_khmer(str(o))]
    if missing and gemini_key:
        for k in range(0, len(missing), 8):
            idxs = missing[k:k + 8]
            try:
                res = gemini_translate_khmer(
                    gemini_key, [str(texts[i]).strip() for i in idxs],
                    [english[i] for i in idxs],
                    [budgets[i] for i in idxs] if budgets else None,
                )
                for i, r in zip(idxs, res):
                    if r and has_khmer(str(r)):
                        outs[i] = r
            except Exception as e:
                errors.append(f"gemini-retry: {e}"[:200])
    # ជំហាន ៤: បម្រុងចុងក្រោយ បកផ្ទាល់ទៅខ្មែរ ដោយ Groq
    missing = [i for i, o in enumerate(outs) if not o or not has_khmer(str(o))]
    if missing and groq_key:
        for k in range(0, len(missing), 8):
            idxs = missing[k:k + 8]
            try:
                res = groq_translate_chunk(
                    groq_key, [str(texts[i]).strip() for i in idxs],
                    [budgets[i] for i in idxs] if budgets else None,
                )
                for i, r in zip(idxs, res):
                    if r and has_khmer(str(r)):
                        outs[i] = r
            except Exception as e:
                errors.append(f"groq-km-retry: {e}"[:200])
            time.sleep(0.5)
    # ជំហានចុងក្រោយ: បកម្តងមួយឃ្លាៗ (មិនអាចខុសចំនួនបន្ទាត់) ជាមួយ Gemini/Groq រួចទើប Google
    missing = [i for i, o in enumerate(outs) if not o or not has_khmer(str(o))]
    if missing:
        _say(f"កំពុងបកឃ្លាដែលនៅខ្វះ {len(missing)} ឃ្លា...")
    for i in missing:
        one = [str(texts[i]).strip()]
        bud = [budgets[i]] if budgets else None
        r = None
        if gemini_key:
            try:
                r = gemini_translate_khmer(gemini_key, one, [english[i]], bud)[0]
            except Exception as e:
                errors.append(f"gemini-1: {e}"[:200])
        if (not r or not has_khmer(str(r))) and groq_key:
            try:
                r = groq_translate_chunk(groq_key, one, bud)[0]
            except Exception as e:
                errors.append(f"groq-1: {e}"[:200])
            time.sleep(0.6)
        if not r or not has_khmer(str(r)):
            try:
                r = clean_translation(google_translate_request(english[i] or one[0]))
            except Exception as e:
                errors.append(f"google-1: {e}"[:200])
                time.sleep(5)
        if r and has_khmer(str(r)):
            outs[i] = r
    # កុំទុកលទ្ធផលទទេ ឬអង់គ្លេសសុទ្ធឱ្យបន្តជាសំឡេង dubbing
    for i, o in enumerate(outs):
        if not o or not has_khmer(str(o)):
            outs[i] = None
    return outs, errors


def _translate_texts_prev(texts, groq_key=None, budgets=None):
    errors = []
    outs = [None] * len(texts)
    if groq_key:
        for k in range(0, len(texts), 12):
            idxs = list(range(k, min(k + 12, len(texts))))
            try:
                res = groq_translate_chunk(
                    groq_key, [str(texts[i]).strip() for i in idxs],
                    [budgets[i] for i in idxs] if budgets else None,
                )
                for i, r in zip(idxs, res):
                    outs[i] = r
            except Exception as e:
                errors.append(f"groq-llm: {e}"[:200])
            time.sleep(0.4)
    missing = [i for i, o in enumerate(outs) if o is None]
    if missing:
        g_outs, g_errs = _translate_texts_old([texts[i] for i in missing], None)
        errors += g_errs
        for i, o in zip(missing, g_outs):
            outs[i] = o
    return outs, errors


def _translate_texts_old(texts, groq_key=None):
    errors = []
    outs = [None] * len(texts)
    google_blocked = False
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
    fails = 0
    for batch in batches:
        if fails >= 2:
            break
        try:
            raw = google_translate_request("\n".join(t for _, t in batch))
            lines = (raw or "").strip("\n").split("\n")
            if len(lines) == len(batch):
                for (i, _), line in zip(batch, lines):
                    outs[i] = clean_translation(line)
            else:
                # line count differs: translate each line on its own
                for i, flat in batch:
                    try:
                        outs[i] = clean_translation(google_translate_request(flat))
                    except Exception:
                        pass
                    time.sleep(0.4)
            fails = 0
        except Exception as e:
            errors.append(f"google: {e}"[:200])
            fails += 1
            time.sleep(3)
        time.sleep(0.5)
    missing = [i for i, o in enumerate(outs) if o is None]
    if missing and groq_key:
        for k in range(0, len(missing), 20):
            idxs = missing[k:k + 20]
            try:
                res = groq_translate_chunk(groq_key, [str(texts[i]).strip() for i in idxs])
                for i, r in zip(idxs, res):
                    outs[i] = r
            except Exception as e:
                errors.append(f"groq-llm: {e}"[:200])
            time.sleep(1)
    return outs, errors


def retime_by_speech(segs, speech, duration, pad=0.6):
    if not speech or duration <= 0:
        return segs
    total_all = sum(b - a for a, b in speech)
    if total_all / duration >= 0.9 or total_all < 1.0:
        return segs
    out = []
    for s, e, text in segs:
        pieces = split_display(text)
        if not pieces:
            continue
        lo, hi = max(0.0, s - pad), min(duration, e + pad)
        win = []
        for a, b in speech:
            a2, b2 = max(a, lo), min(b, hi)
            if b2 - a2 >= 0.1:
                win.append((a2, b2))
        win_total = sum(b - a for a, b in win)
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


def transcribe_khmer_chunks(groq_key, audio_path, duration, speech, status):
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
            run_ffmpeg(["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", base, "-c:a", "libmp3lame", "-b:a", "64k", name], cwd=folder)
            data, _ = groq_transcribe(groq_key, os.path.join(folder, name), "km", status)
            texts = []
            for sg in data.get("segments") or []:
                text = fix_khmer(sg.get("text", ""))
                if not text or not has_khmer(text):
                    continue
                if (float(sg.get("no_speech_prob", 0) or 0) > 0.6 and float(sg.get("avg_logprob", 0) or 0) < -0.8):
                    continue
                texts.append(text)
            text = fix_khmer(" ".join(texts))
            if text:
                out.extend(retime_by_speech([(a, b, text)], speech, duration, pad=0.0))
        except Exception:
            pass
        status.write(f"៣/៤ កំពុងស្តាប់ភាសាខ្មែរ... ({i + 1}/{len(chunks)})")
        wait = 3.2 - (time.time() - t0)
        if wait > 0:
            time.sleep(wait)
    out.sort(key=lambda x: x[0])
    return out


GSPEECH_KEY = get_secret("GSPEECH_KEY", "")


def google_speech_request(flac_bytes, lang="km-KH"):
    query = urllib.parse.urlencode({"client": "chromium", "lang": lang, "key": GSPEECH_KEY, "pFilter": "0"})
    request = urllib.request.Request(
        "https://www.google.com/speech-api/v2/recognize?" + query,
        data=flac_bytes, method="POST",
        headers={"Content-Type": "audio/x-flac; rate=16000", "User-Agent": "Mozilla/5.0"},
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
    folder = os.path.dirname(audio_path)
    base = os.path.basename(audio_path)
    chunks = plan_short_chunks(duration, speech)
    todo = [(i, a, b) for i, (a, b) in enumerate(chunks) if b - a >= 0.5]
    counter = {"n": 0}

    def one(item):
        i, a, b = item
        name = f"gs_{i}.flac"
        try:
            run_ffmpeg(["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", base, "-ac", "1", "-ar", "16000", "-c:a", "flac", name], cwd=folder)
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
            res = retime_by_speech([(a, b, text)], speech, duration, pad=0.0) if text else []
            return res, None
        except Exception as ex_:
            return [], ex_
        finally:
            counter["n"] += 1
            status.write(f"៣/៤ កំពុងស្តាប់ភាសាខ្មែរ... ({counter['n']}/{len(todo)})")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, todo))
    out = []
    got = 0
    errs = 0
    for res, err in results:
        if err is not None:
            errs += 1
        if res:
            got += 1
            out.extend(res)
    if got == 0:
        if errs >= 3:
            raise RuntimeError("Google Speech បរាជ័យ")
        return []
    out.sort(key=lambda x: x[0])
    return out


def merge_for_translate(segs, max_chars=160, max_gap=0.6, max_len=10.0):
    out = []
    for s, e, t in segs:
        if out:
            ps, pe, pt = out[-1]
            ended = pt.rstrip()[-1:] in ".!?។…"
            if (not ended) and s - pe <= max_gap and len(pt) + len(t) + 1 <= max_chars and e - ps <= max_len:
                out[-1] = (ps, max(pe, e), (pt + " " + t).strip())
                continue
        out.append((s, e, t))
    return out


def transcribe_free(groq_key, audio_path, duration, source_language, status, speech=None, khmer_ok=True, dub=False, gemini_key=None, keep_failed=False):
    code = WHISPER_LANG.get(source_language) if source_language else None
    if source_language == "Khmer" and khmer_ok:
        try:
            gs = transcribe_khmer_google(audio_path, duration, speech or [], status)
        except Exception:
            gs = []
        if gs:
            return gs, "Google Speech (km-KH)", 0
    data, model = groq_transcribe(groq_key, audio_path, code, status)
    detected = str(data.get("language", "") or "").lower()
    keep = []
    for sg in data.get("segments") or []:
        text = str(sg.get("text", "")).strip()
        if not text:
            continue
        if (float(sg.get("no_speech_prob", 0) or 0) > 0.6 and float(sg.get("avg_logprob", 0) or 0) < -0.8):
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
        raise UserError("រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូនេះទេ។")
    failed = 0
    is_khmer = detected in ("khmer", "km") or source_language == "Khmer"
    if is_khmer:
        segs = []
        if source_language != "Khmer":
            try:
                segs = transcribe_khmer_google(audio_path, duration, speech or [], status)
            except Exception:
                segs = []
            if segs:
                return segs, "Google Speech (km-KH)", 0
        if not segs and duration > 12:
            try:
                segs = transcribe_khmer_chunks(groq_key, audio_path, duration, speech or [], status)
            except Exception:
                segs = []
        if not segs:
            segs = [(s, e, fix_khmer(t)) for s, e, t in keep if has_khmer(t)]
            segs = retime_by_speech(segs, speech, duration)
    else:
        status.write("៣/៤ កំពុងបកប្រែជាភាសាខ្មែរ...")
        keep = merge_for_translate(keep, max_chars=220, max_gap=0.9, max_len=14.0)
        # បកប្រែតាមប្រវែងឃ្លាចិន៖ ឃ្លាខ្លីអាចពន្យល់ខ្មែរបន្ថែម,
        # ឃ្លាវែងត្រូវសង្ខេបខ្មែរឱ្យខ្លី ដើម្បីសមនឹងចន្លោះសំឡេង។
        budgets = [
            max(18, min(150, int(45 + 22 / max(0.7, e - s))))
            for s, e, _ in keep
        ] if dub else None
        outs, errs = translate_texts([t for _, _, t in keep], groq_key, budgets, gemini_key, progress=lambda m: status.write("៣/៤ " + m))
        segs = []
        for (s, e, orig), out in zip(keep, outs):
            if out:
                segs.append((s, e, out))
            elif keep_failed:
                # មានទំព័រកែអត្ថបទ: ទុកឃ្លាដើមដាក់ស្លាក ⚠️ ឱ្យអ្នកកែដោយដៃ
                segs.append((s, e, "⚠️ " + str(orig)))
                failed += 1
            else:
                failed += 1
        # កុំបង្កើតវីដេអូដែលមានឃ្លាបាត់សំឡេងបកប្រែស្ងាត់ៗ
        if not keep_failed and (failed > 0 or len(segs) != len(keep)):
            reason = " | ".join(errs[:3]) or "AI មិនបានផ្តល់អត្ថបទខ្មែរសម្រាប់ឃ្លាខ្លះ"
            raise RuntimeError(
                "ការបកប្រែមិនគ្រប់ឃ្លា ដូច្នេះបានបញ្ឈប់ដើម្បីកុំឱ្យវីដេអូបាត់អត្ថបទ។ "
                f"(ស្តាប់បាន {len(keep)} ឃ្លា បកបាន {len(segs)} ឃ្លា) មូលហេតុ: {reason}"
            )
    if not segs:
        raise UserError("រកមិនឃើញអត្ថបទខ្មែរក្នុងសំឡេងនេះទេ។")
    segs.sort(key=lambda x: x[0])
    return segs, f"Groq {model} + Translate", failed


def tts_segment(text, voice, path, prosody=None):
    async def _go(p):
        # Natural, slightly slower Khmer delivery by default.
        # Emotion-specific prosody still takes precedence when supplied.
        kw = {"rate": "-4%"}
        if p:
            kw = {"rate": p["rate"], "volume": p["volume"], "pitch": p["pitch"]}
        await edge_tts.Communicate(text, voice, **kw).save(path)

    try:
        asyncio.run(_go(prosody))
    except Exception:
        if prosody:
            asyncio.run(_go(None))
        else:
            raise


def shorten_khmer(client, model, text, max_seconds):
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


VOICE_MALE = "km-KH-PisethNeural"
VOICE_FEMALE = "km-KH-SreymomNeural"

BIN = 0.1
MIN_TURN = 0.8


def load_pcm(path):
    import numpy as np
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [exe, "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    data = np.frombuffer(result.stdout, dtype=np.int16)
    return data.astype(np.float32) / 32768.0


def pitch_track(samples, sr=16000):
    import numpy as np
    n = int(0.04 * sr)
    hop = int(0.02 * sr)
    lag_min = int(sr / 400)
    lag_max = int(sr / 70)
    empty = np.array([])
    if len(samples) < n * 3:
        return empty, empty, empty
    count = 1 + (len(samples) - n) // hop
    times = (np.arange(count) * hop + n / 2) / sr
    f0 = np.zeros(count, dtype=np.float64)
    rms = np.zeros(count, dtype=np.float64)
    peaks = np.zeros(count, dtype=np.float64)
    lags = np.arange(n)
    overlap_fix = n / np.maximum(n - lags, 1)
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
    runs = [list(r) for r in runs]
    while len(runs) > 1:
        idx = min(range(len(runs)), key=lambda k: runs[k][1] - runs[k][0])
        if runs[idx][1] - runs[idx][0] >= min_len:
            break
        left = runs[idx - 1] if idx > 0 else None
        right = runs[idx + 1] if idx < len(runs) - 1 else None
        if left is not None and right is not None:
            target = left if (left[1] - left[0]) >= (right[1] - right[0]) else right
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


def gender_timeline(pcm, duration, default_voice, sr=16000, tracks=None):
    import numpy as np
    if tracks is not None:
        times, f0, rms = tracks
    else:
        times, f0, rms = pitch_track(pcm, sr)
    info = {"times": times, "f0": f0, "rms": rms, "summary": ""}
    mask = f0 > 0
    if int(mask.sum()) < 25:
        info["summary"] = "វាស់កម្រិតសំឡេងមិនបាន ប្រើសំឡេងដែលបានជ្រើស"
        return None, info
    tv = times[mask]
    hz = f0[mask]
    lg = np.log2(hz)
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
                single = g0
    if not two and single is None:
        med = float(np.median(hz))
        if med < 150:
            single = "M"
        elif med > 190:
            single = "F"
        else:
            single = "M" if default_voice == VOICE_MALE else "F"
            info["summary"] = f"កម្រិតសំឡេង ~{int(med)}Hz មិនច្បាស់ ប្រើសំឡេងដែលបានជ្រើស"
    names = {"M": "ប្រុស", "F": "ស្រី"}
    if not two:
        med = float(np.median(hz))
        if not info["summary"]:
            info["summary"] = f"ស្គាល់ឃើញអ្នកនិយាយ ១ នាក់៖ {names[single]} (~{int(med)}Hz)"
        return [(0.0, duration + 1.0, single)], info
    nb = int(duration / BIN) + 2
    isf = np.where(hi, 1 if g1 == "F" else 0, 1 if g0 == "F" else 0)
    bins = np.minimum((tv / BIN).astype(int), nb - 1)
    vf = np.zeros(nb)
    vm = np.zeros(nb)
    np.add.at(vf, bins, isf)
    np.add.at(vm, bins, 1 - isf)
    lab = np.full(nb, -1, dtype=int)
    lab[vf > vm] = 1
    lab[vm > vf] = 0
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
    n = len(text)
    pos = max(0, min(n, pos))
    for d in range(0, 9):
        for p in (pos - d, pos + d):
            if 0 < p < n and text[p] == " ":
                return p
    p = pos
    while 0 < p < n and ("\u17B6" <= text[p] <= "\u17D3" or text[p - 1] == "\u17D2"):
        p -= 1
    return p


def split_text_by_shares(text, shares):
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


def plan_dub_voices(segments, pcm, default_voice, duration, tracks=None):
    runs, info = gender_timeline(pcm, duration, default_voice, tracks=tracks)
    if runs is None:
        return [(s, e, t, default_voice) for s, e, t in segments], [], info, None
    dub = split_by_speaker(segments, runs, default_voice)
    lines = []
    for a, b, t, v in dub:
        hz = median_pitch(info, a, b)
        mark = "♂" if v == VOICE_MALE else "♀"
        lines.append(f"{mark} {int(hz) if hz else '?'}Hz  {t}")
    return dub, lines, info, runs


MATCH_MIN = 0.8
MATCH_MAX = 1.25


def gender_medians(info, runs):
    import numpy as np
    t = info.get("times")
    f = info.get("f0")
    out = {}
    if t is None or len(t) == 0 or not runs:
        return out
    for g in ("M", "F"):
        m = np.zeros(len(t), dtype=bool)
        for a, b, gg in runs:
            if gg == g:
                m |= (t >= a) & (t < b)
        m &= f > 0
        if int(m.sum()) >= 10:
            out[g] = float(np.median(f[m]))
    return out


def compute_targets(dub_segments, seg_voices, info, runs):
    import numpy as np
    meds = gender_medians(info, runs) if runs else {}
    allmed = None
    f = info.get("f0")
    if f is not None and len(f):
        voiced = f[f > 0]
        if len(voiced) >= 25:
            allmed = float(np.median(voiced))
    voices = seg_voices or [None] * len(dub_segments)
    targets = []
    for seg, v in zip(dub_segments, voices):
        s, e = seg[0], seg[1]
        g = "M" if v == VOICE_MALE else ("F" if v == VOICE_FEMALE else None)
        base = meds.get(g) or allmed
        own = median_pitch(info, s, e)
        if base and own:
            t = 0.5 * base + 0.5 * own
        else:
            t = base or own
        targets.append(t)
    return targets


def tts_median_pitch(path):
    try:
        import numpy as np
        pcm = load_pcm(path)
        _, f, _ = pitch_track(pcm)
        if len(f) == 0:
            return None
        voiced = f[f > 0]
        if len(voiced) < 8:
            return None
        return float(np.median(voiced))
    except Exception:
        return None


def atempo_chain(x):
    parts = []
    while x > 2.0:
        parts.append("atempo=2.0")
        x /= 2.0
    while x < 0.5:
        parts.append("atempo=0.5")
        x *= 2.0
    parts.append(f"atempo={x:.4f}")
    return ",".join(parts)


EMO_LABELS = ["neutral", "happy", "excited", "angry", "sad", "fear", "whisper"]
EMO_HIGH = ("happy", "excited", "angry", "fear")
EMO_LOW = ("sad", "whisper")

EMO_PRESETS = {
    "neutral": (0, 0, 0), "happy": (6, 10, 4), "excited": (10, 14, 10),
    "angry": (8, 4, 20), "sad": (-10, -8, -12), "fear": (8, 14, -4),
    "whisper": (-6, -3, -35),
}

EMO_NAMES = {
    "neutral": "😐 ធម្មតា", "happy": "😊 សប្បាយ", "excited": "🤩 រំភើប",
    "angry": "😠 ខឹង", "sad": "😢 ក្រៀមក្រំ", "fear": "😨 ភ័យ",
    "whisper": "🤫 ខ្សឹប",
}

EMO_SYSTEM = (
    "You label the emotion of each Khmer subtitle line spoken by a "
    "character. Use ONLY these labels: neutral, happy, excited, angry, "
    "sad, fear, whisper. Judge from meaning and punctuation. "
    "Return JSON: {\"emotions\": [...]} with exactly the same number of "
    "items, in the same order."
)


def norm_emotion(x):
    x = str(x or "").strip().lower()
    return x if x in EMO_LABELS else "neutral"


def groq_emotion_chunk(api_key, texts):
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    models = groq_chat_models(api_key)
    good = _groq_chat_cache["good"]
    if good in models:
        models = [good] + [m for m in models if m != good]
    last = "មិនមានម៉ូដែល"
    for model in models[:6]:
        body = json.dumps({
            "model": model, "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": EMO_SYSTEM},
                {"role": "user", "content": numbered},
            ],
        }).encode("utf-8")
        for attempt in range(2):
            request = urllib.request.Request(
                GROQ_CHAT_URL, data=body, method="POST",
                headers={"Authorization": f"Bearer {groq_first(api_key)}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            try:
                with groq_urlopen(request, api_key, timeout=60) as r:
                    data = json.loads(r.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
                items = json.loads(content).get("emotions") or []
                if len(items) == len(texts):
                    _groq_chat_cache["good"] = model
                    return [norm_emotion(x) for x in items]
                last = f"{model}: ចំនួនមិនត្រូវគ្នា"
                break
            except urllib.error.HTTPError as e:
                last = f"{model}: {http_detail(e)}"
                if e.code == 429 and attempt == 0:
                    time.sleep(6)
                    continue
                break
            except Exception as e:
                last = f"{model}: {e}"
                break
    raise RuntimeError(last[:300])


def gemini_emotion_labels(api_key, texts):
    client = make_gemini_client(api_key, types.HttpOptions(timeout=TRANSLATE_TIMEOUT_MS))
    models = get_available_models(client)[:3]
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    prompt = EMO_SYSTEM + "\n\n" + numbered
    last = None
    for model in models:
        try:
            resp = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"),
            )
            raw = (getattr(resp, "text", "") or "").strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
            data = json.loads(raw)
            items = data.get("emotions") if isinstance(data, dict) else data
            if isinstance(items, list) and len(items) == len(texts):
                return [norm_emotion(x) for x in items]
        except Exception as e:
            last = e
    raise RuntimeError(f"Gemini emotion: {last}")


def label_emotions(texts, groq_key, gemini_key):
    if not texts:
        return None
    if groq_key:
        out = []
        ok = True
        for k in range(0, len(texts), 25):
            try:
                out.extend(groq_emotion_chunk(groq_key, texts[k:k + 25]))
            except Exception:
                ok = False
                break
            time.sleep(0.5)
        if ok and len(out) == len(texts):
            return out
    if gemini_key:
        try:
            return gemini_emotion_labels(gemini_key, texts)
        except Exception:
            pass
    return None


def combine_emotion(text_label, arousal):
    if text_label in EMO_HIGH:
        return text_label, max(0.3, min(1.4, 0.6 + 0.5 * arousal))
    if text_label in EMO_LOW:
        return text_label, max(0.3, min(1.4, 0.6 - 0.5 * arousal))
    if arousal > 0.35:
        return "excited", min(1.2, 0.4 + (arousal - 0.35) * 0.9)
    if arousal < -0.35:
        return "sad", min(1.2, 0.4 + (-arousal - 0.35) * 0.9)
    return "neutral", 0.0


def plan_emotions(dub_segments, seg_voices, info, runs, groq_key, gemini_key):
    import numpy as np
    texts = [seg[2] for seg in dub_segments]
    labels = label_emotions(texts, groq_key, gemini_key)
    t = f = r = None
    if info:
        t, f, r = info.get("times"), info.get("f0"), info.get("rms")
    have_audio = (t is not None and f is not None and r is not None and len(t) > 0)
    all_f = base_rms = None
    meds = {}
    if have_audio:
        voiced = f > 0
        if int(voiced.sum()) >= 25:
            all_f = float(np.median(f[voiced]))
            base_rms = float(np.median(r[voiced]))
        if runs:
            meds = gender_medians(info, runs)
    def clip(x):
        return float(np.clip(x, -1.5, 1.5))
    voices = seg_voices or [None] * len(dub_segments)
    result = []
    for i, seg in enumerate(dub_segments):
        s, e = seg[0], seg[1]
        v = voices[i]
        g = "M" if v == VOICE_MALE else ("F" if v == VOICE_FEMALE else None)
        arousal = 0.0
        if have_audio and all_f and base_rms:
            m = (t >= s) & (t <= e) & (f > 0)
            if int(m.sum()) >= 5:
                own = float(np.median(f[m]))
                base_f = meds.get(g) or all_f
                loud_db = 20.0 * np.log10(max(float(np.mean(r[m])), 1e-6) / max(base_rms, 1e-6))
                pitch_st = 12.0 * np.log2(own / base_f)
                std_st = float(np.std(12.0 * np.log2(f[m] / own)))
                arousal = (0.5 * clip(loud_db / 6.0) + 0.3 * clip(pitch_st / 4.0) + 0.2 * clip((std_st - 2.5) / 2.0))
        text_label = labels[i] if labels else None
        result.append(combine_emotion(text_label, arousal))
    counts = Counter(lab for lab, _ in result)
    source = ("តាមអត្ថបទ + សំឡេងដើម" if labels and have_audio else "តាមអត្ថបទតែប៉ុណ្ណោះ" if labels else "តាមសំឡេងដើមតែប៉ុណ្ណោះ" if have_audio else "មិនមានទិន្នន័យ")
    summary = (f"🎭 អារម្មណ៍ ({source})៖ " + " · ".join(f"{EMO_NAMES[k]} {counts[k]}" for k in EMO_LABELS if counts.get(k)))
    lines = [summary]
    shown = 0
    for (lab, inten), text in zip(result, texts):
        if lab == "neutral":
            continue
        lines.append(f"{EMO_NAMES[lab]} ×{inten:.1f}  {text}")
        shown += 1
        if shown >= 40:
            break
    return result, lines


def emotion_prosody(label, intensity, use_pitch=True):
    rate, pitch, vol = EMO_PRESETS.get(label, (0, 0, 0))
    k = max(0.0, float(intensity))
    rate = int(max(-30, min(30, rate * k)))
    pitch = int(max(-30, min(30, pitch * k))) if use_pitch else 0
    vol = int(max(-50, min(50, vol * k)))
    if rate == 0 and pitch == 0 and vol == 0:
        return None
    return {"rate": f"{rate:+d}%", "pitch": f"{pitch:+d}Hz", "volume": f"{vol:+d}%"}




_eleven_sem = threading.Semaphore(2)


def _multipart(fields, files):
    boundary = "----kac" + uuid.uuid4().hex
    parts = []
    for n, v in fields:
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}\r\n").encode("utf-8"))
    for n, fn, data, ct in files:
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{n}\"; filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n").encode("utf-8"))
        parts.append(data)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _eleven_call(key, url, body=None, ctype=None, method="POST", timeout=120):
    headers = {"xi-api-key": key, "User-Agent": "Mozilla/5.0"}
    if ctype:
        headers["Content-Type"] = ctype
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:200]
        raise RuntimeError(f"ElevenLabs HTTP {e.code}: {detail}")


def eleven_add_voice(key, sample_bytes):
    body, ctype = _multipart(
        [("name", "kac_" + uuid.uuid4().hex[:8])],
        [("files", "sample.mp3", sample_bytes, "audio/mpeg")],
    )
    raw = _eleven_call(key, "https://api.elevenlabs.io/v1/voices/add", body, ctype, timeout=90)
    return json.loads(raw.decode("utf-8"))["voice_id"]


def eleven_sts(key, voice_id, path):
    with open(path, "rb") as f:
        audio = f.read()
    body, ctype = _multipart(
        [("model_id", "eleven_multilingual_sts_v2")],
        [("audio", "in.mp3", audio, "audio/mpeg")],
    )
    url = f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}?output_format=mp3_44100_128"
    last = None
    for attempt in range(3):
        try:
            with _eleven_sem:
                out = _eleven_call(key, url, body, ctype, timeout=120)
            if len(out) < 500:
                raise RuntimeError("ElevenLabs ឆ្លើយតបទទេ")
            with open(path, "wb") as f:
                f.write(out)
            return
        except RuntimeError as e:
            last = e
            if "429" in str(e) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise last


def eleven_delete_voice(key, voice_id):
    try:
        _eleven_call(key, f"https://api.elevenlabs.io/v1/voices/{voice_id}", method="DELETE", timeout=30)
    except Exception:
        pass



EQ_CENTERS = [150, 250, 400, 630, 1000, 1600, 2500, 4000, 6300]


def band_levels(pcm, sr=16000):
    """វាស់ 'ពណ៌សំឡេង' ជាកម្រិត dB ក្នុងចន្លោះប្រេកង់ ៩ (ឥតគិតថ្លៃ គ្មាន API)"""
    import numpy as np
    n = 1024
    if pcm is None or len(pcm) < n * 8:
        return None
    hop = max(512, (len(pcm) - n) // 6000)
    count = 1 + (len(pcm) - n) // hop
    idx = (np.arange(count) * hop)[:, None] + np.arange(n)[None, :]
    frames = pcm[idx].astype(np.float64)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    thr = max(1e-4, 0.15 * float(np.percentile(rms, 90)))
    frames = frames[rms >= thr]
    if len(frames) < 10:
        return None
    pw = (np.abs(np.fft.rfft(frames * np.hanning(n), axis=1)) ** 2).mean(axis=0)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    out = []
    for c in EQ_CENTERS:
        m = (freqs >= c / 1.41) & (freqs < c * 1.41)
        out.append(10.0 * np.log10(float(pw[m].mean()) + 1e-12))
    return out


def eq_filters(ref, tts, limit=6.0):
    if not ref or not tts:
        return ""
    import numpy as np
    r = np.array(ref, dtype=np.float64)
    t = np.array(tts, dtype=np.float64)
    d = np.clip((r - r.mean()) - (t - t.mean()), -limit, limit)
    parts = [f"equalizer=f={c}:t=q:w=1.0:g={g:.1f}" for c, g in zip(EQ_CENTERS, d) if abs(g) >= 0.8]
    return ",".join(parts)


MERGE_TIGHT = (50, 0.4, 5.0)


def merge_for_dub(segments, max_chars=90, max_gap=0.5, max_len=9.0):
    """បញ្ចូលឃ្លាខ្លីៗជាប់គ្នាជាប្រយោគវែង ដើម្បីឱ្យសំឡេងអានរលូន មិនកាត់ៗ"""
    out = []
    for s, e, t in segments:
        if out:
            ps, pe, pt = out[-1]
            if s - pe <= max_gap and len(pt) + len(t) + 1 <= max_chars and e - ps <= max_len:
                out[-1] = (ps, max(pe, e), fix_khmer(pt + " " + t))
                continue
        out.append((s, e, t))
    return out


def tts_retry(text, voice, path, prosody=None, tries=5):
    last = None
    for k in range(tries):
        try:
            tts_segment(text, voice, path, prosody)
            if os.path.exists(path) and os.path.getsize(path) > 200:
                return True
        except Exception as e:
            last = e
        # Retry without optional prosody as a recovery path; keep the same full text.
        if prosody and k >= 1:
            try:
                tts_segment(text, voice, path, None)
                if os.path.exists(path) and os.path.getsize(path) > 200:
                    return True
            except Exception as e:
                last = e
        time.sleep(0.5 * (k + 1))
    return False


def shorten_groq(api_key, text, max_seconds):
    limit = max(6, int(max_seconds * 11))
    try:
        models = groq_chat_models(api_key)[:3]
    except Exception:
        return text
    for model in models:
        try:
            body = json.dumps({
                "model": model, "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": f"Shorten the Khmer sentence to at most {limit} characters. Keep the meaning. Khmer script only. Return only the sentence."},
                    {"role": "user", "content": text},
                ],
            }).encode("utf-8")
            request = urllib.request.Request(
                GROQ_CHAT_URL, data=body, method="POST",
                headers={"Authorization": f"Bearer {groq_first(api_key)}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            with groq_urlopen(request, api_key, timeout=40) as r:
                data = json.loads(r.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
            out = clean_translation(content)
            if out and has_khmer(out) and len(out) < len(text):
                return out
        except Exception:
            continue
    return text


def make_dub(folder, segments, voice, duration, keep_bg, client, model,
             seg_voices=None, targets=None, notes=None, emotions=None, groq_key=None,
             clone_voice=None, eleven_key=None, ref_bands=None, offset=0.0, tight=True):
    inputs, filters = [], []
    n = 0
    if keep_bg:
        inputs += ["-i", "audio.mp3"]
        filters.append("[0:a]volume=0.08[bg]")
        n = 1
    first_voice = n
    n_seg = len(segments)
    voices_ = [seg_voices[i] if seg_voices else voice for i in range(n_seg)]
    pros = []
    for i in range(n_seg):
        p = None
        if emotions is not None and i < len(emotions):
            label, inten = emotions[i]
            p = emotion_prosody(label, inten, use_pitch=(targets is None))
        pros.append(p)

    clone_stats = {"ok": 0, "fail": 0, "err": ""}

    def gen(i):
        s_, e_, t_ = segments[i]
        next_s_ = segments[i + 1][0] if i + 1 < n_seg else duration
        slot0 = max(0.6, min(next_s_ - 0.08, e_ + (0.3 if tight else 1.0)) - s_)
        path_ = os.path.join(folder, f"tts_{i}.mp3")
        try:
            if not tts_retry(t_, voices_[i], path_, pros[i]):
                return None
            d_, _, _ = probe_media(path_)
            # Preserve the complete translated sentence. Do not automatically
            # ask an LLM to shorten it, since that can omit words or meaning.
            if clone_voice:
                try:
                    eleven_sts(eleven_key, clone_voice, path_)
                    d_, _, _ = probe_media(path_)
                    clone_stats["ok"] += 1
                except Exception as ce:
                    clone_stats["fail"] += 1
                    clone_stats["err"] = str(ce)[:160]
            f0_ = None
            if targets is not None and i < len(targets) and targets[i]:
                f0_ = tts_median_pitch(path_)
            tb_ = None
            if ref_bands and not clone_voice:
                try:
                    tb_ = band_levels(load_pcm(path_))
                except Exception:
                    tb_ = None
            return d_, f0_, tb_
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(gen, range(n_seg)))

    voice_eq = {}
    if ref_bands and not clone_voice:
        import numpy as np
        for v_ in set(voices_):
            arrs = [r_[2] for k_, r_ in enumerate(results) if r_ and r_[2] and voices_[k_] == v_]
            if arrs:
                eqs = eq_filters(ref_bands, np.mean(arrs, axis=0).tolist())
                if eqs:
                    voice_eq[v_] = eqs
        if notes is not None and voice_eq:
            notes.append("🎚 ផ្គូផ្គងពណ៌សំឡេងស្រដៀងសំឡេងគំរូ")
    if notes is not None and clone_voice:
        notes.append(f"🧑‍🎤 ក្លូនសំឡេងបាន {clone_stats['ok']}/{n_seg} ឃ្លា"
                     + (f" (បរាជ័យ: {clone_stats['err']})" if clone_stats["fail"] else ""))
    cursor = 0.0
    plan = []
    skipped = 0
    for i, res in enumerate(results):
        s, e, t = segments[i]
        if res is None:
            skipped += 1
            continue
        d, f0, _tb = res
        next_s = segments[i + 1][0] if i + 1 < n_seg else duration
        start = max(s + offset, 0.0)
        if start >= duration - 0.3:
            break
        slot = max(0.6, min(next_s - 0.04, e + (0.3 if tight else 1.2)) - start)
        # Fit the complete generated sentence into its available slot when
        # possible. atempo > 1 speeds up; < 1 slows down. Avoid extreme rates
        # that make Khmer hard to understand.
        # Previous line still talking? Start right after it, never overlap.
        if start < cursor:
            start = cursor
            slot = max(0.6, min(next_s - 0.04, e + 1.2) - start)
        # Too long for its slot -> speed up (max 1.35x) so it never talks over the next line.
        speed = d / slot if d > slot else 1.0
        speed = min(1.35, max(1.0, speed))
        cursor = max(cursor, start + d / speed + 0.08)
        target = targets[i] if (targets is not None and i < len(targets) and targets[i]) else None
        plan.append({"name": f"tts_{i}.mp3", "start": start, "speed": speed,
                     "voice": voices_[i], "f0": f0 if target else None, "target": target,
                     "eq": voice_eq.get(voices_[i], "")})
    if notes is not None and skipped:
        notes.append(f"⚠️ មិនអាចបង្កើតសំឡេង {skipped} ឃ្លា")
    if not plan:
        return False
    base = {}
    for v in set(p["voice"] for p in plan):
        vals = [p["f0"] for p in plan if p["voice"] == v and p["f0"]]
        if vals:
            base[v] = float(statistics.median(vals))
    stats = {}
    for p in plan:
        ratio = 1.0
        if p["target"] and base.get(p["voice"]):
            ratio = p["target"] / base[p["voice"]]
            ratio = max(MATCH_MIN, min(MATCH_MAX, ratio))
            if abs(ratio - 1.0) < 0.03:
                ratio = 1.0
            rec = stats.setdefault(p["voice"], [[], []])
            rec[0].append(ratio)
            rec[1].append(p["target"])
        delay = int(p["start"] * 1000)
        inputs += ["-i", p["name"]]
        if ratio == 1.0:
            chain = atempo_chain(p["speed"])
        else:
            chain = ("aresample=24000," f"asetrate={int(24000 * ratio)}," "aresample=24000," + atempo_chain(p["speed"] / ratio))
        if p.get("eq"):
            chain += "," + p["eq"]
        filters.append(f"[{n}:a]{chain},adelay={delay}:all=1[a{n}]")
        n += 1
    if notes is not None:
        for v, (ratios, tgts) in stats.items():
            who = "ប្រុស" if v == VOICE_MALE else "ស្រី"
            notes.append(f"🧬 សំឡេង AI {who}៖ ~{int(base[v])}Hz → " f"សំឡេងដើម ~{int(statistics.median(tgts))}Hz " f"(កែ ×{statistics.mean(ratios):.2f})")
    labels = "[bg]" if keep_bg else ""
    labels += "".join(f"[a{k}]" for k in range(first_voice, n))
    limiter = ",alimiter=limit=0.95" if emotions is not None else ""
    fc = (";".join(filters) + f";{labels}amix=inputs={n}:dropout_transition=0," f"volume={n}{limiter}[out]")
    run_ffmpeg(inputs + ["-filter_complex", fc, "-map", "[out]", "-t", f"{duration:.2f}", "dub.wav"], cwd=folder)
    return os.path.exists(os.path.join(folder, "dub.wav"))


def build_video_filter(max_side, subs=True):
    parts = []
    if max_side and max_side > 0:
        parts.append(f"scale=w='if(gt(iw,ih),-2,min({max_side},iw))':" f"h='if(gt(iw,ih),min({max_side},ih),-2)'")
    if subs:
        parts.append("ass=filename=captions.ass:fontsdir=.")
    parts.append("format=yuv420p")
    return ",".join(parts)


def render_with_fonts(folder, fonts, captions, font_size, outline_size,
                      color, vid_w, vid_h, quality, status, dub=False, style=None, subs=True):
    ass_path = os.path.join(folder, "captions.ass")
    output_path = os.path.join(folder, "output.mp4")
    max_side, crf, preset = quality
    if not subs:
        args = ["-i", "input.mp4"]
        if dub:
            args += ["-i", "dub.wav"]
        args += ["-vf", build_video_filter(max_side, False)]
        if dub:
            args += ["-map", "0:v:0", "-map", "1:a:0"]
        args += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "output.mp4"]
        log = run_ffmpeg(args, cwd=folder)
        with open(output_path, "rb") as f:
            data = f.read()
        return data, "-", log, ["មិនដាក់អក្សរ"]
    conf_env = make_fontconfig_env(folder)
    plan = [(0, False), (0, True)]
    plan += [(i, True) for i in range(1, len(fonts))]
    attempts = []
    have_output = False
    best = None
    for font_index, use_conf in plan:
        font_path, default_name = fonts[font_index]
        family = get_font_family(font_path, default_name)
        keys = [family.lower(), default_name.lower()]
        write_ass(ass_path, captions, family, font_size, outline_size, color, vid_w, vid_h, style)
        args = ["-i", "input.mp4"]
        if dub:
            args += ["-i", "dub.wav"]
        args += ["-vf", build_video_filter(max_side)]
        if dub:
            args += ["-map", "0:v:0", "-map", "1:a:0"]
        args += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "output.mp4"]
        try:
            log = run_ffmpeg(args, cwd=folder, verbose=True, env=conf_env if use_conf else None)
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


def new_item(name, path=None, url=None):
    return {
        "name": name, "path": path, "url": url, "state": "queued",
        "stage": "ក្នុងជួររង់ចាំ...", "pct": 0.0, "warn": [], "log": [],
        "video": None, "captions": [], "voice_lines": [], "error": None,
        "raw_error": "", "debug": {}, "t0": None, "elapsed": None,
        "srt": "", "srt_on": False,
        "review_segments": None, "review_final": None, "review_event": None,
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
        return any(it["state"] in ("queued", "running", "review") for it in self.items)
    def reviewing(self):
        return any(it["state"] == "review" for it in self.items)


def engine_name(engine):
    return "ឥតគិតថ្លៃ (Groq)" if engine == "free" else "Gemini"


def run_worker(job, item, settings, fonts_data):
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
            duration, vid_w, vid_h = probe_media(source)
            if duration > MAX_DURATION_MIN * 60:
                raise UserError(f"វីដេអូវែងពេក។ សូមប្រើវីដេអូខ្លីជាង {MAX_DURATION_MIN} នាទី។")
            speech = detect_speech(master_path, duration)
            item["pct"] = 0.25
            rep.write("៣/៤ កំពុងស្តាប់ និងបកប្រែជាភាសាខ្មែរ...")
            order = (["free", "gemini"] if settings["engine"] == "free" else ["gemini", "free"])
            order = [k for k in order if (k == "free" and settings["groq_key"]) or (k == "gemini" and settings["gemini_key"])]
            segments = None
            used_engine = ""
            used_model = ""
            failed_chunks = 0
            engine_errors = []
            for idx, engine in enumerate(order):
                try:
                    if engine == "free":
                        segments, used_model, failed_chunks = transcribe_free(settings["groq_key"], audio_path, duration, settings["language"], rep, speech=speech, dub=settings["dub_on"], gemini_key=settings["gemini_key"], keep_failed=bool(settings.get("review_on")))
                    else:
                        segments, used_model, failed_chunks = transcribe(settings["gemini_key"], master_path, duration, settings["language"], rep, concise=settings["dub_on"], speech=speech)
                    used_engine = engine
                    break
                except UserError:
                    raise
                except Exception as e:
                    reason = f"{engine_name(engine)}: {str(e)[:400]}"
                    engine_errors.append(reason)
                    if idx + 1 < len(order):
                        item["warn"].append("ម៉ាស៊ីនទីមួយមានបញ្ហា កម្មវិធីបានប្តូរទៅម៉ាស៊ីនបម្រុងដោយស្វ័យប្រវត្តិ។" f"\n\nមូលហេតុ → {reason}")
                        rep.write("កំពុងប្តូរទៅម៉ាស៊ីនបម្រុង...")
            if segments is None:
                raise UserError("ម៉ាស៊ីនបកប្រែទាំងអស់បរាជ័យ។\n\n" + "\n\n".join(engine_errors))
            if failed_chunks:
                item["warn"].append("ផ្នែកខ្លះនៃវីដេអូមិនអាចបកប្រែបាន។ សូមសាកម្តងទៀតពេលក្រោយ។")
            item["pct"] = 0.55
            segments = snap_segments(segments, speech, duration)
            if settings.get("narrate_on"):
                rep.write("📖 កំពុងកែសម្រួលជាភាសានិទានរឿង...")
                narr_notes = []
                try:
                    segments = narrate_rewrite(segments, settings["groq_key"], settings["gemini_key"], narr_notes)
                    item["warn"].extend(narr_notes)
                except Exception:
                    item["warn"].append("ម៉ូដនិទានរឿងមានបញ្ហា ប្រើអត្ថបទបកប្រែដើម។")
            if settings.get("review_on"):
                segments = wait_for_review(item, segments)
                item["pct"] = 0.55
            captions, sync_mode = build_captions(segments, duration)
            if not captions:
                raise UserError("រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូនេះទេ។")
            dub_ok = False
            if settings["dub_on"]:
                item["pct"] = 0.6
                rep.write("🎙 កំពុងបង្កើតសំឡេងខ្មែរ...")
                try:
                    client = (make_gemini_client(settings["gemini_key"]) if used_engine == "gemini" else None)
                    dub_segments = merge_for_dub(segments)
                    seg_voices = None
                    targets = None
                    emotions = None
                    voice_notes = []
                    pitch_inf = None
                    runs_ = None
                    ref_bands = None
                    need_audio = (settings["auto_gender"] or settings["voice_match"] or settings["emotion"] or settings.get("timbre"))
                    if need_audio:
                        try:
                            rep.write("🔍 កំពុងវិភាគសំឡេងអ្នកនិយាយដើម...")
                            pcm = load_pcm(master_path)
                            tracks = pitch_track(pcm)
                            pitch_inf = {"times": tracks[0], "f0": tracks[1], "rms": tracks[2]}
                            if settings.get("timbre"):
                                ref_pcm = pcm
                                if settings.get("timbre_sample"):
                                    sp = os.path.join(folder, "timbre_sample.bin")
                                    with open(sp, "wb") as f:
                                        f.write(settings["timbre_sample"])
                                    ref_pcm = load_pcm(sp)
                                ref_bands = band_levels(ref_pcm)
                            if settings["auto_gender"]:
                                planned, lines, voice_info, runs_ = plan_dub_voices(dub_segments, pcm, settings["voice"], duration, tracks=tracks)
                                dub_segments = [(s, e, t) for s, e, t, _ in planned]
                                seg_voices = [v for _, _, _, v in planned]
                                pitch_inf = voice_info
                                voice_notes = [voice_info.get("summary", "")] + lines
                            if settings["voice_match"]:
                                targets = compute_targets(dub_segments, seg_voices, pitch_inf, runs_)
                        except Exception:
                            dub_segments = merge_for_dub(segments)
                            seg_voices = None
                            targets = None
                            voice_notes = []
                            pitch_inf = None
                            runs_ = None
                            item["warn"].append("វិភាគសំឡេងអ្នកនិយាយមិនបាន ប្រើសំឡេងតែមួយតាមដែលបានជ្រើស។")
                    if settings["emotion"]:
                        try:
                            rep.write("🎭 កំពុងវិភាគអារម្មណ៍...")
                            emotions, emo_lines = plan_emotions(dub_segments, seg_voices, pitch_inf, runs_, settings["groq_key"], settings["gemini_key"])
                            voice_notes = voice_notes + emo_lines
                        except Exception:
                            emotions = None
                            item["warn"].append("វិភាគអារម្មណ៍មិនបាន ប្រើសំឡេងធម្មតា។")
                    clone_voice = None
                    if settings.get("clone_sample") and settings.get("eleven_key"):
                        try:
                            rep.write("🧑‍🎤 កំពុងក្លូនសំឡេងគំរូ...")
                            clone_voice = eleven_add_voice(settings["eleven_key"], settings["clone_sample"])
                            targets = None
                        except Exception as ce:
                            item["warn"].append("ក្លូនសំឡេងមិនបាន ប្រើសំឡេង AI ធម្មតា។ មូលហេតុ: " + str(ce)[:200])
                    rep.write("🎙 កំពុងបង្កើតសំឡេងខ្មែរ...")
                    match_notes = []
                    try:
                        dub_ok = make_dub(folder, dub_segments, settings["voice"], duration, settings["keep_bg"], client, used_model, seg_voices=seg_voices, targets=targets, notes=match_notes, emotions=emotions, groq_key=settings["groq_key"], clone_voice=clone_voice, eleven_key=settings.get("eleven_key"), ref_bands=ref_bands, offset=0.0, tight=False)
                    finally:
                        if clone_voice:
                            eleven_delete_voice(settings["eleven_key"], clone_voice)
                    item["voice_lines"] = match_notes + voice_notes
                except Exception:
                    dub_ok = False
                if not dub_ok:
                    item["warn"].append("បង្កើតសំឡេងអានមិនបានទេ។ វីដេអូមានតែអក្សរ។")
            item["pct"] = 0.75
            rep.write("៤/៤ កំពុងរង់ចាំដាក់អក្សរចូលវីដេអូ...")
            with job.render_slots:
                item["pct"] = 0.82
                rep.write("៤/៤ កំពុងដាក់អក្សរចូលវីដេអូ...")
                video, used_font, ffmpeg_log, attempts = render_with_fonts(folder, fonts, captions, settings["font_size"], settings["outline_size"], settings["color"], vid_w, vid_h, settings["quality"], rep, dub=dub_ok, style=settings["style"], subs=settings["sub_on"])
            item["video"] = video
            item["captions"] = [t for _, _, t in captions]
            item["srt"] = make_srt(captions)
            item["srt_on"] = settings["srt_on"]
            item["debug"] = {
                "ម៉ាស៊ីន": used_engine, "ម៉ូដែល": used_model,
                "ការតម្រឹម": sync_mode, "ផ្នែកបរាជ័យ": failed_chunks,
                "Font ដែលប្រើ": used_font, "Dubbing": dub_ok,
                "អ្នកនិយាយ": (item["voice_lines"][0] if item["voice_lines"] else ""),
                "ទំហំលទ្ធផល": f"{len(video) / (1024 * 1024):.1f}MB",
                "ការសាក Font": "\n".join(attempts),
                "fontselect": "\n".join(line for line in ffmpeg_log.splitlines() if "fontselect" in line.lower())[:1500],
                "ម៉ោងអក្សរ": "\n".join(f"[{s:.1f}-{e:.1f}] {t}" for s, e, t in captions),
            }
            item["pct"] = 1.0
            item["stage"] = "រួចរាល់"
            item["elapsed"] = time.time() - item["t0"]
            # Automatically add completed outputs to the shared gallery.
            item["gallery_saved"] = save_to_public_gallery(item["name"], video)
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
        try:
            if item.get("path") and os.path.exists(item["path"]):
                os.remove(item["path"])
        except Exception:
            pass


NARR_SYSTEM = (
    "You are a Cambodian storyteller who narrates films and dramas for Khmer YouTube/TikTok channels. "
    "The numbered lines are consecutive Khmer dialogue lines of ONE story. Rewrite each line as lively, natural spoken "
    "Khmer narration/dialogue that a native audience enjoys: smooth flow between lines, correct emotion, natural particles, "
    "consistent pronouns. Keep EXACTLY the same meaning, names and facts; add nothing new; do not merge or drop lines; "
    "each rewritten line must be no longer than the original line. Khmer script only. "
    "Return JSON {\"translations\": [...]} with exactly one item per input, same order."
)


def narrate_rewrite(segments, groq_key=None, gemini_key=None, notes=None):
    """Polish translated lines into natural storytelling Khmer (same count, same timing)."""
    out = [t for _, _, t in segments]
    n = len(out)
    if n == 0:
        return segments
    client = None
    if gemini_key:
        try:
            client = make_gemini_client(gemini_key, types.HttpOptions(timeout=TRANSLATE_TIMEOUT_MS))
            models = get_available_models(client)[:5]
        except Exception:
            client = None
    done_lines = 0
    for k in range(0, n, 8):
        idxs = list(range(k, min(k + 8, n)))
        batch = [out[i] for i in idxs]
        story = " / ".join(out[max(0, k - 5):k])
        res = None
        if client:
            rows = "\n".join(f"{j + 1}. {t} [max {max(8, len(t))} chars]" for j, t in enumerate(batch))
            prompt = NARR_SYSTEM + "\n\n" + (("PREVIOUS LINES (context only):\n" + story + "\n\n") if story else "") + "LINES:\n" + rows
            for model in model_order(models, "gemini"):
                try:
                    resp = client.models.generate_content(
                        model=model, contents=prompt,
                        config=types.GenerateContentConfig(temperature=0.5, response_mime_type="application/json"))
                    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (getattr(resp, "text", "") or "").strip())
                    data = json.loads(raw)
                    items = data.get("translations") if isinstance(data, dict) else data
                    if isinstance(items, list) and len(items) == len(batch):
                        res = [clean_translation(x) for x in items]
                        model_good("gemini", model)
                        break
                except Exception as e_:
                    model_cool(model, e_)
                    continue
        if res is None and groq_key:
            try:
                res = groq_translate_chunk(groq_key, batch, [max(8, len(t)) for t in batch], system=NARR_SYSTEM)
            except Exception:
                res = None
        if res:
            for i, r in zip(idxs, res):
                if r and has_khmer(str(r)):
                    out[i] = r
                    done_lines += 1
    if notes is not None:
        notes.append(f"📖 ម៉ូដនិទានរឿង៖ កែឃ្លាឱ្យរលូន {done_lines}/{n} ឃ្លា")
    return [(s_, e_, t_) for (s_, e_, _), t_ in zip(segments, out)]


def wait_for_review(item, segments, timeout=1800):
    """Pause the worker so the person can fix the Khmer lines, then continue."""
    item["review_segments"] = list(segments)
    item["review_final"] = None
    item["review_event"] = threading.Event()
    item["stage"] = "✏️ សូមពិនិត្យ/កែអត្ថបទខ្មែរ រួចចុច «បន្ត»"
    bad = sum(1 for _, _, t_ in segments if str(t_).startswith("⚠️"))
    if bad:
        item["warn"].append(f"⚠️ មាន {bad} ឃ្លាដែល AI បកមិនបាន (ដាក់ស្លាក ⚠️)។ សូមវាយអត្ថបទខ្មែរជំនួស បើមិនកែ ឃ្លានោះនឹងត្រូវលុបចោល។")
    item["pct"] = 0.5
    item["state"] = "review"
    item["review_event"].wait(timeout)
    final = item.get("review_final")
    item["state"] = "running"
    item["review_segments"] = None
    if not final:
        return segments
    cleaned = [(s_, e_, fix_khmer(t_.replace("⚠️", "").strip())) for s_, e_, t_ in final if t_ and has_khmer(t_)]
    return cleaned or segments


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
            z.writestr(f"{i:02d}_{safe_filename(it['name'])}_khmer.mp4", it["video"])
    return buf.getvalue()


def dl_button(label, data, file_name, mime, key, **kwargs):
    if ST_VER >= (1, 43):
        return st.download_button(label, data=data, file_name=file_name, mime=mime, key=key, on_click="ignore", **kwargs)
    return st.download_button(label, data=data, file_name=file_name, mime=mime, key=key, **kwargs)


def work_area(job, was_running, reviewing=False):
    items = job.items
    total = len(items)
    done = sum(1 for it in items if it["state"] == "done")
    failed = sum(1 for it in items if it["state"] == "error")
    working = total - done - failed
    c1, c2, c3 = st.columns(3)
    c1.metric("⏳ កំពុងធ្វើ", working)
    c2.metric("✅ រួចរាល់", done)
    c3.metric("❌ បរាជ័យ", failed)
    st.progress((done + failed) / total, text=f"សរុប {done + failed} / {total}")
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
            elif it["state"] == "review" and it.get("review_segments"):
                st.info("✏️ ពិនិត្យអត្ថបទខ្មែរ។ កែឃ្លាដែលខុស ឬលុបអត្ថបទចោលដើម្បីកាត់ឃ្លានោះ រួចចុច «បន្ត»។")
                with st.form(key=f"review_form_{job.id}_{i}"):
                    for j, (s_, e_, t_) in enumerate(it["review_segments"]):
                        st.text_area(f"{j + 1}. [{s_:.1f}s – {e_:.1f}s]", value=t_, key=f"rev_{job.id}_{i}_{j}", height=80)
                    go = st.form_submit_button("✅ បន្តបង្កើតសំឡេង និងវីដេអូ", type="primary", use_container_width=True)
                if go:
                    it["review_final"] = [
                        (s_, e_, str(st.session_state.get(f"rev_{job.id}_{i}_{j}", t_)))
                        for j, (s_, e_, t_) in enumerate(it["review_segments"])
                    ]
                    it["state"] = "running"
                    it["stage"] = "កំពុងបន្ត..."
                    if it.get("review_event"):
                        it["review_event"].set()
                    st.rerun()
            else:
                st.progress(max(0.0, min(1.0, it["pct"])), text=it["stage"])
            for w in it["warn"]:
                st.warning(w)
    if (was_running and not job.running()) or (reviewing != job.reviewing()):
        st.rerun()


def download_area(job):
    done = [(i, it) for i, it in enumerate(job.items, start=1) if it["state"] == "done"]
    if job.zip:
        dl_button("📦 ទាញយកទាំងអស់ (ZIP)", job.zip, "khmer_videos.zip", "application/zip", key=f"zip_{job.id}", use_container_width=True)
    if not done:
        st.info("វីដេអូណាដែលរួចរាល់ នឹងលេចឡើងនៅទីនេះភ្លាមៗ ហើយអាចទាញយកបានតែម្តង។")
        return
    for i, it in done:
        with st.container(border=True):
            st.markdown(f"**{i}. {it['name']}**")
            st.video(it["video"])
            dl_button("⬇️ ទាញយកវីដេអូនេះ", it["video"], f"{safe_filename(it['name'])}_khmer.mp4", "video/mp4", key=f"dl_{job.id}_{i}", type="primary", use_container_width=True)
            if it.get("srt_on") and it.get("srt"):
                dl_button("📄 ទាញយក SRT", it["srt"].encode("utf-8"), f"{safe_filename(it['name'])}_khmer.srt", "text/plain", key=f"srt_{job.id}_{i}", use_container_width=True)
            with st.expander("📝 មើលអត្ថបទខ្មែរ"):
                for text in it["captions"]:
                    st.write(text)
            if it.get("voice_lines"):
                with st.expander("👫 ព័ត៌មានសំឡេងអាន"):
                    for line in it["voice_lines"]:
                        st.write(line)
            if DEBUG:
                with st.expander("🛠 DEBUG"):
                    for key, value in it["debug"].items():
                        st.text(f"{key}: {value}")
                    st.text("\n".join(it["log"][-30:]))


def scroll_to_downloads():
    components.html(
        f"""
        <script>
        // {time.time()}
        const go = () => {{
          try {{
            const doc = window.parent.document;
            const el = doc.getElementById("download-area");
            if (el) {{ el.scrollIntoView({{behavior: "smooth", block: "start"}}); return true; }}
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


GEMINI_KEY = "\n".join(split_keys([
    get_secret("GEMINI_API_KEY", ""),
    get_secret("GEMINI_API_KEYS", ""),
]))  # ទទួលបានច្រើន key (បំបែកដោយ , ឬបន្ទាត់ថ្មី ឬជា list)
GROQ_KEY = "\n".join(split_keys([
    get_secret("GROQ_API_KEY", ""),
    get_secret("GROQ_API_KEYS", ""),
]))
ELEVEN_KEY = get_secret("ELEVENLABS_API_KEY", "")

render_header()

if not GEMINI_KEY and not GROQ_KEY:
    st.error("កម្មវិធីមិនទាន់រួចរាល់ទេ។ សូមទាក់ទងម្ចាស់កម្មវិធី។")
    st.stop()

ENGINE_FREE = "🆓 ឥតគិតថ្លៃ (Groq + Google Translate)"
ENGINE_GEMINI = "✨ Gemini (ធម្មជាតិជាង តែមានកូតា)"

current_job = st.session_state.get("job")
busy = bool(current_job and current_job.running())

voice_label = list(TTS_VOICES.keys())[0]
keep_bg = False
auto_gender = True
voice_match = False
emotion = False
clone_on = False
clone_file = None
timbre = False
timbre_file = None
dub_offset = 0.0
tight_sync = False

# ប៊ូតុងចាប់ផ្តើម (ជាប់ខាងក្រោម) — បំពេញនៅខាងក្រោយ
start_slot = st.container(key="startbar")

tab_vid, tab_trans, tab_voice, tab_text, tab_out, tab_gallery = st.tabs(
    ["🏠 វីដេអូ", "🌐 បកប្រែ", "🎙 សំឡេង", "🔤 អក្សរ", "⬇️ ទាញយក", "🎬 វីដេអូរួម"]
)

# ============================ ផ្ទាំង ១: វីដេអូ ============================
with tab_vid:
    with st.container(border=True):
        mode = st.radio("វិធីបញ្ចូលវីដេអូ", ["📁 Upload", "🔗 Link"], horizontal=True,
                        label_visibility="collapsed", key="mode_pick")
        uploaded_files = []
        link_text = ""
        if mode.startswith("📁"):
            uploaded_files = st.file_uploader(
                "បន្ថែមវីដេអូ (ជ្រើសបានច្រើន)", type=["mp4", "mov", "mkv", "avi", "webm"],
                accept_multiple_files=True) or []
        else:
            link_text = st.text_area("តំណវីដេអូ (មួយបន្ទាត់ ១ តំណ)", placeholder="https://...", height=90)
        st.caption(f"រហូតដល់ {MAX_VIDEOS} វីដេអូ · រហូតដល់ {MAX_DURATION_MIN // 60} ម៉ោង · តំណអតិបរមា {MAX_DOWNLOAD_MB}MB")
        if uploaded_files:
            try:
                st.video(uploaded_files[0])
            except Exception:
                pass
    with st.container(border=True):
        quality_label = st.radio("📈 គុណភាពវីដេអូ", list(QUALITY.keys()), index=1,
                                 horizontal=True, key="quality_pick")

# ============================ ផ្ទាំង ២: បកប្រែ ============================
with tab_trans:
    with st.container(border=True):
        engine_options = []
        if GROQ_KEY:
            engine_options.append(ENGINE_FREE)
        if GEMINI_KEY:
            engine_options.append(ENGINE_GEMINI)
        engine_label = st.selectbox("ម៉ាស៊ីនបកប្រែ", engine_options, index=0)
        lc1, lc2 = st.columns(2)
        with lc1:
            language_label = st.selectbox("ភាសាដើម", list(LANGUAGES.keys()), index=0)
        with lc2:
            st.selectbox("បកប្រែទៅ", ["🇰🇭 ខ្មែរ"], disabled=True, key="target_lang")
    with st.container(border=True):
        sub_on = st.toggle("បង្កើតអក្សររត់ខ្មែរ (Subtitle)", value=True)
        dub_on = st.toggle("បង្កើតសំឡេងអានខ្មែរ (Dubbing)")
        srt_on = st.toggle("ទាញយកអក្សរជាឯកសារ (SRT)")
        narrate_on = st.toggle(
            "📖 ម៉ូដនិទានរឿង (កែអត្ថបទឱ្យរលូនដូចអ្នកនិទាន)",
            value=False, key="narrate_pick",
            help="AI កែសម្រួលអត្ថបទបកប្រែទាំងមូលជាភាសានិទានរឿង ឱ្យរលូនតគ្នា ដោយរក្សាអត្ថន័យ និងពេលវេលាដដែល។",
        )
        review_on = st.toggle(
            "✏️ ពិនិត្យ និងកែអត្ថបទមុនបង្កើតសំឡេង",
            value=True, key="review_pick",
            help="កម្មវិធីនឹងឈប់រង់ចាំអ្នកកែអត្ថបទខ្មែរតាមបន្ទាត់ មុននឹងបង្កើតសំឡេង និងវីដេអូ។",
        )

# ============================ ផ្ទាំង ៣: សំឡេង ============================
with tab_voice:
    with st.container(border=True):
        # Keep only the simple voice choices requested by the user.
        voice_label = st.radio("ជ្រើសសំឡេងនិយាយ", list(TTS_VOICES.keys()), horizontal=True, key="voice_pick")
        auto_gender = st.toggle(
            "🎭 ឱ្យ AI ប្តូរសំឡេងប្រុស/ស្រីតាមអ្នកនិយាយក្នុងវីដេអូ",
            value=True,
            help="បើបើក AI នឹងវិភាគសំឡេងដើម ហើយប្រើសំឡេងប្រុសសម្រាប់អ្នកនិយាយប្រុស និងសំឡេងស្រីសម្រាប់អ្នកនិយាយស្រី។ ត្រូវការសំឡេងដើមច្បាស់។",
            key="auto_gender_pick",
        )
        emotion_on = st.toggle(
            "🎭 ដាក់អារម្មណ៍ក្នុងសំឡេង (ខឹង ក្រៀមក្រំ សប្បាយ ភ័យ)",
            value=True,
            help="AI វិភាគអារម្មណ៍ពីអត្ថបទ និងសំឡេងដើម ហើយកែល្បឿន កម្រិតសំឡេង និងកម្ពស់សំឡេងឱ្យសមនឹងអារម្មណ៍។",
            key="emotion_pick",
        )
        keep_bg = st.toggle("រក្សាសំឡេងដើមក្នុងវីដេអូ (ពេលមាន Dubbing)")
        if not dub_on:
            st.caption("💡 បើក «បង្កើតសំឡេងអានខ្មែរ» នៅផ្ទាំង 🌐 បកប្រែ ដើម្បីប្រើការនិយាយ។")

# ============================ ផ្ទាំង ៤: អក្សរ ============================
with tab_text:
    prev_slot = st.container()
    with st.container(border=True):
        a1, a2 = st.columns(2)
        with a1:
            font_name = st.selectbox("Font", [f[2] for f in FONT_SOURCES], index=0, key="font_pick")
        with a2:
            color_pick = st.selectbox("ពណ៌អក្សរ", list(COLOR_OPTIONS.keys()), index=0, key="color_pick")
        b1, b2 = st.columns(2)
        with b1:
            box_pick = st.selectbox("ផ្ទៃក្រោយ", list(BOX_OPTIONS.keys()), index=0, key="box_pick")
        with b2:
            style_pick = st.selectbox("បែបអក្សរ", list(STYLE_OPTIONS.keys()), index=0, key="style_pick")
        c1, c2 = st.columns(2)
        with c1:
            font_size = st.slider("ទំហំអក្សរ", 16, 36, 22)
        with c2:
            outline_size = st.slider("គែមអក្សរ", 1, 5, 2)
        pos_pick = st.radio("ទីតាំងអក្សរ", list(POS_MAP.keys()), index=7, horizontal=True, key="pos")
    bold_, italic_ = STYLE_OPTIONS[style_pick]
    with prev_slot:
        render_preview(font_size, COLOR_OPTIONS[color_pick][1], POS_MAP[pos_pick],
                       bold_, italic_, BOX_OPTIONS[box_pick])

# ============================ បញ្ជីវីដេអូ ============================
items = []
too_many = False
if uploaded_files:
    too_many = len(uploaded_files) > MAX_VIDEOS
    for f in uploaded_files[:MAX_VIDEOS]:
        items.append({"name": f.name, "file": f, "url": None})
else:
    lines = [ln.strip() for ln in link_text.splitlines() if ln.strip().lower().startswith(("http://", "https://"))]
    too_many = len(lines) > MAX_VIDEOS
    for i, url in enumerate(lines[:MAX_VIDEOS], start=1):
        tail = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
        items.append({"name": tail or f"តំណទី {i}", "file": None, "url": url})

# ============================ ប៊ូតុងចាប់ផ្តើម (ជាប់ខាងក្រោម) ============================
run = False
with start_slot:
    if busy:
        st.button("⏳ កំពុងធ្វើការ... មើលនៅផ្ទាំង ⬇️", disabled=True, use_container_width=True)
    elif not items:
        st.button("📁 សូមជ្រើសវីដេអូជាមុនសិន", disabled=True, use_container_width=True)
    elif not (sub_on or dub_on):
        st.button("⚠️ សូមបើក «អក្សររត់» ឬ «សំឡេងអាន»", disabled=True, use_container_width=True)
    else:
        label = "✨ ចាប់ផ្តើមបង្កើតវីដេអូ"
        if len(items) > 1:
            label += f" ({len(items)})"
        run = st.button(label, type="primary", use_container_width=True)
    if too_many:
        st.caption(f"⚠️ ធ្វើបានត្រឹម {MAX_VIDEOS} វីដេអូដំបូង។")

if run:
    try:
        fonts_data = load_font_bytes()
    except Exception:
        st.error("ទាញយក Font ខ្មែរមិនបាន។ សូមសាកម្តងទៀត។")
        st.stop()
    prepare_home_font(fonts_data)
    fonts_data = sorted(fonts_data, key=lambda f: 0 if f[2] == font_name else 1)
    settings = {
        "engine": "free" if engine_label == ENGINE_FREE else "gemini",
        "gemini_key": GEMINI_KEY, "groq_key": GROQ_KEY,
        "language": LANGUAGES[language_label], "quality": QUALITY[quality_label],
        "dub_on": dub_on, "voice": TTS_VOICES[voice_label],
        # Fixed internal defaults; no extra voice-tuning controls in the UI.
        "keep_bg": keep_bg, "dub_offset": 0.0, "tight_sync": False, "auto_gender": auto_gender,
        "voice_match": False, "emotion": emotion_on,
        "clone_sample": None,
        "eleven_key": ELEVEN_KEY,
        "timbre": False, "timbre_sample": None,
        "font_size": font_size, "outline_size": outline_size,
        "color": COLOR_OPTIONS[color_pick][0],
        "sub_on": sub_on, "srt_on": srt_on,
        "narrate_on": narrate_on, "review_on": review_on,
        "style": {"align": POS_MAP[pos_pick], "bold": bold_, "italic": italic_, "box": BOX_OPTIONS[box_pick]},
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
    job = Job(job_items, job_folder)
    st.session_state["job"] = job
    for item in job.items:
        threading.Thread(target=run_worker, args=(job, item, settings, fonts_data), daemon=True).start()
    st.rerun()

# ============================ ផ្ទាំង ៥: ធ្វើការ + ទាញយក ============================
job = st.session_state.get("job")
with tab_out:
    if not job:
        st.info("មិនទាន់មានលទ្ធផលទេ។ ជ្រើសវីដេអូ រួចចុច «ចាប់ផ្តើម» ខាងក្រោម។")
    else:
        running = job.running()
        if not running and not job.zip_done:
            job.zip = build_zip(job.items)
            job.zip_done = True
        reviewing = job.reviewing()
        refresh = REFRESH_SECONDS if (running and not reviewing) else None
        st.fragment(run_every=refresh)(work_area)(job, running, reviewing)
        st.markdown('<div id="download-area"></div>', unsafe_allow_html=True)
        st.fragment(run_every=refresh)(download_area)(job)
        if not running:
            if st.button("🗑 លុបលទ្ធផលទាំងអស់"):
                shutil.rmtree(job.folder, ignore_errors=True)
                st.session_state.pop("job", None)
                st.rerun()


# ============================ ផ្ទាំង ៦: វីដេអូរួម ============================
with tab_gallery:
    st.markdown("### 🎬 វីដេអូរួម")
    st.caption("វីដេអូដែលបង្កើតរួចនឹងត្រូវរក្សាទុកដោយស្វ័យប្រវត្តិ ហើយអ្នកប្រើអេបនេះអាចមើល/ទាញយកបាន។")
    try:
        gallery_rows = read_public_gallery()
    except Exception as gallery_error:
        gallery_rows = []
        st.error("មិនអាចបើកវីដេអូរួមបានទេ។ សូមពិនិត្យ Storage របស់ម៉ាស៊ីនអេប។")
    if not gallery_rows:
        st.info("មិនទាន់មានវីដេអូក្នុងវីដេអូរួមទេ។ បង្កើតវីដេអូរួច វានឹងបង្ហាញនៅទីនេះដោយស្វ័យប្រវត្តិ។")
    else:
        st.caption(f"មានវីដេអូ {len(gallery_rows)}")
        for gallery_id, gallery_name, gallery_filename, gallery_created, gallery_size in gallery_rows:
            gallery_path = os.path.join(PUBLIC_VIDEO_DIR, gallery_filename)
            if not os.path.isfile(gallery_path):
                continue
            with st.container(border=True):
                st.markdown(f"**{gallery_name}**")
                st.caption(time.strftime("%Y-%m-%d %H:%M", time.localtime(gallery_created)) + f" · {gallery_size / (1024 * 1024):.1f} MB")
                try:
                    st.video(gallery_path)
                except Exception:
                    st.caption("មើលវីដេអូនេះក្នុងកម្មវិធីមិនបាន ប៉ុន្តែអាចទាញយកបាន។")
                with open(gallery_path, "rb") as gallery_file:
                    gallery_data = gallery_file.read()
                dl_button("⬇️ ទាញយកវីដេអូ", gallery_data, gallery_filename, "video/mp4", key=f"gallery_dl_{gallery_id}", use_container_width=True)
