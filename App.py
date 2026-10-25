
import os
import io
import re
import json
import gc
import time
import uuid
import shutil
import asyncio
import zipfile
import base64
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
    page_title="បកប្រែវីដេអូមកនិយាយខ្មែរ",
    page_icon="🎬",
    layout="wide",
)

# =====================================================================
#  MODE កំពុង UPDATE
#  ► ពេលកំពុង update: ទុក MAINTENANCE_MODE = True  (អ្នកប្រើនឹងឃើញតែសារ «កំពុង Update»)
#  ► ពេល update ចប់: ប្តូរទៅ False  (ឬដាក់ MAINTENANCE_MODE = "0" ក្នុង Secrets)
# =====================================================================
MAINTENANCE_MODE = True
_maint_env = str(os.environ.get("MAINTENANCE_MODE", "")).strip().lower()
if _maint_env in ("0", "false", "off", "no"):
    MAINTENANCE_MODE = False
elif _maint_env in ("1", "true", "on", "yes"):
    MAINTENANCE_MODE = True

# លេខសម្ងាត់អ្នកគ្រប់គ្រង (ចូលកែ/សាកល្បងពេលកំពុង update)។ ប្តូរបាន ឬដាក់ MAINTENANCE_KEY ក្នុង Secrets
MAINTENANCE_ADMIN_KEY = os.environ.get("MAINTENANCE_KEY", "").strip() or "admin1234"
_is_admin = False
if MAINTENANCE_MODE:
    _qk = st.query_params.get("admin")
    if isinstance(_qk, list):
        _qk = _qk[0] if _qk else ""
    if st.session_state.get("_maint_admin") or (_qk and _qk == MAINTENANCE_ADMIN_KEY):
        st.session_state["_maint_admin"] = True
        _is_admin = True

if MAINTENANCE_MODE and not _is_admin:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Kantumruy+Pro:wght@400;700&display=swap');
.stApp { background: radial-gradient(circle at 50% 0%, #1b1450 0%, #0A0F2E 60%) !important; }
header, [data-testid="stToolbar"], [data-testid="stSidebar"] { display: none !important; }
.kvai-maint {
  max-width: 460px; margin: 18vh auto 0; padding: 36px 26px; text-align: center;
  border: 1px solid rgba(177,60,255,.45); border-radius: 26px;
  background: rgba(17,24,66,.75); box-shadow: 0 0 40px rgba(177,60,255,.25);
  font-family: 'Kantumruy Pro', 'Battambang', sans-serif; color: #E8ECFF;
}
.kvai-maint .ic { font-size: 64px; line-height: 1; animation: kvai-spin 3.2s linear infinite; display: inline-block; }
.kvai-maint h1 { font-size: 28px; margin: 18px 0 8px; color: #fff; }
.kvai-maint p { font-size: 17px; line-height: 1.7; margin: 6px 0; color: #C9D0FF; }
.kvai-maint .dots span { animation: kvai-blink 1.4s infinite both; font-size: 30px; color: #B13CFF; }
.kvai-maint .dots span:nth-child(2) { animation-delay: .2s; }
.kvai-maint .dots span:nth-child(3) { animation-delay: .4s; }
@keyframes kvai-spin { to { transform: rotate(360deg); } }
@keyframes kvai-blink { 0%, 80%, 100% { opacity: .15; } 40% { opacity: 1; } }
</style>
<div class="kvai-maint">
  <div class="ic">⚙️</div>
  <h1>កំពុង Update</h1>
  <p>យើងកំពុងធ្វើបច្ចុប្បន្នភាពកម្មវិធី ដើម្បីឱ្យប្រសើរជាងមុន។</p>
  <p>សូមអត់ធ្មត់ ហើយត្រឡប់មកវិញនៅពេលក្រោយ។ សូមអរគុណ 🙏</p>
  <div class="dots"><span>●</span><span>●</span><span>●</span></div>
</div>
""",
        unsafe_allow_html=True,
    )
    with st.expander("🔑 អ្នកគ្រប់គ្រង"):
        _pw = st.text_input("លេខសម្ងាត់", type="password", key="_maint_pw")
        if _pw and _pw == MAINTENANCE_ADMIN_KEY:
            st.session_state["_maint_admin"] = True
            st.rerun()
        elif _pw:
            st.error("លេខសម្ងាត់មិនត្រឹមត្រូវ")
    st.stop()

if MAINTENANCE_MODE and _is_admin:
    st.warning("⚙️ កំពុងស្ថិតក្នុង Mode Update — មានតែអ្នក (អ្នកគ្រប់គ្រង) ទេដែលឃើញកម្មវិធីពេញលេញ។ អ្នកដទៃឃើញតែទំព័រ «កំពុង Update»។")

# ---- Streamlit Cloud ----
# លំនាំដើម: អនុញ្ញាតឱ្យរត់លើ Cloud (មិនចាំបាច់ដាក់ Secrets អ្វីទេ)
# បើចង់បិទមិនឱ្យរត់លើ Cloud (ឱ្យរត់តែលើម៉ាស៊ីនមេខ្លួនឯង) កំណត់ BLOCK_STREAMLIT_CLOUD=1
def _running_on_streamlit_cloud():
    return os.path.isdir("/mount/src") or os.environ.get("HOME", "") == "/home/appuser"


IS_STREAMLIT_CLOUD = _running_on_streamlit_cloud()

if IS_STREAMLIT_CLOUD and os.environ.get("BLOCK_STREAMLIT_CLOUD") == "1":
    st.error("🚫 កម្មវិធីនេះមិនអនុញ្ញាតឱ្យរត់លើ Streamlit Cloud ទេ។ សូមប្រើម៉ាស៊ីនមេផ្ទាល់ខ្លួន។")
    st.stop()

# =====================================================================
#  THEME (Khmer Video AI — dark)
# =====================================================================
for _k, _v in {
    "theme.base": "dark",
    "theme.primaryColor": "#B13CFF",
    "theme.backgroundColor": "#0A0F2E",
    "theme.secondaryBackgroundColor": "#111842",
    "theme.textColor": "#E8ECFF",
    "server.maxUploadSize": 100,
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
[data-testid="stFileUploaderDropzoneInstructions"] small,
[data-testid="stFileUploaderDropzoneInstructions"] span + span,
[data-testid="stFileUploaderDropzoneInstructions"] div > span:nth-of-type(2) { display: none !important; }
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
            <h1>បកប្រែវីដេអូ<span>មកនិយាយខ្មែរ</span></h1>
            <p>បកប្រែវីដេអូ និងបង្កើតអក្សរ/សំឡេងខ្មែរ ដោយ AI</p>
          </div>
          <div class="kvai-badge">👑 គម្រោង VIP</div>
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


apply_theme()


def server_ram_info():
    """បង្ហាញ RAM របស់ម៉ាស៊ីនដែលកម្មវិធីកំពុងរត់ (អាន /proc/meminfo)។"""
    try:
        info = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.strip().split()[0])  # kB
        total = info["MemTotal"] / 1024 / 1024
        free = info.get("MemAvailable", info.get("MemFree", 0)) / 1024 / 1024
        host = os.uname().nodename
        return f"🖥️ ម៉ាស៊ីន: {host} · RAM សរុប {total:.1f}GB · នៅសល់ {free:.1f}GB"
    except Exception:
        return ""


def get_secret(name, default=""):
    """អាន secret ពី Environment Variable (Hugging Face Spaces) ឬ Streamlit secrets។"""
    val = os.environ.get(name)
    if val:
        return val
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


# បង្ហាញព័ត៌មានលម្អិត (DEBUG) ជានិច្ច ដល់អ្នកប្រើទាំងអស់
DEBUG = True

REQUEST_TIMEOUT_MS = 120000
TRANSLATE_TIMEOUT_MS = 40000   # ការបកប្រែអត្ថបទ: មិនរង់ចាំលើសពី ៤០ វិនាទី
MAX_CAPTION_CHARS = 26
def _env_int(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except Exception:
        return default


# Streamlit Cloud (RAM តូច) = 200MB · ម៉ាស៊ីនមេផ្ទាល់ខ្លួន = 2GB (ប្រើ RAM របស់ម៉ាស៊ីនខ្លួនឯង)
# អាចប្តូរបានតាម Environment Variable MAX_UPLOAD_MB
MAX_UPLOAD_MB = 100  # ទំហំអតិបរមាសម្រាប់ Upload (ថេរ ១០០MB)
MAX_DOWNLOAD_MB = _env_int("MAX_DOWNLOAD_MB", 200000)   # តំណវីដេអូ: ទំហំប៉ុន្មានក៏បាន (ចំនួនធំណាស់)
MAX_VIDEOS = _env_int("MAX_VIDEOS", 10)
MAX_ZIP_MB = 600
MOBILE_COPY = os.environ.get("MOBILE_COPY", "0") == "1"   # បង្កើតកំណែតូចសម្រាប់ទូរស័ព្ទ (encode ម្តងទៀត → យឺត) លំនាំដើមបិទ
REFRESH_SECONDS = 2
MAX_RENDER_AT_ONCE = 2
MAX_VIDEOS_AT_ONCE = _env_int("MAX_VIDEOS_AT_ONCE", 2)   # ធ្វើវីដេអូស្របគ្នាអតិបរមា ២ ដើម្បីកុំឲ្យអស់រ៉េមរហូតគាំងកម្មវិធី
_PIPELINE_SLOTS = threading.Semaphore(MAX_VIDEOS_AT_ONCE)
MAX_DURATION_MIN = 300

CHUNK_TARGET = 20.0
CHUNK_MAX = 28.0
MAX_CHUNK_WORKERS = 4

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODELS = ["whisper-large-v3", "whisper-large-v3-turbo"]

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GROQ_CHAT_PREFERRED = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
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
    "⚡ លឿន 480p": (480, 30, "ultrafast"),
    "✨ ល្អ 720p": (720, 28, "superfast"),
    "💎 ខ្ពស់ (ដើម)": (0, 25, "veryfast"),
}

# កំណត់ bitrate អតិបរមា ដើម្បីកុំឱ្យឯកសារធំពេក (ទាញយកលើទូរស័ព្ទបានលឿន)
RATE_CAP = {480: ("1200k", "2400k"), 720: ("2500k", "5000k"), 0: ("6000k", "12000k")}


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
        return "មានអ្នកប្រើច្រើនពេក ឬ API អស់កូតា។ សូមរង់ចាំមួយភ្លែត ឬដាក់ API Key ផ្ទាល់ខ្លួននៅផ្ទាំង «🌐 បកប្រែ»។"
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


def khmer_dominant(text, min_ratio=0.6):
    """អក្សរខ្មែរត្រូវមានច្រើនជាងអក្សរឡាតាំង (មិនអនុញ្ញាតឱ្យនៅសល់អង់គ្លេស/ចិនច្រើន)។"""
    t = str(text or "")
    kh = len(re.findall(r"[\u1780-\u17FF]", t))
    lat = len(re.findall(r"[A-Za-z]", t))
    if kh == 0:
        return False
    return kh / float(kh + lat) >= min_ratio


def tts_clean(text):
    """សម្អាតអត្ថបទមុនអាន ដើម្បីកុំឱ្យ TTS ផ្អាកដាច់ៗ ដោយសារសញ្ញាចម្លែកៗ។"""
    t = fix_khmer(text)
    t = re.sub(r"[\"\u201c\u201d\u2018\u2019'\u00ab\u00bb()\[\]{}<>*_#~`^|\\/]", " ", t)
    t = re.sub(r"(\.{2,}|\u2026+|[-\u2013\u2014]+)", " ", t)
    t = re.sub(r"[,;:\u060c]+", " ", t)
    t = re.sub(r"([!?\u17D4])\1+", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or fix_khmer(text)


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


def run_ffmpeg_progress(args, cwd=None, env=None, total=0.0, on_pct=None):
    """រត់ ffmpeg ហើយរាយការណ៍ភាគរយ (មិនចាំបាច់រង់ចាំងងឹតរហូតចប់)។"""
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [exe, "-y", "-nostats", "-progress", "pipe:1"] + args
    full_env = None
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=full_env,
                            text=True, encoding="utf-8", errors="ignore")
    err_buf = []

    def _drain():
        for line in proc.stderr:
            err_buf.append(line)
            if len(err_buf) > 400:
                del err_buf[:200]

    th = threading.Thread(target=_drain, daemon=True)
    th.start()
    t0 = time.time()
    last_cb = 0.0
    for line in proc.stdout:
        if not line.startswith("out_time_us="):
            continue
        try:
            sec = int(line.split("=", 1)[1]) / 1e6
        except Exception:
            continue
        now = time.time()
        if total > 0 and on_pct and now - last_cb >= 1.0:
            last_cb = now
            try:
                on_pct(max(0.0, min(0.99, sec / total)), now - t0)
            except Exception:
                pass
    proc.wait()
    th.join(timeout=3)
    if proc.returncode != 0:
        raise RuntimeError("FFmpeg បរាជ័យ:\n" + "".join(err_buf)[-1500:])


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


SOCIAL_HOSTS = ("tiktok.com", "douyin.com", "iesdouyin.com")


def is_social_link(url):
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS)


SSSTIK_BASE = "https://ssstik.io"
_SS_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_SS_HEADERS = {"User-Agent": _SS_UA, "Accept-Language": "en-US,en;q=0.9"}


def _ss_decode_link(u):
    if "ssscdn.io" not in u:
        return u
    try:
        parts = u.split("/")
        decoded = base64.b64decode("/".join(parts[5:])).decode("utf-8")
        if decoded.startswith("http"):
            return decoded
    except Exception:
        pass
    return u


def _ss_parse(page):
    import html as _html
    video_links = []
    for attrs in re.findall(r'<a\b([^>]*?)>', page, flags=re.I):
        cm = re.search(r'class=["\']([^"\']*)["\']', attrs, flags=re.I)
        hm = re.search(r'href=["\']([^"\']+)["\']', attrs, flags=re.I)
        if not hm:
            continue
        href = _html.unescape(hm.group(1))
        if not href.startswith("http"):
            continue
        css = cm.group(1) if cm else ""
        if "without_watermark" in css or "download_link" in css or "dl-button" in css:
            href = _ss_decode_link(href)
            if href not in video_links:
                video_links.append(href)
    if not video_links:
        for href in re.findall(r'href=["\'](https?://[^"\']+)["\']', page, flags=re.I):
            href = _html.unescape(href)
            low = href.lower()
            if ".mp4" in low or "ssscdn" in low or "tikcdn" in low:
                href = _ss_decode_link(href)
                if href not in video_links:
                    video_links.append(href)
    return video_links


def _ssstik_links(url):
    import requests
    sess = requests.Session()
    sess.headers.update(_SS_HEADERS)
    try:
        r = sess.get(SSSTIK_BASE + "/en", headers={**_SS_HEADERS, "Referer": SSSTIK_BASE + "/"}, timeout=30)
        r.raise_for_status()
        page = r.text
        m = (re.search(r"s_tt\s*=\s*['\"]([^'\"]+)['\"]", page)
             or re.search(r"tt\s*:\s*['\"]([^'\"]+)['\"]", page))
        if not m:
            raise RuntimeError("SSSTik token not found")
        token = m.group(1)
        fm = re.search(r"s_furl\s*=\s*['\"]([^'\"]+)['\"]", page)
        endpoint = fm.group(1) if fm else "abc"
        headers = {
            **_SS_HEADERS,
            "Origin": SSSTIK_BASE,
            "Referer": SSSTIK_BASE + "/en",
            "HX-Current-URL": SSSTIK_BASE + "/en",
            "HX-Request": "true",
            "HX-Target": "target",
            "HX-Trigger": "_gcaptcha_pt",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        r = sess.post(f"{SSSTIK_BASE}/{endpoint}?url=dl",
                      data={"id": url, "locale": "en", "tt": token}, headers=headers, timeout=60)
        r.raise_for_status()
        links = _ss_parse(r.text)
        if not links:
            raise RuntimeError("SSSTik returned no video link")
        return links
    finally:
        sess.close()


def _download_with_ssstik(url, path, progress):
    import requests
    limit = MAX_DOWNLOAD_MB * 1024 * 1024
    last = None
    for vurl in _ssstik_links(url):
        try:
            with requests.get(vurl, headers={"User-Agent": _SS_UA, "Referer": SSSTIK_BASE + "/"},
                              stream=True, timeout=120) as r:
                r.raise_for_status()
                ct = (r.headers.get("Content-Type") or "").lower()
                if "text/html" in ct or "json" in ct or ct.startswith("audio"):
                    raise RuntimeError("not a video file")
                total = int(r.headers.get("Content-Length") or 0)
                if total > limit:
                    raise RuntimeError(f"video larger than {MAX_DOWNLOAD_MB}MB")
                done = 0
                with open(path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        done += len(chunk)
                        if done > limit:
                            raise RuntimeError(f"video larger than {MAX_DOWNLOAD_MB}MB")
                        if total:
                            progress.progress(min(1.0, done / total))
            if os.path.getsize(path) < 1000:
                raise RuntimeError("empty video file")
            progress.progress(1.0)
            return
        except Exception as e:
            last = e
            try:
                os.remove(path)
            except Exception:
                pass
    raise last or RuntimeError("no downloadable link")


def download_social_video(url, path, progress):
    """ទាញវីដេអូ TikTok៖ SSSTik មុន រួច yt-dlp រួច tikwm (មិនបង្ហាញតំណដល់អ្នកប្រើ)។"""
    reasons = []
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        try:
            _download_with_ssstik(url, path, progress)
            return
        except Exception as e:
            reasons.append("ssstik: " + (str(e) or type(e).__name__))
    try:
        _download_with_ytdlp(url, path, progress)
        return
    except Exception as e:
        reasons.append("yt-dlp: " + (str(e) or type(e).__name__))
    try:
        _download_with_tikwm(url, path, progress)
        return
    except Exception as e:
        reasons.append("tikwm: " + (str(e) or type(e).__name__))
    raise UserError(" | ".join(reasons))


def _download_with_tikwm(url, path, progress):
    api = "https://www.tikwm.com/api/?" + urllib.parse.urlencode({"url": url, "hd": 1})
    req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    d = (data or {}).get("data") or {}
    play = d.get("hdplay") or d.get("play")
    if not play:
        raise RuntimeError("no video in response: " + str((data or {}).get("msg", ""))[:80])
    if play.startswith("/"):
        play = "https://www.tikwm.com" + play
    download_video(play, path, progress)


def _download_with_ytdlp(url, path, progress):
    try:
        import yt_dlp
    except Exception:
        raise UserError("yt-dlp មិនទាន់ដំឡើង")
    limit = MAX_DOWNLOAD_MB * 1024 * 1024
    base = os.path.splitext(path)[0]

    def hook(d):
        try:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                if total:
                    progress.progress(min(1.0, (d.get("downloaded_bytes") or 0) / total))
        except Exception:
            pass

    opts = {
        "outtmpl": base + ".%(ext)s",
        "format": "best[ext=mp4]/best",
        "max_filesize": limit,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    found = None
    folder = os.path.dirname(base)
    prefix = os.path.basename(base) + "."
    for fn in os.listdir(folder):
        if fn.startswith(prefix):
            found = os.path.join(folder, fn)
            break
    if not found or os.path.getsize(found) < 1000:
        raise UserError(f"ទាញយកវីដេអូមិនបាន ឬវីដេអូធំជាង {MAX_DOWNLOAD_MB}MB។")
    if found != path:
        os.replace(found, path)
    progress.progress(1.0)


def download_video(url, path, progress):
    url = normalize_link(url)
    if is_social_link(url):
        return download_social_video(url, path, progress)
    limit = MAX_DOWNLOAD_MB * 1024 * 1024
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            ctype = (response.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype:
                raise UserError("តំណនេះមិនមែនជាវីដេអូផ្ទាល់ទេ។")
            total = int(response.headers.get("Content-Length") or 0)
            if total > limit:
                raise UserError(f"វីដេអូធំជាង {MAX_DOWNLOAD_MB}MB។")
            done = 0
            with open(path, "wb") as f:
                while True:
                    chunk = response.read(1024 * 1024)
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
        if len(self.item["log"]) > 200:
            del self.item["log"][:100]
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


def build_prompt_original(clip_duration, source_language):
    lang = (f"The speech or singing is in {source_language}. " if source_language
            else "First detect the spoken or sung language. ")
    return (
        lang + "Transcribe it faithfully, word for word, in its ORIGINAL language and original script "
        "with correct spelling and punctuation. Do NOT translate, summarize or paraphrase. "
        "If a word is unclear, choose the most likely word from the context. "
        "Split into natural sentence-level segments, each about 2 to 6 seconds long. "
        "Timestamps are in seconds, measured from the very beginning "
        f"of THIS audio clip (0 to {clip_duration:.1f}). "
        "Each segment must start exactly when its first word is heard and end exactly when its last word ends. "
        "Return ONLY a JSON array. Each item must be an object: "
        '{"start": <seconds as number>, "end": <seconds as number>, "text": "<original-language transcript>"}. '
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


def transcribe_clip(client, models, audio_bytes, mime, clip_duration, source_language, concise, status, original_only=False):
    prompt = build_prompt_original(clip_duration, source_language) if original_only else build_prompt(clip_duration, source_language, concise)
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
                if original_only or ratio >= 0.6:
                    return segments, model, errors
                kept = [s for s in segments if has_khmer(s[2])]
                if kept and (weak is None or len(kept) > len(weak[0])):
                    weak = (kept, model)
                errors.append(f"{model}: មិនមែនអក្សរខ្មែរ")
                break
            if is_empty_json(raw):
                return [], model, []
            plain = fix_khmer(re.sub(r"[\[\]{}\"]", " ", raw))
            if plain and (has_khmer(plain) or original_only):
                return plain_to_segments(plain, clip_duration), model, errors
            errors.append(f"{model}: មិនមានអត្ថបទ")
            break
    if weak:
        return weak[0], weak[1], errors
    return [], None, errors


def transcribe(api_key, audio_path, duration, source_language, status, concise=False, speech=None, original_only=False):
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
        segs, model, errors = transcribe_clip(client, models, data, "audio/flac", end - start, source_language, concise, status, original_only=original_only)
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
    for model in model_order(GROQ_MODELS, None):  # whisper-large-v3 មុនជានិច្ច; turbo ជាបម្រុងពេល large-v3 រវល់
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
    if out and not khmer_dominant(out):
        return None
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
    "(5) Flowing, connected spoken sentences that sound like a real person talking (join clauses naturally, do not chop into tiny fragments); no stiff foreign word order; no repeated words; "
    "no word salad. Write numbers and units the way Khmer speakers say them. Transliterate foreign names naturally. "
    "(6) If a line is garbled or uncertain, keep the closest clear meaning, do not invent dialogue. "
    "(7) A [max N chars] tag is the SPEAKING-TIME budget of the on-screen speaker's mouth (Khmer TTS speaks about 12 characters per second). "
    "Make the dubbed line end when the mouth stops: choose the shortest natural everyday wording, drop filler words, repeated words and pronouns a native would omit, "
    "and keep the same rhythm as the original. NEVER drop a fact, name, number, negation or the emotional point just to fit; if the meaning truly cannot fit, keep the meaning and exceed the budget slightly. Never output the tag. "
    "(8) Every numbered line is ONE complete spoken sentence unit: translate it into exactly one complete, grammatical Khmer "
    "sentence; never merge lines, split lines, or move content between lines. Never leave source-language words untranslated except names. "
    "(9) The output will be read aloud by a TTS voice: use plain natural Khmer, put ។ (or ? !) only at the end of a sentence, and avoid "
    "commas, brackets, quotes, dashes, ellipses, emojis and symbols so the speech flows smoothly without choppy pauses. "
    "(10) If an English meaning is given, use it only as a hint; the original line is the authority for facts, names and numbers. "
    "(11) Translate MEANING, not words: never copy the source sentence structure or idioms literally. Use common everyday Khmer vocabulary "
    "(avoid stiff Pali/Sanskrit-heavy or royal words unless the speaker is a king/monk), drop pronouns that Khmer speakers would omit, "
    "and make sure every sentence is something a native Khmer person would really say and instantly understand. "
    "(12) Double-check every line against the original before answering: a wrong meaning, a missed negation (not, never, មិន, គ្មាន), swapped subject and object, or a wrong number is the worst mistake. "
    "(13) Match the DELIVERY of the original: a short sharp exclamation, shout or one-word reply stays short and punchy in Khmer; a slow, soft, sad or "
    "thoughtful line becomes a calm, flowing Khmer sentence with natural softening particles; a fast angry or excited burst uses clipped, energetic words. "
    "Keep each speaker's pronouns, politeness level and vocabulary consistent across all lines of the video. "
    "Output Khmer script only (no English, no Chinese, no romanization). "
    "Return JSON {\"translations\": [...]} with exactly one item per input, same order."
)


def groq_translate_chunk(api_key, texts, budgets=None, system=None, to_english=False, rotate=False):
    numbered = "\n".join(
        f"{i + 1}. " + (f"[max {budgets[i]} chars] " if budgets and budgets[i] else "") + str(t)
        for i, t in enumerate(texts)
    )
    models = groq_chat_models(api_key)
    _strong = [m for m in models if not any(x in m.lower() for x in ("8b", "instant", "scout", "20b"))]
    models = model_order(_strong or models, "groq")
    if rotate and len(models) > 1:
        _shift = (int(rotate) if not isinstance(rotate, bool) else 1) % len(models)
        models = models[_shift:] + models[:_shift]   # ឱ្យម៉ូដែលផ្សេងពីអ្នកបកដំបូង មកពិនិត្យ
    last = "មិនមានម៉ូដែល"
    for model in models[:8]:
        body = json.dumps({
            "model": model, "temperature": 0.05,
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
    _av = get_available_models(client)
    _av = [m for m in _av if "pro" in m.lower()] + [m for m in _av if "pro" not in m.lower()]
    models = model_order(_av[:5], "gemini")
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
                config=types.GenerateContentConfig(temperature=0.05, response_mime_type="application/json"),
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


REFINE_SYSTEM = (
    "You are a senior Khmer (Cambodian) dubbing editor and bilingual proofreader. For EVERY item first back-translate the KHMER DRAFT into English in your head and compare it with the ORIGINAL: any difference in meaning (an idea added or missing, a lost negation, wrong subject or object, wrong number or name, wrong tense or mood, changed emotion or tone) must be fixed. Each numbered item has an ORIGINAL line, "
    "sometimes an ENGLISH meaning, and a KHMER DRAFT. Check the KHMER DRAFT against the ORIGINAL: fix wrong or missing meaning, "
    "mistranslated words, wrong pronouns/politeness, literal word-for-word phrasing, unnatural or ungrammatical Khmer, and any leftover "
    "foreign words (except names). Rewrite into natural everyday SPOKEN Khmer that a native Phnom Penh speaker would say and instantly understand, "
    "keeping exactly the same facts, names, numbers, emotion and tone. Do not add or remove information. If the draft is already correct and natural, "
    "return it unchanged. Use the neighbouring items as story context (who speaks to whom). One complete sentence per item, same order, "
    "Khmer script only, end with ។ (or ? !), no commas, brackets, quotes, dashes, ellipses, emojis or symbols. "
    "Return JSON {\"translations\": [...]} with exactly one item per input."
)


def refine_khmer(texts, englishes, drafts, gemini_key, groq_key, progress=None, shift=1):
    """ពិនិត្យការបកប្រែខ្មែរម្តងទៀតប្រៀបធៀបនឹងអត្ថបទដើម ហើយកែឱ្យត្រូវន័យ និងស្ទួនភាសាខ្មែរធម្មជាតិ។"""
    n = len(drafts)
    result = list(drafts)
    groups = [list(range(k, min(k + 6, n))) for k in range(0, n, 6)]

    def rows_for(idxs):
        rows = []
        for i in idxs:
            row = f"ORIGINAL: {str(texts[i]).strip()}"
            if englishes[i] and "[unclear]" not in englishes[i]:
                row += f" | ENGLISH: {englishes[i]}"
            row += f" | KHMER DRAFT: {drafts[i]}"
            rows.append(row)
        return rows

    def story_for(idxs):
        prev = [str(drafts[j]) for j in range(max(0, idxs[0] - 4), idxs[0]) if drafts[j]]
        nxt = [str(drafts[j]) for j in range(idxs[-1] + 1, min(n, idxs[-1] + 3)) if drafts[j]]
        s = ""
        if prev:
            s += "PREVIOUS LINES (context only): " + " / ".join(prev) + "\n"
        if nxt:
            s += "NEXT LINES (context only): " + " / ".join(nxt) + "\n"
        return s

    def work(idxs):
        rows = rows_for(idxs)
        story = story_for(idxs)
        if gemini_key:
            try:
                client = make_gemini_client(gemini_key, types.HttpOptions(timeout=TRANSLATE_TIMEOUT_MS))
                avail = get_available_models(client)
                models = [m for m in avail if "pro" in m.lower()] + [m for m in avail if "pro" not in m.lower()]
                models = model_order(models[:5], "gemini-refine")
                numbered = "\n".join(f"{k + 1}. {r}" for k, r in enumerate(rows))
                prompt = REFINE_SYSTEM + "\n\n" + story + "\nITEMS:\n" + numbered
                for model in models:
                    try:
                        resp = client.models.generate_content(
                            model=model, contents=prompt,
                            config=types.GenerateContentConfig(temperature=0.15, response_mime_type="application/json"),
                        )
                        raw = (getattr(resp, "text", "") or "").strip()
                        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
                        data = json.loads(raw)
                        items = data.get("translations") if isinstance(data, dict) else data
                        if isinstance(items, list) and len(items) == len(idxs):
                            model_good("gemini-refine", model)
                            return idxs, [clean_translation(x) for x in items]
                        model_cool(model, "ចំនួនបន្ទាត់មិនត្រូវគ្នា")
                    except Exception as e:
                        model_cool(model, str(e))
            except Exception:
                pass
        if groq_key:
            try:
                res = groq_translate_chunk(groq_key, rows, None, system=REFINE_SYSTEM + " " + story, rotate=shift)
                return idxs, res
            except Exception:
                pass
        return idxs, None

    done = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        for idxs, res in pool.map(work, groups):
            if res:
                for i, r in zip(idxs, res):
                    if r and has_khmer(str(r)) and khmer_dominant(str(r)):
                        result[i] = r
            done += len(idxs)
            if progress:
                try:
                    progress(f"កំពុងកែសម្រួលអត្ថន័យខ្មែរ {done}/{n} ឃ្លា...")
                except Exception:
                    pass
    return result


JUDGE_SYSTEM = (
    "You are the final Khmer (Cambodian) dubbing judge. For each candidate first back-translate it into English in your head and compare it with the ORIGINAL; a candidate that changes, adds or drops any meaning, negation, number, name or emotion loses. Each item has the ORIGINAL line, sometimes an ENGLISH meaning, and two Khmer candidates A and B. "
    "Decide which candidate is MORE FAITHFUL to the original (every fact, name, number, negation, who-does-what-to-whom, tone) AND sounds like natural everyday spoken Khmer. "
    "Then output the best final Khmer line: you may pick A, pick B, or fix/merge them if both have a flaw. Never add information that is not in the original, never drop a negation or a number. "
    "Use neighbouring lines for context (speakers, pronouns, politeness) and keep pronouns consistent. Do not make it longer than needed. "
    "One complete sentence per item, Khmer script only, end with ។ (or ? !), no commas, brackets, quotes, dashes, ellipses, emojis or symbols. "
    "Return JSON {\"translations\": [...]} with exactly one item per input, same order."
)


def judge_khmer(texts, englishes, cand_a, cand_b, gemini_key, groq_key, progress=None, shift=2):
    """ប្រៀបធៀបឃ្លាបកពីរបែប ហើយជ្រើស/កែយកមួយល្អបំផុត (ត្រឹមត្រូវតាមអត្ថន័យដើម និងធម្មជាតិ)។"""
    n = len(cand_a)
    result = list(cand_a)
    groups = [list(range(k, min(k + 6, n))) for k in range(0, n, 6)]

    def work(idxs):
        rows = []
        for i in idxs:
            row = f"ORIGINAL: {str(texts[i]).strip()}"
            if englishes[i] and "[unclear]" not in englishes[i]:
                row += f" | ENGLISH: {englishes[i]}"
            row += f" | A: {cand_a[i]} | B: {cand_b[i]}"
            rows.append(row)
        prev = [str(cand_a[j]) for j in range(max(0, idxs[0] - 3), idxs[0]) if cand_a[j]]
        nxt = [str(cand_a[j]) for j in range(idxs[-1] + 1, min(n, idxs[-1] + 3)) if cand_a[j]]
        ctx = ""
        if prev:
            ctx += "PREVIOUS LINES (context only): " + " / ".join(prev) + " "
        if nxt:
            ctx += "NEXT LINES (context only): " + " / ".join(nxt)
        if gemini_key:
            try:
                res = gemini_lines(gemini_key, JUDGE_SYSTEM + " " + ctx, rows)
                if res:
                    return idxs, res
            except Exception:
                pass
        if groq_key:
            try:
                return idxs, groq_translate_chunk(groq_key, rows, None, system=JUDGE_SYSTEM + " " + ctx, rotate=shift)
            except Exception:
                pass
        return idxs, None

    done = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        for idxs, res in pool.map(work, groups):
            if res:
                for i, r in zip(idxs, res):
                    if r and has_khmer(str(r)) and khmer_dominant(str(r)):
                        result[i] = r
            done += len(idxs)
            if progress:
                try:
                    progress(f"កំពុងជ្រើសការបកប្រែល្អបំផុត {done}/{n} ឃ្លា...")
                except Exception:
                    pass
    return result


def make_synopsis(english, texts, gemini_key, groq_key):
    """សង្ខេបរឿងទាំងមូល (អ្នកណានិយាយទៅអ្នកណា ប្រធានបទ អារម្មណ៍) ជាអង់គ្លេស ដើម្បីជួយបកប្រែឱ្យត្រូវបរិបទ។"""
    body = " ".join((english[i] or str(texts[i])) for i in range(len(texts)))[:7000]
    ask = ("Read this video transcript. In under 120 words of English, state: the topic, who the speakers are and how they relate "
           "(gender, age, formal or casual), the mood, and any recurring names or terms. No translation.\n\n" + body)
    try:
        if gemini_key:
            client = make_gemini_client(gemini_key, types.HttpOptions(timeout=TRANSLATE_TIMEOUT_MS))
            for model in model_order(get_available_models(client)[:5], "gemini")[:2]:
                try:
                    r = client.models.generate_content(model=model, contents=ask)
                    t = (getattr(r, "text", "") or "").strip()
                    if t:
                        return t[:900]
                except Exception:
                    continue
    except Exception:
        pass
    if groq_key:
        try:
            for model in groq_chat_models(groq_key)[:3]:
                try:
                    payload = json.dumps({"model": model, "temperature": 0.1, "messages": [
                        {"role": "user", "content": ask}]}).encode("utf-8")
                    req = urllib.request.Request(GROQ_CHAT_URL, data=payload, method="POST", headers={
                        "Authorization": f"Bearer {groq_first(groq_key)}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
                    with groq_urlopen(req, groq_key, timeout=40) as r:
                        data = json.loads(r.read().decode("utf-8"))
                    t = re.sub(r"<think>.*?</think>", "", data["choices"][0]["message"]["content"], flags=re.S).strip()
                    if t:
                        return t[:900]
                except Exception:
                    continue
        except Exception:
            pass
    return ""


def gemini_lines(api_key, system, rows, temperature=0.15, khmer=True):
    """ផ្ញើបន្ទាត់ទៅ Gemini ហើយទទួលបញ្ជី JSON ត្រឡប់វិញ (ចំនួនស្មើគ្នា)។"""
    client = make_gemini_client(api_key, types.HttpOptions(timeout=TRANSLATE_TIMEOUT_MS))
    avail = get_available_models(client)
    avail = [m for m in avail if "pro" in m.lower()] + [m for m in avail if "pro" not in m.lower()]
    models = model_order(avail[:5], "gemini")
    prompt = system + "\n\nITEMS:\n" + "\n".join(f"{k + 1}. {r}" for k, r in enumerate(rows))
    last = None
    for model in models:
        try:
            resp = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(temperature=temperature, response_mime_type="application/json"),
            )
            raw = (getattr(resp, "text", "") or "").strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
            data = json.loads(raw)
            items = data.get("translations") if isinstance(data, dict) else data
            if isinstance(items, list) and len(items) == len(rows):
                model_good("gemini", model)
                return [(clean_translation(x) if khmer else (str(x).strip() or None)) for x in items]
            last = f"{model}: ចំនួនបន្ទាត់មិនត្រូវគ្នា"
            model_cool(model, last)
        except Exception as e:
            last = f"{model}: {e}"
            model_cool(model, last)
    raise RuntimeError(str(last)[:300])


def llm_lines(rows, system, gemini_key=None, groq_key=None, khmer=True):
    """សាក Gemini មុន បើមិនបានសាក Groq (ឬបញ្ច្រាស់ពេលមានតែមួយ)។ ត្រឡប់ None បើទាំងពីរបរាជ័យ។"""
    if gemini_key:
        try:
            return gemini_lines(gemini_key, system, rows, khmer=khmer)
        except Exception:
            pass
    if groq_key:
        try:
            return groq_translate_chunk(groq_key, rows, None, system=system, to_english=(not khmer), rotate=True)
        except Exception:
            pass
    return None


FIT_SYSTEM = (
    "You are a Khmer dubbing editor doing lip-sync timing. Each numbered item has an ORIGINAL line, the current KHMER line and a MAX number "
    "of characters (the time the speaker's mouth is moving). Rewrite the KHMER line so it is at most MAX characters and still sounds like natural "
    "everyday spoken Khmer: use shorter common words, drop filler words, repeated words and pronouns a native would omit. "
    "Keep every fact, name, number, negation and the emotion. Do not add anything new. If the KHMER line already fits, return it unchanged. "
    "Khmer script only, one sentence per item ending with ។ (or ? !), no commas, brackets, quotes, dashes, ellipses or symbols. "
    "Return JSON {\"translations\": [...]} with exactly one item per input, same order."
)


def fit_to_budget(texts, outs, budgets, gemini_key, groq_key, progress=None):
    """បង្រួមឃ្លាខ្មែរដែលវែងជាងពេលមាត់និយាយ ដោយរក្សាអត្ថន័យ (ឱ្យសំឡេងចប់ត្រូវមាត់)។"""
    n = len(outs)
    result = list(outs)
    over = [i for i in range(n)
            if budgets[i] and len(str(outs[i])) > budgets[i] * 1.6 and len(str(outs[i])) > 30]
    if not over:
        return result
    groups = [over[k:k + 6] for k in range(0, len(over), 6)]

    def work(idxs):
        rows = [f"ORIGINAL: {str(texts[i]).strip()} | KHMER: {outs[i]} | MAX: {budgets[i]}" for i in idxs]
        return idxs, llm_lines(rows, FIT_SYSTEM, gemini_key, groq_key)

    done = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        for idxs, res in pool.map(work, groups):
            if res:
                for i, r in zip(idxs, res):
                    if (r and has_khmer(str(r)) and khmer_dominant(str(r))
                            and len(r) < len(str(outs[i])) and len(r) >= 0.4 * len(str(outs[i]))):
                        result[i] = r
            done += len(idxs)
            if progress:
                try:
                    progress(f"កំពុងតម្រឹមប្រវែងឃ្លាឱ្យត្រូវមាត់ {done}/{len(over)} ឃ្លា...")
                except Exception:
                    pass
    return result


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
            rows_ = [str(texts[i]).strip() for i in idxs]
            try:
                return idxs, groq_translate_chunk(groq_key, rows_, None, system=EN_SYSTEM, to_english=True), None
            except Exception as e:
                # Groq ពេញកូតា/មានបញ្ហា → Gemini ជួយបម្រុង
                if gemini_key:
                    res_ = llm_lines(rows_, EN_SYSTEM, gemini_key, None, khmer=False)
                    if res_:
                        return idxs, res_, None
                return idxs, None, e
        done = 0
        with ThreadPoolExecutor(max_workers=5) as pool:
            for idxs, res, err in pool.map(_en, batches):
                if err:
                    errors.append(f"groq-en: {err}"[:200])
                else:
                    for i, r in zip(idxs, res):
                        english[i] = r
                done += len(idxs)
                _say(f"កំពុងស្ដាប់អត្ថន័យ {done}/{n} ឃ្លា...")
    synopsis = ""
    if n > 2:
        if groq_key:
            synopsis = make_synopsis(english, texts, None, groq_key)
        if not synopsis and gemini_key:
            synopsis = make_synopsis(english, texts, gemini_key, None)
    # ជំហាន ២: Gemini បកជាខ្មែរមុន (ល្អបំផុតសម្រាប់ខ្មែរ) ដោយមានបរិបទមុន/ក្រោយ
    missing = [i for i, o in enumerate(outs) if o is None]
    batches = [missing[k:k + 6] for k in range(0, len(missing), 6)]
    if gemini_key and missing:
        def _km(idxs):
            try:
                prev_ctx = [english[j] or str(texts[j]) for j in range(max(0, idxs[0] - 6), idxs[0])]
                story = " / ".join(str(x).strip() for x in prev_ctx if x) or None
                if synopsis:
                    story = "VIDEO SUMMARY: " + synopsis + " || " + (story or "")
                nxt_ctx = [english[j] or str(texts[j]) for j in range(idxs[-1] + 1, min(n, idxs[-1] + 4))]
                if nxt_ctx:
                    story = (story or "") + " || NEXT LINES (context only): " + " / ".join(str(x).strip() for x in nxt_ctx if x)
                return idxs, gemini_translate_khmer(
                    gemini_key, [str(texts[i]).strip() for i in idxs],
                    [english[i] for i in idxs], [budgets[i] for i in idxs] if budgets else None,
                    story=story,
                ), None
            except Exception as e:
                return idxs, None, e
        done = 0
        with ThreadPoolExecutor(max_workers=5) as pool:
            for idxs, res, err in pool.map(_km, batches):
                if err:
                    errors.append(f"gemini: {err}"[:200])
                else:
                    for i, r in zip(idxs, res):
                        outs[i] = r
                done += len(idxs)
                _say(f"កំពុងបកជាខ្មែរ {done}/{n} ឃ្លា...")
    gem_ok = {i for i, o in enumerate(outs) if o is not None}
    # ជំហាន ២ខ: Groq បកឃ្លាដែល Gemini មិនបាន (បម្រុង)
    missing = [i for i, o in enumerate(outs) if o is None]
    if missing and groq_key:
        _say(f"កំពុងបកជាខ្មែរតាមសាច់រឿង (Groq) 0/{len(missing)} ឃ្លា...")
        groups = [missing[k:k + 8] for k in range(0, len(missing), 8)]
        def _gkm(idxs):
            try:
                prev = [english[j] or str(texts[j]) for j in range(max(0, idxs[0] - 6), idxs[0])]
                story = " / ".join(str(x).strip() for x in prev if x)
                if synopsis:
                    story = "VIDEO SUMMARY: " + synopsis + " || " + story
                lines_ = []
                for i in idxs:
                    row = str(texts[i]).strip()
                    if english[i] and "[unclear]" not in english[i]:
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
        with ThreadPoolExecutor(max_workers=4) as pool:
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
        # ធ្វើស្របគ្នា + ឈប់សាកម៉ាស៊ីនដែលខូចជាប់ៗគ្នា + កំណត់ពេលអតិបរមា ដើម្បីកុំឱ្យរង់ចាំយូរដូចគាំង
        dead = {"gemini": 0, "groq": 0, "google": 0}
        t_end = time.time() + 75
        lock = threading.Lock()

        def _fail(name, msg):
            with lock:
                dead[name] += 1
                errors.append(msg[:200])

        def _one_line(i):
            if time.time() > t_end:
                return i, None
            one = [str(texts[i]).strip()]
            bud = [budgets[i]] if budgets else None
            r = None
            if gemini_key and dead["gemini"] < 2:
                try:
                    r = gemini_translate_khmer(gemini_key, one, [english[i]], bud)[0]
                    dead["gemini"] = 0
                except Exception as e:
                    _fail("gemini", f"gemini-1: {e}")
            if (not r or not has_khmer(str(r))) and groq_key and dead["groq"] < 2 and time.time() < t_end:
                try:
                    r = groq_translate_chunk(groq_key, one, bud)[0]
                    dead["groq"] = 0
                except Exception as e:
                    _fail("groq", f"groq-1: {e}")
            if (not r or not has_khmer(str(r))) and dead["google"] < 2 and time.time() < t_end:
                try:
                    r = clean_translation(google_translate_request(english[i] or one[0], retries=1))
                    dead["google"] = 0
                except Exception as e:
                    _fail("google", f"google-1: {e}")
            return i, r

        with ThreadPoolExecutor(max_workers=4) as pool:
            for i, r in pool.map(_one_line, missing):
                if r and has_khmer(str(r)):
                    outs[i] = r
    # ជំហានកែសម្រួលចុងក្រោយ: ពិនិត្យអត្ថន័យខ្មែរប្រៀបនឹងអត្ថបទដើម
    # ពិនិត្យ ២ ជុំ ដោយម៉ូដែលផ្សេងគ្នា លើគ្រប់ឃ្លា (ជុំទី២ ពិនិត្យអត្ថន័យ និងភាពស៊ីសង្វាក់ម្តងទៀត)
    allidx = list(range(n))
    if allidx and (groq_key or gemini_key) and all(o and has_khmer(str(o)) for o in outs):
        try:
            cand_a = list(outs)
            cand_b = refine_khmer([texts[i] for i in allidx], [english[i] for i in allidx], cand_a,
                                  gemini_key, groq_key, progress=progress, shift=1)
            cand_b = [b or a for a, b in zip(cand_a, cand_b)]
            outs = judge_khmer([texts[i] for i in allidx], [english[i] for i in allidx], cand_a, cand_b,
                               gemini_key, groq_key, progress=progress, shift=2)
        except Exception as e:
            errors.append(f"refine/judge: {e}"[:200])
    # តម្រឹមប្រវែងឃ្លាខ្មែរឱ្យសមនឹងពេលមាត់តួអង្គនិយាយ (lip-sync)
    if budgets and all(o and has_khmer(str(o)) for o in outs):
        try:
            outs = fit_to_budget(texts, outs, budgets, gemini_key, groq_key, progress=progress)
        except Exception as e:
            errors.append(f"fit: {e}"[:200])
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

    with ThreadPoolExecutor(max_workers=8) as pool:
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


KHMER_CPS = 14.0   # តួអក្សរខ្មែរដែលសំឡេង AI អានបានក្នុង ១ វិនាទី (ប្រហែល)


def lip_budgets(segs):
    """ប្រវែងអក្សរខ្មែរអតិបរមា តាមពេលដែលតួអង្គបើកមាត់និយាយ (ដើម្បីឱ្យសំឡេងចប់ត្រូវមាត់)។"""
    out = []
    for s_, e_, _t in segs:
        dur = max(0.0, float(e_) - float(s_))
        out.append(max(10, int(dur * KHMER_CPS)))
    return out


def merge_for_translate(segs, max_chars=200, max_gap=1.0, max_len=11.0):
    """បញ្ចូលបំណែក Whisper ដែលដាច់កណ្តាលប្រយោគ ឱ្យទៅជាប្រយោគពេញ មុនបកប្រែ
    (បកទាំងប្រយោគ ត្រឹមត្រូវជាងបកបំណែកខ្លីៗ)។"""
    strong_end = ".!?។…。！？"
    out = []
    for s, e, t in segs:
        t = str(t).strip()
        if not t:
            continue
        if out:
            ps, pe, pt = out[-1]
            last = pt.rstrip()[-1:]
            ended = last in strong_end
            tiny_prev = len(pt.strip()) < 14           # បំណែកខ្លីពេក មិនអាចបកឱ្យត្រូវ
            tiny_cur = len(t) < 8
            starts_lower = t[:1].islower()              # ចាប់ផ្តើមអក្សរតូច = បន្តប្រយោគមុន
            cont = (not ended) or tiny_prev or tiny_cur or starts_lower
            gap_ok = (s - pe) <= (max_gap if not ended else 0.5)
            if cont and gap_ok and len(pt) + len(t) + 1 <= max_chars and e - ps <= max_len:
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
        if float(sg.get("compression_ratio", 0) or 0) > 2.4:
            continue
        try:
            s = float(sg.get("start", 0))
            e = float(sg.get("end", 0))
        except Exception:
            continue
        s = min(max(0.0, s), duration)
        e = min(max(e, s + 0.4), duration + 0.5)
        if keep and keep[-1][2].strip().lower() == text.strip().lower():
            keep[-1] = (keep[-1][0], max(keep[-1][1], e), keep[-1][2])
            continue
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
        keep = merge_for_translate(keep)
        # បកប្រែតាមប្រវែងឃ្លាចិន៖ ឃ្លាខ្លីអាចពន្យល់ខ្មែរបន្ថែម,
        # ឃ្លាវែងត្រូវសង្ខេបខ្មែរឱ្យខ្លី ដើម្បីសមនឹងចន្លោះសំឡេង។
        # ប្រវែងគោល (soft hint): ~១០ តួអក្សរខ្មែរ/វិនាទី តាមពេលមាត់និយាយ ឱ្យស្របចង្វាក់ lip-sync
        # (prompt ហាមកាត់អត្ថន័យ ដូច្នេះនេះគ្រាន់តែជាការណែនាំ)
        budgets = lip_budgets(keep)  # ប្រវែងអក្សរតាមពេលមាត់និយាយ ឱ្យសំឡេងចប់ត្រូវមាត់
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


def transcribe_gemini_text(gemini_key, groq_key, audio_path, duration, source_language, status, speech=None, keep_failed=False):
    """Gemini ទាញអត្ថបទដើមពីសំឡេងតែប៉ុណ្ណោះ (មិនបកប្រែ)។ ការបកជាខ្មែរធ្វើដោយ Groq/Google។"""
    if source_language == "Khmer":
        return transcribe(gemini_key, audio_path, duration, source_language, status, concise=False, speech=speech)
    raw, model, failed = transcribe(gemini_key, audio_path, duration, source_language, status, speech=speech, original_only=True)
    if khmer_ratio(raw) >= 0.6:
        return raw, f"Gemini {model}", failed
    status.write("៣/៤ Gemini ទាញអត្ថបទរួច កំពុងបកប្រែជាភាសាខ្មែរ...")
    keep = merge_for_translate([(a, b, t) for a, b, t in raw if str(t).strip()])
    outs, errs = translate_texts([t for _, _, t in keep], groq_key, lip_budgets(keep), gemini_key, progress=lambda m: status.write("៣/៤ " + m))
    segs = []
    for (a, b, orig), out in zip(keep, outs):
        if out:
            segs.append((a, b, out))
        elif keep_failed:
            segs.append((a, b, "⚠️ " + str(orig)))
            failed += 1
        else:
            failed += 1
    if not keep_failed and (failed > 0 or len(segs) != len(keep)):
        reason = " | ".join(errs[:3]) or "មិនបានអត្ថបទខ្មែរសម្រាប់ឃ្លាខ្លះ"
        raise RuntimeError(f"ការបកប្រែមិនគ្រប់ឃ្លា (ទាញបាន {len(keep)} បកបាន {len(segs)}) មូលហេតុ: {reason}")
    if not segs:
        raise UserError("រកមិនឃើញអត្ថបទខ្មែរក្នុងសំឡេងនេះទេ។")
    segs.sort(key=lambda x: x[0])
    return segs, f"Gemini {model} (ទាញអត្ថបទ) + Translate", failed


def tts_segment(text, voice, path, prosody=None):
    async def _go(p):
        # Natural, slightly slower Khmer delivery by default.
        # Emotion-specific prosody still takes precedence when supplied.
        kw = {"rate": "-4%"}
        if p:
            kw = {"rate": p["rate"], "volume": p["volume"], "pitch": p["pitch"]}
        await edge_tts.Communicate(tts_clean(text), voice, **kw).save(path)

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
MIN_TURN = 2.0


def load_pcm(path):
    import numpy as np
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [exe, "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    raw = result.stdout
    result = None
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    raw = None
    data /= 32768.0
    return data


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
        parts = merge_short_runs(parts, 2.0)
        if len(parts) == 1:
            out.append((s, e, text, voice_of[parts[0][2]]))
            continue
        shares = [p[1] - p[0] for p in parts]
        pieces = split_text_by_shares(text, shares)
        for (a, b, g), piece in zip(parts, pieces):
            if piece:
                out.append((a, b, piece, voice_of[g]))
    return out


def dominant_voice(a, b, runs, default_voice):
    """ជ្រើសសំឡេងតែមួយក្នុងមួយឃ្លា តាមអ្នកនិយាយដែលនិយាយយូរជាងគេ (កុំកាត់ប្រយោគ)។"""
    tot = {"M": 0.0, "F": 0.0}
    for rs, re_, g in runs:
        ov = min(b, re_) - max(a, rs)
        if ov > 0 and g in tot:
            tot[g] += ov
    if tot["M"] <= 0 and tot["F"] <= 0:
        return default_voice
    return VOICE_MALE if tot["M"] >= tot["F"] else VOICE_FEMALE


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


EMO_LABELS = ["neutral", "happy", "excited", "angry", "sad", "fear", "whisper",
              "shout", "tender", "surprised", "worried", "sarcastic"]
EMO_HIGH = ("happy", "excited", "angry", "fear", "shout", "surprised")
EMO_LOW = ("sad", "whisper", "tender", "worried")

# (rate %, pitch Hz, volume %) ត្រូវគុណនឹងកម្លាំងអារម្មណ៍ (intensity)
EMO_PRESETS = {
    "neutral": (0, 0, 0),
    "happy": (8, 12, 6),
    "excited": (14, 18, 14),
    "angry": (12, 6, 28),
    "sad": (-16, -12, -20),
    "fear": (12, 18, -6),
    "whisper": (-10, -5, -45),
    "shout": (10, 10, 40),
    "tender": (-10, -4, -18),
    "surprised": (10, 20, 12),
    "worried": (-4, 6, -10),
    "sarcastic": (-8, 4, 0),
}

EMO_NAMES = {
    "neutral": "😐 ធម្មតា", "happy": "😊 សប្បាយ", "excited": "🤩 រំភើប",
    "angry": "😠 ខឹង", "sad": "😢 ក្រៀមក្រំ", "fear": "😨 ភ័យ",
    "whisper": "🤫 ខ្សឹប", "shout": "📢 ស្រែក", "tender": "🥰 ទន់ភ្លន់",
    "surprised": "😲 ភ្ញាក់ផ្អើល", "worried": "😟 បារម្ភ", "sarcastic": "😏 ចំអក",
}

EMO_SYSTEM = (
    "You are a film dubbing director. Each numbered Khmer line is spoken by a character. Decide the emotion the voice actor must PERFORM "
    "for that line so the dubbed voice sounds like a real, feeling human, not a reading machine. Use the neighbouring/context lines to understand "
    "the scene, who is speaking to whom and the mood. Allowed labels ONLY: neutral, happy, excited, angry, sad, fear, whisper, shout, tender, "
    "surprised, worried, sarcastic. Judge from the meaning, word choice, particles, punctuation (! ? ...), insults, pleading, crying, laughing, "
    "teasing, commands and exclamations. Do NOT default to neutral: use neutral only when the line is truly flat or purely informational. "
    "Also give intensity from 0.2 (slight) to 1.0 (very strong). "
    "Return JSON {\"emotions\": [{\"label\": \"angry\", \"intensity\": 0.8}, ...]} with exactly the same number of items, in the same order."
)


def norm_emotion(x):
    x = str(x or "").strip().lower()
    return x if x in EMO_LABELS else "neutral"


def parse_emo_item(x):
    """ទទួលទាំង {"label","intensity"} និងអក្សរសុទ្ធ → (label, intensity)។"""
    if isinstance(x, dict):
        lab = norm_emotion(x.get("label") or x.get("emotion"))
        try:
            inten = float(x.get("intensity", 0.7))
        except Exception:
            inten = 0.7
        return lab, max(0.2, min(1.0, inten))
    return norm_emotion(x), 0.7


def groq_emotion_chunk(api_key, texts, context=""):
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    user = (("CONTEXT (previous lines, do NOT label them): " + context + "\n\n") if context else "") + "LINES TO LABEL:\n" + numbered
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
                {"role": "user", "content": user},
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
                    return [parse_emo_item(x) for x in items]
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
    avail = get_available_models(client)
    avail = [m for m in avail if "pro" in m.lower()] + [m for m in avail if "pro" not in m.lower()]
    models = avail[:3]
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    prompt = EMO_SYSTEM + "\n\nLINES TO LABEL:\n" + numbered
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
                return [parse_emo_item(x) for x in items]
        except Exception as e:
            last = e
    raise RuntimeError(f"Gemini emotion: {last}")


def label_emotions(texts, groq_key, gemini_key):
    """ត្រឡប់បញ្ជី (label, intensity) ឬ None។ ប្រើ Gemini មុន (យល់ខ្មែរល្អជាង) រួច Groq ជាបម្រុង។"""
    if not texts:
        return None
    if gemini_key:
        try:
            out = gemini_emotion_labels(gemini_key, texts)
            if out and len(out) == len(texts):
                return out
        except Exception:
            pass
    if groq_key:
        out = []
        ok = True
        for k in range(0, len(texts), 25):
            ctx = " / ".join(str(t) for t in texts[max(0, k - 3):k])
            try:
                out.extend(groq_emotion_chunk(groq_key, texts[k:k + 25], ctx))
            except Exception:
                ok = False
                break
            time.sleep(0.5)
        if ok and len(out) == len(texts):
            return out
    return None


def combine_emotion(text_label, arousal, text_inten=None):
    """ผสมอารម្មណ៍ពីអត្ថបទ (AI) និងកម្លាំងសំឡេងដើម (arousal)។"""
    ti = 0.7 if text_inten is None else max(0.2, min(1.0, float(text_inten)))
    base = 0.4 + 1.0 * ti            # 0.6 .. 1.4
    if text_label in EMO_HIGH:
        return text_label, max(0.4, min(1.7, base + 0.5 * arousal))
    if text_label in EMO_LOW:
        return text_label, max(0.4, min(1.7, base - 0.3 * arousal))
    if text_label == "sarcastic":
        return text_label, max(0.5, min(1.3, base))
    if arousal > 0.3:
        return "excited", min(1.4, 0.5 + (arousal - 0.3) * 1.1)
    if arousal < -0.3:
        return "sad", min(1.4, 0.5 + (-arousal - 0.3) * 1.1)
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
        text_label, text_inten = (labels[i] if labels else (None, None))
        result.append(combine_emotion(text_label, arousal, text_inten))
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
    rate = int(max(-22, min(22, rate * k)))
    pitch = int(max(-16, min(16, pitch * k * 0.8))) if use_pitch else 0
    vol = int(max(-35, min(30, vol * k * 0.7)))
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


def merge_for_dub(segments, max_chars=260, max_gap=1.6, max_len=18.0):
    """បញ្ចូលតែបំណែកខ្លីៗដែលដាច់កណ្តាលប្រយោគ ដើម្បីអានរលូន ហើយនៅជិតម៉ោងសំឡេងដើម"""
    out = []
    for s, e, t in segments:
        t = fix_khmer(t)
        if not t:
            continue
        if out:
            ps, pe, pt = out[-1]
            ended = pt.rstrip()[-1:] in "។.!?…"
            tiny_prev = len(pt) < 18
            tiny_cur = len(t) < 10
            if ((not ended) or tiny_prev or tiny_cur) and (s - pe) <= max_gap \
                    and len(pt) + len(t) + 1 <= max_chars and e - ps <= max_len:
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


def condense_for_slot(text, slot, client, model, groq_key):
    """បង្រួមប្រយោគខ្មែរឱ្យខ្លី (រក្សាអត្ថន័យ) ពេលវែងជាងមាត់និយាយច្រើនពេក។ បើមិនបានលទ្ធផលល្អ ត្រឡប់អត្ថបទដើម។"""
    try:
        if client is not None and model:
            out = shorten_khmer(client, model, text, slot)
            if out and out != text and has_khmer(out) and len(out) < len(text):
                return out
        if groq_key:
            out = shorten_groq(groq_key, text, slot)
            if out and out != text and has_khmer(out) and len(out) < len(text):
                return out
    except Exception:
        pass
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
        slot0 = max(0.6, min(next_s_ - 0.08, e_ + (0.4 if tight else 1.0)) - s_)
        path_ = os.path.join(folder, f"tts_{i}.mp3")
        try:
            if not tts_retry(t_, voices_[i], path_, pros[i]):
                return None
            d_, _, _ = probe_media(path_)
            # តម្រឹមល្បឿនអាន ឱ្យចប់ត្រូវពេលមាត់តួអង្គ (មិនលឿនពេក មិនយឺតពេក)
            mouth_ = max(0.5, e_ - s_)
            lo_ = min(mouth_ * 0.88, slot0)
            hi_ = slot0

            def _miss(x):
                return max(0.0, x - hi_ * 1.03) + max(0.0, lo_ - x)

            def _fit_rate(text_, d_cur, p_cur):
                for _k in range(3):
                    if _miss(d_cur) <= 0:
                        break
                    try:
                        try:
                            base_ = int(str((p_cur or {}).get("rate", "-4%")).replace("%", "").replace("+", ""))
                        except Exception:
                            base_ = -4
                        goal_ = hi_ * 0.97 if d_cur > hi_ * 1.03 else min(hi_, mouth_ * 0.95)
                        mult_ = (1.0 + base_ / 100.0) * (d_cur / max(0.3, goal_))
                        new_rate = int(round(max(-30, min(60, (mult_ - 1.0) * 100))))
                        if new_rate == base_:
                            break
                        p2_ = {"rate": f"{new_rate:+d}%",
                               "volume": (p_cur or {}).get("volume", "+0%"),
                               "pitch": (p_cur or {}).get("pitch", "+0Hz")}
                        path2_ = os.path.join(folder, f"tts_{i}_f.mp3")
                        if not tts_retry(text_, voices_[i], path2_, p2_, tries=2):
                            break
                        d2_, _, _ = probe_media(path2_)
                        if _miss(d2_) < _miss(d_cur):
                            shutil.move(path2_, path_)
                            d_cur, p_cur = d2_, p2_
                        else:
                            break
                    except Exception:
                        break
                return d_cur, p_cur

            p_cur_ = pros[i]
            if not clone_voice:
                d_, p_cur_ = _fit_rate(t_, d_, p_cur_)
            # នៅតែវែងពេក៖ បង្រួមឃ្លាបន្តិច (រក្សាអត្ថន័យ) រួចតម្រឹមល្បឿនម្តងទៀត
            if (not clone_voice) and d_ > slot0 * 1.6 and len(t_) > 30:
                short_ = condense_for_slot(t_, slot0, client, model, groq_key)
                if short_ != t_:
                    path3_ = os.path.join(folder, f"tts_{i}_s.mp3")
                    if tts_retry(short_, voices_[i], path3_, p_cur_, tries=2):
                        d3_, _, _ = probe_media(path3_)
                        if d3_ < d_ * 0.9:
                            shutil.move(path3_, path_)
                            d_ = d3_
                            d_, p_cur_ = _fit_rate(short_, d_, p_cur_)
            # Preserve the complete translated sentence otherwise.
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
        prev_end = segments[i - 1][1] if i > 0 else 0.0
        lead = max(0.0, min(0.15, s - prev_end - 0.05))   # ចាប់ផ្តើមមុនបន្តិច តាមការបើកមាត់
        start = max(s + offset - lead, 0.0)
        if start >= duration - 0.3:
            break
        slot = max(0.6, min(next_s - 0.04, e + (0.4 if tight else 1.2)) - start)
        # Fit the complete generated sentence into its available slot when
        # possible. atempo > 1 speeds up; < 1 slows down. Avoid extreme rates
        # that make Khmer hard to understand.
        # Previous line still talking? Start right after it, never overlap.
        if start < cursor:
            start = cursor
            slot = max(0.6, min(next_s - 0.04, e + 1.2) - start)
        # Too long for its slot -> speed up (max 1.35x) so it never talks over the next line.
        speed = d / slot if d > slot else 1.0
        speed = min(1.4, max(1.0, speed))
        # តួអង្គនិយាយយឺត/បន្ថយសំឡេង៖ បើសំឡេង AI ខ្លីជាងពេលមាត់ ច្រើន ធ្វើឱ្យយឺតបន្តិច (មិនឱ្យសំឡេងចប់មុនមាត់)
        mouth = max(0.5, e - s)
        if d < mouth * 0.82 and speed == 1.0:
            speed = max(0.85, d / (mouth * 0.92))
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
        filters.append(f"[{n}:a]{chain},afade=t=in:d=0.03,adelay={delay}:all=1[a{n}]")
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
        parts.append(f"scale=w='if(gt(iw,ih),-2,min({max_side},iw))':" f"h='if(gt(iw,ih),min({max_side},ih),-2)':flags=fast_bilinear")
    if subs:
        parts.append("ass=filename=captions.ass:fontsdir=.")
    parts.append("format=yuv420p")
    return ",".join(parts)



# =====================================================================
#  Logo + Blur (បិទបាំង) លើវីដេអូ
# =====================================================================
def out_dims(w, h, max_side):
    """ទំហំវីដេអូលទ្ធផល ក្រោយ scale (ដូចក្នុង build_video_filter)។"""
    if not max_side or max_side <= 0:
        return w, h

    def ev(x):
        return max(2, int(round(x / 2.0)) * 2)

    if w > h:
        h2 = min(max_side, h)
        return ev(w * h2 / float(h)), h2
    w2 = min(max_side, w)
    return w2, ev(h * w2 / float(w))


def prepare_fx(folder, fx, vid_w, vid_h, max_side):
    """រៀបចំ logo.png (ទំហំ/ពណ៌/ភាពថ្លា) និងបញ្ជី blur សម្រាប់ ffmpeg។"""
    if not fx:
        return None
    spec = {"blurs": [], "logo": None}
    for b in fx.get("blurs") or []:
        w = max(0.02, min(1.0, float(b["w"])))
        h = max(0.02, min(1.0, float(b["h"])))
        x = max(0.0, min(1.0 - w, float(b["x"])))
        y = max(0.0, min(1.0 - h, float(b["y"])))
        spec["blurs"].append({"x": x, "y": y, "w": w, "h": h,
                              "sigma": max(2, int(b.get("sigma", 25))),
                              "t0": b.get("t0"), "t1": b.get("t1")})
    if fx.get("logo_bytes"):
        try:
            from PIL import Image
            out_w, _out_h = out_dims(vid_w, vid_h, max_side)
            im = Image.open(io.BytesIO(fx["logo_bytes"])).convert("RGBA")
            tw = max(8, int(out_w * float(fx.get("logo_size", 15)) / 100.0))
            th = max(8, int(im.height * tw / float(im.width)))
            im = im.resize((tw, th), Image.LANCZOS)
            r, g, b_, a = im.split()
            if fx.get("logo_color"):
                solid = Image.new("RGBA", im.size, fx["logo_color"])
                r, g, b_, _ = solid.split()
            op = max(0.05, min(1.0, float(fx.get("logo_opacity", 1.0))))
            a = a.point(lambda v: int(v * op))
            Image.merge("RGBA", (r, g, b_, a)).save(os.path.join(folder, "logo.png"))
            spec["logo"] = {"x": max(0.0, min(1.0, float(fx.get("logo_x", 0.9)))),
                            "y": max(0.0, min(1.0, float(fx.get("logo_y", 0.1))))}
        except Exception:
            spec["logo"] = None
    if not spec["blurs"] and not spec["logo"]:
        return None
    return spec


def video_filter_args(max_side, subs, dub, spec, vid_w=None, vid_h=None):
    """ត្រឡប់ (input បន្ថែម, ជម្រើស filter+map) សម្រាប់ ffmpeg។"""
    if not spec:
        a = ["-vf", build_video_filter(max_side, subs)]
        if dub:
            a += ["-map", "0:v:0", "-map", "1:a:0"]
        return [], a
    nodes = []
    cur = "[0:v]"
    cnt = [0]

    def nxt():
        cnt[0] += 1
        return f"[v{cnt[0]}]"

    if max_side and max_side > 0:
        out = nxt()
        nodes.append(
            f"{cur}scale=w='if(gt(iw,ih),-2,min({max_side},iw))':"
            f"h='if(gt(iw,ih),min({max_side},ih),-2)':flags=fast_bilinear{out}")
        cur = out
    for i, b in enumerate(spec["blurs"]):
        out = nxt()
        nodes.append(f"{cur}split=2[ba{i}][bb{i}]")
        nodes.append(
            f"[bb{i}]crop=w='trunc(iw*{b['w']:.4f}/2)*2':h='trunc(ih*{b['h']:.4f}/2)*2':"
            f"x='trunc(iw*{b['x']:.4f}/2)*2':y='trunc(ih*{b['y']:.4f}/2)*2',"
            f"gblur=sigma={b['sigma']}:steps=2[bc{i}]")
        en = ""
        if b.get("t0") is not None and b.get("t1") is not None:
            en = f":enable='between(t,{float(b['t0']):.2f},{float(b['t1']):.2f})'"
        nodes.append(
            f"[ba{i}][bc{i}]overlay=x='trunc(W*{b['x']:.4f}/2)*2':y='trunc(H*{b['y']:.4f}/2)*2'{en}{out}")
        cur = out
    extra_in = []
    if spec.get("logo"):
        lg = spec["logo"]
        idx = 2 if dub else 1
        extra_in = ["-i", "logo.png"]
        out = nxt()
        nodes.append(
            f"{cur}[{idx}:v]overlay=x='max(0,min(W-w,W*{lg['x']:.4f}-w/2))':"
            f"y='max(0,min(H-h,H*{lg['y']:.4f}-h/2))'{out}")
        cur = out
    if subs:
        out = nxt()
        nodes.append(f"{cur}ass=filename=captions.ass:fontsdir=.{out}")
        cur = out
    nodes.append(f"{cur}format=yuv420p[vout]")
    maps = ["-map", "[vout]"] + (["-map", "1:a:0"] if dub else ["-map", "0:a:0?"])
    return extra_in, ["-filter_complex", ";".join(nodes)] + maps


def render_with_fonts(folder, fonts, captions, font_size, outline_size,
                      color, vid_w, vid_h, quality, status, dub=False, style=None, subs=True, fx=None):
    ass_path = os.path.join(folder, "captions.ass")
    output_path = os.path.join(folder, "output.mp4")
    max_side, crf, preset = quality
    fx_spec = prepare_fx(folder, fx, vid_w, vid_h, max_side)
    if not subs:
        args = ["-i", "input.mp4"]
        if dub:
            args += ["-i", "dub.wav"]
        fast_copy = not (max_side and max_side > 0) and not fx_spec
        if not fast_copy:
            extra_in, vf_args = video_filter_args(max_side, False, dub, fx_spec, vid_w, vid_h)
            args += extra_in + vf_args
        elif dub:
            args += ["-map", "0:v:0", "-map", "1:a:0"]
        if fast_copy:
            args += ["-c:v", "copy"]
        else:
            args += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                     "-maxrate", RATE_CAP.get(max_side, RATE_CAP[0])[0], "-bufsize", RATE_CAP.get(max_side, RATE_CAP[0])[1]]
        args += ["-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "output.mp4"]
        log = run_ffmpeg(args, cwd=folder)
        return output_path, "-", log, ["មិនដាក់អក្សរ"]
    conf_env = make_fontconfig_env(folder)
    plan = [(0, False), (0, True)]
    plan += [(i, True) for i in range(1, len(fonts))]
    attempts = []
    chosen = None
    fallback = None
    # ជំហាន ១: សាក Font លើក្លីបខ្លី ១.៥ វិនាទី (លឿន) ជំនួសឱ្យ render ទាំងមូលច្រើនដង
    for font_index, use_conf in plan:
        font_path, default_name = fonts[font_index]
        family = get_font_family(font_path, default_name)
        keys = [family.lower(), default_name.lower()]
        write_ass(ass_path, [(0.0, 3.0, "ខ្ញុំស្រឡាញ់អ្នក")], family, font_size, outline_size, color, vid_w, vid_h, style)
        try:
            log = run_ffmpeg(
                ["-i", "input.mp4", "-t", "1.5", "-an",
                 "-vf", "ass=filename=captions.ass:fontsdir=.,format=yuv420p",
                 "-c:v", "libx264", "-preset", "ultrafast", "-crf", "40", "font_test.mp4"],
                cwd=folder, verbose=True, env=conf_env if use_conf else None)
        except RuntimeError:
            attempts.append(f"{family} conf={use_conf}: ffmpeg error")
            continue
        ok = font_was_used(log, keys)
        attempts.append(f"{family} conf={use_conf}: ok={ok}")
        if fallback is None:
            fallback = (font_index, use_conf, family, log)
        if ok:
            chosen = (font_index, use_conf, family, log)
            break
        dbg(status, f"Font {family} មិនត្រូវបានប្រើ កំពុងសាកវិធីផ្សេង...")
    if chosen is None:
        chosen = fallback
    if chosen is None:
        raise RuntimeError("Render មិនបាន។\n" + "\n".join(attempts))
    font_index, use_conf, family, test_log = chosen
    # ជំហាន ២: render ពេញមួយដងតែប៉ុណ្ណោះ ជាមួយ Font ដែលបានជ្រើស
    write_ass(ass_path, captions, family, font_size, outline_size, color, vid_w, vid_h, style)
    args = ["-i", "input.mp4"]
    if dub:
        args += ["-i", "dub.wav"]
    extra_in, vf_args = video_filter_args(max_side, True, dub, fx_spec, vid_w, vid_h)
    args += extra_in + vf_args
    args += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
             "-maxrate", RATE_CAP.get(max_side, RATE_CAP[0])[0], "-bufsize", RATE_CAP.get(max_side, RATE_CAP[0])[1],
             "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "output.mp4"]
    try:
        total_dur = probe_media(os.path.join(folder, "input.mp4"))[0]
    except Exception:
        total_dur = 0.0
    item_ = getattr(status, "item", None)

    def _on_pct(frac, elapsed):
        if item_ is None:
            return
        item_["pct"] = max(item_.get("pct", 0.0), 0.82 + 0.17 * frac)
        msg = f"៤/៤ កំពុងដាក់អក្សរចូលវីដេអូ... {int(frac * 100)}%"
        if frac > 0.03:
            msg += f" · នៅសល់ប្រហែល {int(elapsed / frac - elapsed)} វិនាទី"
        item_["stage"] = msg

    run_ffmpeg_progress(args, cwd=folder, env=conf_env if use_conf else None, total=total_dur, on_pct=_on_pct)
    return output_path, family, test_log, attempts


def new_item(name, path=None, url=None):
    return {
        "name": name, "path": path, "url": url, "state": "queued",
        "stage": "ក្នុងជួររង់ចាំ...", "pct": 0.0, "warn": [], "log": [],
        "video_path": None, "captions": [], "voice_lines": [], "error": None,
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
        self.turn = 0
        self.turn_cv = threading.Condition()
    def running(self):
        return any(it["state"] in ("queued", "running", "review") for it in self.items)
    def reviewing(self):
        return any(it["state"] == "review" for it in self.items)


def engine_name(engine):
    return "គម្រោង VIP" if engine == "free" else "Gemini"


def run_worker(job, item, settings, fonts_data):
    rep = Reporter(item)
    item["stage"] = "ក្នុងជួររង់ចាំ..."
    _seq = item.get("seq")
    if _seq is not None:
        # ចាប់ផ្តើមតាមលំដាប់លំដោយ: ផ្នែកទី១ មុន រួចផ្នែកទី២ ...
        with job.turn_cv:
            while job.turn != _seq:
                job.turn_cv.wait(timeout=5)
    _PIPELINE_SLOTS.acquire()
    if _seq is not None:
        with job.turn_cv:
            job.turn = _seq + 1
            job.turn_cv.notify_all()
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
            analysis_pool = None
            analysis_future = None
            if (settings["dub_on"] and duration <= 600
                    and (settings["auto_gender"] or settings["voice_match"] or settings["emotion"] or settings.get("timbre"))):
                analysis_pool = ThreadPoolExecutor(max_workers=1)
                def _analyze():
                    pcm_ = load_pcm(master_path)
                    return pcm_, pitch_track(pcm_)
                analysis_future = analysis_pool.submit(_analyze)
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
                        segments, used_model, failed_chunks = transcribe_free(settings["groq_key"], audio_path, duration, settings["language"], rep, speech=speech, dub=settings["dub_on"], gemini_key=settings["gemini_key"], keep_failed=False)
                    else:
                        segments, used_model, failed_chunks = transcribe_gemini_text(settings["gemini_key"], settings["groq_key"], master_path, duration, settings["language"], rep, speech=speech)
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
            captions, sync_mode = build_captions(segments, duration)
            if not captions:
                raise UserError("រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូនេះទេ។")
            dub_ok = False
            if settings["dub_on"]:
                item["pct"] = 0.6
                rep.write("🎙 កំពុងបង្កើតសំឡេងខ្មែរ...")
                try:
                    client = None
                    dub_model = used_model
                    if settings["gemini_key"]:
                        try:
                            client = make_gemini_client(settings["gemini_key"], types.HttpOptions(timeout=TRANSLATE_TIMEOUT_MS))
                            _ms = model_order(get_available_models(client)[:5], "gemini")
                            dub_model = _ms[0] if _ms else None
                        except Exception:
                            client = None
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
                            if analysis_future is not None:
                                pcm, tracks = analysis_future.result()
                            else:
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
                                try:
                                    runs_, _info = gender_timeline(pcm, duration, settings["voice"], tracks=tracks)
                                    if runs_ is not None:
                                        seg_voices = [dominant_voice(a_, b_, runs_, settings["voice"]) for a_, b_, _t in dub_segments]
                                        voice_notes = voice_notes + [f"🗣 ប្រុស {sum(1 for v_ in seg_voices if v_ == VOICE_MALE)} / ស្រី {sum(1 for v_ in seg_voices if v_ == VOICE_FEMALE)} ឃ្លា"]
                                except Exception:
                                    seg_voices = None
                                    runs_ = None
                            if settings["voice_match"]:
                                targets = compute_targets(dub_segments, seg_voices, pitch_inf, runs_)
                            pcm = None
                            ref_pcm = None
                            tracks = None
                            gc.collect()
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
                        dub_ok = make_dub(folder, dub_segments, settings["voice"], duration, settings["keep_bg"], client, dub_model, seg_voices=seg_voices, targets=targets, notes=match_notes, emotions=emotions, groq_key=settings["groq_key"], clone_voice=clone_voice, eleven_key=settings.get("eleven_key"), ref_bands=ref_bands, offset=0.0, tight=True)
                    finally:
                        if clone_voice:
                            eleven_delete_voice(settings["eleven_key"], clone_voice)
                    item["voice_lines"] = match_notes + voice_notes
                except Exception:
                    dub_ok = False
                if not dub_ok:
                    item["warn"].append("បង្កើតសំឡេងអានមិនបានទេ។ វីដេអូមានតែអក្សរ។")
            if analysis_pool is not None:
                analysis_pool.shutdown(wait=False)
                analysis_future = None
            item["pct"] = 0.75
            rep.write("៤/៤ កំពុងរង់ចាំដាក់អក្សរចូលវីដេអូ...")
            with job.render_slots:
                item["pct"] = 0.82
                rep.write("៤/៤ កំពុងដាក់អក្សរចូលវីដេអូ...")
                out_path, used_font, ffmpeg_log, attempts = render_with_fonts(folder, fonts, captions, settings["font_size"], settings["outline_size"], settings["color"], vid_w, vid_h, settings["quality"], rep, dub=dub_ok, style=settings["style"], subs=settings["sub_on"], fx=settings.get("fx"))
            final_path = os.path.join(job.folder, f"out_{uuid.uuid4().hex[:8]}.mp4")
            shutil.move(out_path, final_path)
            item["video_path"] = final_path
            out_size = os.path.getsize(final_path)
            if MOBILE_COPY and out_size > 40 * 1024 * 1024:
                try:
                    rep.write("📱 កំពុងបង្កើតកំណែតូចសម្រាប់ទូរស័ព្ទ...")
                    item["small_path"] = make_mobile_copy(final_path, os.path.join(job.folder, f"mobile_{uuid.uuid4().hex[:8]}.mp4"))
                except Exception:
                    item["small_path"] = None
            item["captions"] = [t for _, _, t in captions]
            item["debug"] = {
                "ម៉ាស៊ីន": used_engine, "ម៉ូដែល": used_model,
                "ការតម្រឹម": sync_mode, "ផ្នែកបរាជ័យ": failed_chunks,
                "Font ដែលប្រើ": used_font, "Dubbing": dub_ok,
                "អ្នកនិយាយ": (item["voice_lines"][0] if item["voice_lines"] else ""),
                "ទំហំលទ្ធផល": f"{out_size / (1024 * 1024):.1f}MB",
                "ការសាក Font": "\n".join(attempts),
                "fontselect": "\n".join(line for line in ffmpeg_log.splitlines() if "fontselect" in line.lower())[:1500],
                "ម៉ោងអក្សរ": "\n".join(f"[{s:.1f}-{e:.1f}] {t}" for s, e, t in captions),
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
        try:
            if item.get("path") and os.path.exists(item["path"]):
                os.remove(item["path"])
        except Exception:
            pass
        _PIPELINE_SLOTS.release()
        gc.collect()


def build_zip(items, folder):
    ok = [it for it in items if it["state"] == "done" and it.get("video_path")]
    if len(ok) < 2:
        return None
    total = sum(os.path.getsize(it["video_path"]) for it in ok if os.path.isfile(it["video_path"]))
    if total > MAX_ZIP_MB * 1024 * 1024:
        return None
    zip_path = os.path.join(folder, "khmer_videos.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for i, it in enumerate(ok, start=1):
            if os.path.isfile(it["video_path"]):
                z.write(it["video_path"], f"{i:02d}_{safe_filename(it['name'])}_khmer.mp4")
    return zip_path


class _NoProgress:
    def progress(self, *a, **k):
        pass

    def write(self, *a, **k):
        pass


def extract_links(text):
    """ទាញតំណ http/https ទាំងអស់ពីអត្ថបទ (បំបែកដោយបន្ទាត់ ដកឃ្លា ឬក្បៀស ក៏បាន) ហើយលុបតំណស្ទួន។"""
    found = re.findall(r"https?://[^\s<>\"'\u3000\uff0c\u3002]+", text or "", flags=re.I)
    out = []
    for u in found:
        u = u.rstrip(".,;:!?)]}\u00bb\u17d4")
        if len(u) > 10 and u not in out:
            out.append(u)
    return out


LINK_RETRIES = _env_int("LINK_RETRIES", 8)   # ចំនួនលើកព្យាយាមអតិបរមាក្នុងមួយតំណ


def _fetch_one(url, on_try=None):
    """ទាញវីដេអូមួយតំណ ហើយព្យាយាមម្តងទៀតដោយស្វ័យប្រវត្តិរហូតរកឃើញ (មិនប៉ះ st.session_state)។"""
    last = ""
    for attempt in range(1, LINK_RETRIES + 1):
        if on_try:
            try:
                on_try(attempt)
            except Exception:
                pass
        folder = tempfile.mkdtemp(prefix="kac_link_")
        path = os.path.join(folder, "video.mp4")
        try:
            download_video(url, path, _NoProgress())
            return {"path": path, "ok": True, "tries": attempt}
        except Exception as e:
            shutil.rmtree(folder, ignore_errors=True)
            last = re.sub(r"https?://\S+", "[link]", str(e) or type(e).__name__)[:600]
            if attempt < LINK_RETRIES:
                time.sleep(min(2 * attempt, 8))
    return {"path": None, "ok": False, "err": last, "tries": LINK_RETRIES}


def fetch_link_preview(url):
    """ទាញវីដេអូពីតំណមកទុកជាមុន (ដើម្បីបង្ហាញ មើល ទាញយក និងបកប្រែ)។"""
    cache = st.session_state.setdefault("link_cache", {})
    ent = cache.get(url)
    if ent is None:
        ent = _fetch_one(url)
        cache[url] = ent
    return ent


def fetch_links_preview(urls, status=None):
    """រកតំណម្តងមួយៗតាមលំដាប់ (ទី១ រួចទី២ ...) តំណណារកមិនឃើញ ព្យាយាមម្តងទៀតរហូតរកឃើញ ទើបទៅតំណបន្ទាប់។"""
    cache = st.session_state.setdefault("link_cache", {})
    for u in [u for u in urls if u not in cache]:
        num = urls.index(u) + 1

        def _cb(attempt, num=num):
            if status is not None:
                status.info(f"⏳ កំពុងរកវីដេអូទី {num} / {len(urls)} · ព្យាយាមលើកទី {attempt}/{LINK_RETRIES}")

        cache[u] = _fetch_one(u, _cb)
    return {u: cache[u] for u in urls}


def app_base_url():
    """អាសយដ្ឋានកម្មវិធីនេះ (សម្រាប់បង្កើត Bookmarklet)។"""
    try:
        u = st.context.url
        if u:
            return str(u).split("?")[0]
    except Exception:
        pass
    try:
        h = st.context.headers
        host = h.get("X-Forwarded-Host") or h.get("Host")
        if host:
            return f"https://{host}/"
    except Exception:
        pass
    return "https://YOUR-APP.streamlit.app/"


SPLIT_SECONDS = 6 * 60   # បំបែកវីដេអូជាផ្នែកប្រវែង ៦ នាទី


def link_or_copy(src, dst):
    """បង្កើត hard link (លឿន មិនចំណាយទំហំថ្មី) បើមិនបានទើបចម្លង។"""
    try:
        os.link(src, dst)
    except Exception:
        shutil.copyfile(src, dst)


def split_video_parts(src, folder, idx):
    """បំបែកវីដេអូវែងជាផ្នែក ~៦ នាទី (កាត់ដោយមិន encode ឡើងវិញ ដូច្នេះលឿន)។ ត្រឡប់បញ្ជីផ្លូវឯកសារតាមលំដាប់ ឬ None បើមិនចាំបាច់/បរាជ័យ។"""
    try:
        duration, _w, _h = probe_media(src)
    except Exception:
        return None
    if duration <= SPLIT_SECONDS + 20:
        return None
    pattern = os.path.join(folder, f"part_{idx}_%03d.mp4")
    try:
        run_ffmpeg(["-i", src, "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
                    "-f", "segment", "-segment_time", str(SPLIT_SECONDS),
                    "-reset_timestamps", "1", pattern])
    except Exception:
        return None
    prefix = f"part_{idx}_"
    parts = sorted(os.path.join(folder, fn) for fn in os.listdir(folder)
                   if fn.startswith(prefix) and fn.endswith(".mp4"))
    parts = [pp for pp in parts if os.path.getsize(pp) > 1000]
    return parts if len(parts) > 1 else None


# =====================================================================
#  បណ្ណាល័យវីដេអូស្រាប់ (អ្នកគ្រប់គ្រងដាក់តំណ → អ្នកប្រើជ្រើសយកទៅបកប្រែ)
# =====================================================================
# ដាក់តំណនៅទីនេះ ឬក្នុង Secrets (VIDEO_LIBRARY = មួយបន្ទាត់ ១ តំណ) ឬបន្ថែមតាមអ្នកគ្រប់គ្រងក្នុងកម្មវិធី
VIDEO_LIBRARY = [
    # {"url": "https://www.tiktok.com/@user/video/123...", "title": "ចំណងជើង (មិនបង្ខំ)"},
]
LIB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_library.json")
LIB_PAGE = 6


def _lib_read_file():
    try:
        with open(LIB_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [d for d in data if isinstance(d, dict) and d.get("url")]
    except Exception:
        return []


def _lib_write_file(items):
    try:
        with open(LIB_FILE, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def load_library():
    out, seen = [], set()
    sources = list(VIDEO_LIBRARY)
    sources += [{"url": u, "title": ""} for u in extract_links(os.environ.get("VIDEO_LIBRARY", ""))]
    sources += _lib_read_file()
    for d in sources:
        u = str(d.get("url", "")).strip()
        if u and u not in seen:
            seen.add(u)
            out.append({"url": u, "title": str(d.get("title", "") or "")})
    return out


@st.cache_data(ttl=86400, show_spinner=False)
def video_meta(url):
    """យកចំណងជើង និងរូបតូចពី TikTok oEmbed (បើបរាជ័យ ត្រឡប់ទទេ)។"""
    try:
        if "tiktok.com" in url:
            api = "https://www.tiktok.com/oembed?url=" + urllib.parse.quote(url, safe="")
            req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as r:
                d = json.loads(r.read().decode("utf-8"))
            return {"title": d.get("title") or "", "thumb": d.get("thumbnail_url") or "",
                    "author": d.get("author_name") or ""}
    except Exception:
        pass
    return {"title": "", "thumb": "", "author": ""}


def drop_link_cache(keep=()):
    cache = st.session_state.get("link_cache", {})
    for k in list(cache.keys()):
        if k not in keep:
            ent = cache.pop(k)
            if ent.get("path"):
                shutil.rmtree(os.path.dirname(ent["path"]), ignore_errors=True)


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
                st.info("💡 បើបញ្ហាដោយសារ API អស់កូតា សូមដាក់ API Key ផ្ទាល់ខ្លួននៅផ្ទាំង «🌐 បកប្រែ» រួចសាកម្តងទៀត។")
                if DEBUG and it["raw_error"]:
                    st.text(it["raw_error"])
            else:
                st.progress(max(0.0, min(1.0, it["pct"])), text=it["stage"])
            for w in it["warn"]:
                st.warning(w)
    if (was_running and not job.running()) or (reviewing != job.reviewing()):
        st.rerun()


def make_mobile_copy(src, dst):
    """បង្កើតវីដេអូតូច (720p, bitrate ទាប) សម្រាប់ទាញយក/រក្សាទុកលើទូរស័ព្ទ។"""
    run_ffmpeg([
        "-i", src,
        "-vf", "scale=w='if(gt(iw,ih),min(1280,iw),-2)':h='if(gt(iw,ih),-2,min(1280,ih))',format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
        "-maxrate", "1500k", "-bufsize", "3000k",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", dst,
    ])
    return dst


PREVIEW_MAX_MB = 60   # វីដេអូធំជាងនេះ មិនបង្ហាញ preview


SHARE_MAX_MB = 30


def share_button(path, fname):
    """បង្ហោះវីដេអូទៅ TikTok តាមបញ្ជី Share ក្នុងទូរស័ព្ទ (មិនបាច់ទាញយក)។"""
    try:
        size = os.path.getsize(path)
    except Exception:
        return False
    if size > SHARE_MAX_MB * 1024 * 1024:
        return False
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    components.html(
        """
<button id="b" style="width:100%;padding:14px;font-size:17px;font-weight:700;color:#fff;border:0;
border-radius:14px;background:linear-gradient(90deg,#B13CFF,#3C6BFF);cursor:pointer;
font-family:system-ui,sans-serif;">🎵 បង្ហោះទៅ TikTok</button>
<div id="m" style="color:#ffb4b4;font-size:14px;margin-top:6px;font-family:system-ui,sans-serif;"></div>
<script>
const B64 = "__B64__";
const NAME = __NAME__;
document.getElementById("b").onclick = async () => {
  const m = document.getElementById("m");
  m.textContent = "";
  try {
    const bin = atob(B64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    const targets = [];
    try { if (window.parent && window.parent.navigator && window.parent.File) targets.push([window.parent.navigator, window.parent.File]); } catch (e) {}
    targets.push([navigator, File]);
    for (const [nav, F] of targets) {
      try {
        const file = new F([arr], NAME, {type: "video/mp4"});
        if (nav.canShare && nav.canShare({files: [file]})) {
          await nav.share({files: [file]});
          return;
        }
      } catch (e) {
        if (e && e.name === "AbortError") return;
      }
    }
    m.innerHTML = "ឧបករណ៍ ឬកម្មវិធីរុករកនេះមិនគាំទ្រការបង្ហោះផ្ទាល់ទេ។ សូមទាញយកវីដេអូ រួច "
      + '<a href="https://www.tiktok.com/tiktokstudio/upload" target="_blank" style="color:#fff">បើកទំព័រ TikTok</a>';
  } catch (e) {
    m.textContent = "មិនអាចបង្ហោះបានទេ។ សូមទាញយកវីដេអូជាមុន។";
  }
};
</script>
""".replace("__B64__", b64).replace("__NAME__", json.dumps(fname)),
        height=84,
    )
    return True


def download_area(job):
    done = [(i, it) for i, it in enumerate(job.items, start=1) if it["state"] == "done"]
    if not done:
        st.info("វីដេអូណាដែលរួចរាល់ នឹងលេចឡើងនៅទីនេះភ្លាមៗ ហើយអាចទាញយកបានតែម្តង។")
        return
    st.caption("📱 iPhone: ចុចប៊ូតុងទាញយក → ចុច «Download» → បើក Safari បង្ហាញរូបព្រួញ ⬇️ ខាងលើ ចុចវា → ជ្រើសវីដេអូ → Share → Save Video។ សូមប្រើ Safari។")
    for i, it in done:
        with st.container(border=True):
            vp = it.get("video_path")
            if vp and os.path.isfile(vp):
                fname = f"{safe_filename(it['name'])}_khmer.mp4"
                size_mb = os.path.getsize(vp) / (1024 * 1024)
                # វីដេអូធំ: ប្រើកំណែតូច (ដែលបង្កើតស្វ័យប្រវត្តិ) ដើម្បីឱ្យ iPhone ទាញយកបានលឿន
                small = it.get("small_path")
                if small and os.path.isfile(small):
                    vp = small
                    fname = fname.replace("_khmer.mp4", "_khmer_mobile.mp4")
                    size_mb = os.path.getsize(vp) / (1024 * 1024)
                st.markdown(f"**✅ {os.path.splitext(it['name'])[0]}.mp4** · {size_mb:.0f}MB")
                with open(vp, "rb") as vf:
                    dl_button("⬇️ ទាញយកវីដេអូ", vf, fname, "video/mp4",
                              key=f"dl_{job.id}_{i}", type="primary", use_container_width=True)
                if not share_button(vp, fname):
                    if hasattr(st, "link_button"):
                        st.link_button("🎵 បង្ហោះទៅ TikTok", "https://www.tiktok.com/tiktokstudio/upload",
                                       use_container_width=True)
                if size_mb <= PREVIEW_MAX_MB:
                    with st.expander("▶️ មើលវីដេអូ"):
                        st.video(vp)
            else:
                st.caption("ឯកសារវីដេអូត្រូវបានលុបចេញពីម៉ាស៊ីនហើយ។")
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
                    st.text("\\n".join(it["log"][-30:]))
    if job.zip and os.path.isfile(job.zip):
        with open(job.zip, "rb") as zf:
            dl_button("📦 ទាញយកទាំងអស់ (ZIP)", zf, "khmer_videos.zip", "application/zip", key=f"zip_{job.id}", use_container_width=True)


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


# API keys: អាចដាក់ច្រើនក្នុង Secret តែមួយដោយបំបែកជាក្បៀស ឬបន្ទាត់ថ្មី។
# ក៏អាចប្រើ GEMINI_API_KEY_1, GEMINI_API_KEY_2 ... និង GROQ_API_KEY_1, GROQ_API_KEY_2 ... បាន។
def collect_api_keys(prefix):
    values = [get_secret(prefix, ""), get_secret(prefix + "S", "")]
    # អាន numbered secrets រហូតដល់ 20 keys; ឈប់ពេលជួប 5 លេខទទេជាប់គ្នា។
    empty_streak = 0
    for i in range(1, 21):
        value = get_secret(f"{prefix}_{i}", "")
        if value:
            values.append(value)
            empty_streak = 0
        else:
            empty_streak += 1
            if empty_streak >= 5 and i >= 5:
                break
    return "\n".join(split_keys(values))


# =====================================================================
#  API Key ផ្ទាល់ខ្លួនរបស់អ្នកប្រើ (ពេល API របស់កម្មវិធីអស់)
#  Key រក្សាទុកតែក្នុង session របស់អ្នកប្រើប៉ុណ្ណោះ (មិនសរសេរចូលឯកសារ)
#  វាបាត់ដោយស្វ័យប្រវត្តិពេលបិទទំព័រ ឬចុច «ឈប់ប្រើ»
# =====================================================================
def validate_groq_key(key):
    """ពិនិត្យ Groq key ថាប្រើបានឬអត់។ ត្រឡប់ (True/False, សារ)។"""
    key = str(key or "").strip()
    if not key or len(key) < 20 or any(c.isspace() for c in key):
        return False, "Key មិនត្រឹមត្រូវ (ត្រូវចាប់ផ្តើមដោយ gsk_ ហើយគ្មានដកឃ្លា)។"
    try:
        req = urllib.request.Request(GROQ_MODELS_URL, headers={"Authorization": f"Bearer {key}", "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
        return True, "Key ប្រើបាន ✅"
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return True, "Key ត្រឹមត្រូវ (ប៉ុន្តែកំពុងអស់កូតាបណ្តោះអាសន្ន) ✅"
        if e.code in (401, 403):
            return False, "Key មិនត្រឹមត្រូវ ឬត្រូវបានបិទ។"
        return False, f"ពិនិត្យ Key មិនបាន (HTTP {e.code})។"
    except Exception:
        return False, "ពិនិត្យ Key មិនបាន (បញ្ហាបណ្តាញ)។ សូមសាកម្តងទៀត។"


def validate_gemini_key(key):
    """ពិនិត្យ Gemini key ថាប្រើបានឬអត់។ ត្រឡប់ (True/False, សារ)។"""
    key = str(key or "").strip()
    if not key or len(key) < 20 or any(c.isspace() for c in key):
        return False, "Key មិនត្រឹមត្រូវ (ត្រូវចាប់ផ្តើមដោយ AIza ហើយគ្មានដកឃ្លា)។"
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1&key=" + urllib.parse.quote(key)
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            r.read()
        return True, "Key ប្រើបាន ✅"
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return True, "Key ត្រឹមត្រូវ (ប៉ុន្តែកំពុងអស់កូតាបណ្តោះអាសន្ន) ✅"
        if e.code in (400, 401, 403):
            return False, "Key មិនត្រឹមត្រូវ ឬត្រូវបានបិទ។"
        return False, f"ពិនិត្យ Key មិនបាន (HTTP {e.code})។"
    except Exception:
        return False, "ពិនិត្យ Key មិនបាន (បញ្ហាបណ្តាញ)។ សូមសាកម្តងទៀត។"


def effective_groq_key():
    """Key របស់អ្នកប្រើ (បើមាន) មុន ហើយ key របស់កម្មវិធីជាបម្រុង។"""
    mine = st.session_state.get("user_groq_key", "")
    return "\n".join(split_keys([mine, GROQ_KEY])) if mine else GROQ_KEY


def effective_gemini_key():
    mine = st.session_state.get("user_gemini_key", "")
    return "\n".join(split_keys([mine, GEMINI_KEY])) if mine else GEMINI_KEY


def user_key_box():
    """ប្រអប់ឱ្យអ្នកប្រើដាក់ API Key ផ្ទាល់ខ្លួន (Groq ឬ Gemini)។ រក្សាតែក្នុង session។"""
    if st.session_state.pop("_clear_key_input", False):
        st.session_state.pop("user_key_input", None)
    with st.container(border=True):
        st.markdown("**🔑 API Key ផ្ទាល់ខ្លួន**")
        st.caption("បើ API របស់កម្មវិធីអស់កូតា ឬបរាជ័យ អ្នកអាចដាក់ Groq (console.groq.com/keys) ឬ Gemini (aistudio.google.com/apikey) Key របស់អ្នកផ្ទាល់ ដើម្បីបន្តប្រើបាន។")
        for name, sk in (("Groq", "user_groq_key"), ("Gemini", "user_gemini_key")):
            mine = st.session_state.get(sk, "")
            if mine:
                st.success(f"✅ កំពុងប្រើ {name} Key របស់អ្នក (…{mine[-4:]})")
                if st.button(f"🗑 ឈប់ប្រើ {name} Key", key=f"remove_{sk}"):
                    st.session_state.pop(sk, None)
                    st.rerun()
        provider = st.radio("ប្រភេទ Key", ["Groq", "Gemini"], horizontal=True, key="user_key_provider")
        typed = st.text_input(f"{provider} API Key", type="password",
                              placeholder="gsk_..." if provider == "Groq" else "AIza...", key="user_key_input")
        st.caption("🔒 Key ប្រើតែក្នុងទំព័រនេះ មិនត្រូវបានរក្សាទុកទេ ហើយបាត់ពេលអ្នកបិទទំព័រ ឬឈប់ប្រើ។")
        if st.button("✅ ពិនិត្យ និងប្រើ Key នេះ", key="user_key_save", use_container_width=True):
            ok, msg = (validate_groq_key if provider == "Groq" else validate_gemini_key)(typed)
            if ok:
                st.session_state["user_groq_key" if provider == "Groq" else "user_gemini_key"] = typed.strip()
                st.session_state["_clear_key_input"] = True
                st.rerun()
            else:
                st.error(msg)


GEMINI_KEY = collect_api_keys("GEMINI_API_KEY")   # ដាក់ GEMINI_API_KEY ក្នុង Secrets (អាចដាក់ច្រើន)
GROQ_KEY = collect_api_keys("GROQ_API_KEY")
ELEVEN_KEY = get_secret("ELEVENLABS_API_KEY", "")

render_header()

if not GEMINI_KEY and not GROQ_KEY and not st.session_state.get("user_groq_key") and not st.session_state.get("user_gemini_key"):
    st.warning("កម្មវិធីមិនមាន API ទេ។ សូមដាក់ API Key ផ្ទាល់ខ្លួននៅផ្ទាំង «🌐 បកប្រែ» ឬទាក់ទងម្ចាស់កម្មវិធី។")

ENGINE_FREE = "⭐ គម្រោង VIP"
ENGINE_GEMINI = "✨ Gemini (ទាញអត្ថបទ)"

current_job = st.session_state.get("job")
busy = bool(current_job and current_job.running())

voice_label = list(TTS_VOICES.keys())[0]
# មុខងារដែលបើកដោយស្វ័យប្រវត្តិជានិច្ច (គ្មានប៊ូតុងបិទបើក)
sub_on = True
dub_on = True
emotion_on = True
keep_bg = True
auto_gender = True
srt_on = False
narrate_on = False
review_on = False
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

tab_vid, tab_trans, tab_voice, tab_text, tab_fx, tab_out = st.tabs(
    ["🏠 វីដេអូ", "🌐 បកប្រែ", "🎙 សំឡេង", "🔤 អក្សរ", "🖼 Logo", "⬇️ ទាញយក"]
)

# ============================ ផ្ទាំង ១: វីដេអូ ============================
with tab_vid:
    # បើកមកពី TikTok តាម Bookmarklet: ?link=<តំណវីដេអូ>&auto=1 → ដាក់តំណ ស្វែងរក ហើយបកប្រែអូតូ
    _qp_link = st.query_params.get("link")
    if isinstance(_qp_link, list):
        _qp_link = _qp_link[0] if _qp_link else ""
    if _qp_link and st.session_state.get("_qp_consumed") != _qp_link:
        st.session_state["_qp_consumed"] = _qp_link
        _ql = extract_links(_qp_link)[:MAX_VIDEOS]
        if _ql:
            st.session_state["mode_pick"] = "🔗 Link"
            st.session_state["link_text_area"] = "\n".join(_ql)
            st.session_state["link_searched"] = list(_ql)
            _qa = st.query_params.get("auto")
            if isinstance(_qa, list):
                _qa = _qa[0] if _qa else ""
            st.session_state["_auto_translate"] = (str(_qa) == "1")
        try:
            st.query_params.clear()
        except Exception:
            pass
    with st.container(border=True):
        mode = st.radio("វិធីបញ្ចូលវីដេអូ", ["📁 Upload", "🔗 Link"], horizontal=True,
                        label_visibility="collapsed", key="mode_pick")
        uploaded_files = []
        link_text = ""
        link_translate = False
        if mode.startswith("📁"):
            uploaded_files = st.file_uploader(
                "បន្ថែមវីដេអូ (ជ្រើសបានច្រើន)", type=["mp4", "mov", "mkv", "avi", "webm"],
                accept_multiple_files=True) or []
        else:
            # ---------- វីដេអូស្រាប់ ----------
            _lib = load_library()
            if _lib:
                st.markdown("**🎞 វីដេអូស្រាប់ — ជ្រើសយកទៅបកប្រែ**")
                _shown = st.session_state.get("lib_shown", LIB_PAGE)
                for _i, _v in enumerate(_lib[:_shown]):
                    _m = video_meta(_v["url"])
                    with st.container(border=True):
                        if _m["thumb"]:
                            try:
                                st.image(_m["thumb"], use_container_width=True)
                            except Exception:
                                try:
                                    st.image(_m["thumb"])
                                except Exception:
                                    pass
                        _title = _v["title"] or _m["title"] or f"វីដេអូទី {_i + 1}"
                        st.caption(_title[:120] + (f" · @{_m['author']}" if _m["author"] else ""))
                        _c1, _c2 = st.columns(2)
                        _add = _c1.button("➕ បន្ថែម", key=f"lib_add_{_i}", use_container_width=True)
                        _go = _c2.button("✨ បកប្រែ", key=f"lib_go_{_i}", use_container_width=True, disabled=busy)
                        if _go:
                            st.session_state["link_text_area"] = _v["url"]
                            st.session_state["link_searched"] = [_v["url"]]
                            st.session_state["_auto_translate"] = True
                        elif _add:
                            _cur = extract_links(st.session_state.get("link_text_area", ""))
                            if _v["url"] not in _cur:
                                _cur.append(_v["url"])
                            _cur = _cur[:MAX_VIDEOS]
                            st.session_state["link_text_area"] = "\n".join(_cur)
                            st.session_state["link_searched"] = list(_cur)
                if len(_lib) > _shown:
                    if st.button(f"បង្ហាញបន្ថែម ({len(_lib) - _shown})", key="lib_more", use_container_width=True):
                        st.session_state["lib_shown"] = _shown + LIB_PAGE
                        st.rerun()
            else:
                st.caption("🎞 មិនទាន់មានវីដេអូស្រាប់ទេ។ អ្នកគ្រប់គ្រងអាចបន្ថែមខាងក្រោម។")
            with st.expander("🔑 អ្នកគ្រប់គ្រង (បន្ថែម/លុបវីដេអូស្រាប់)"):
                if not st.session_state.get("_lib_admin"):
                    _lpw = st.text_input("លេខសម្ងាត់", type="password", key="_lib_pw")
                    if _lpw and _lpw == MAINTENANCE_ADMIN_KEY:
                        st.session_state["_lib_admin"] = True
                        st.rerun()
                    elif _lpw:
                        st.error("លេខសម្ងាត់មិនត្រឹមត្រូវ")
                else:
                    _new = st.text_area("តំណវីដេអូថ្មី (មួយបន្ទាត់ ១ តំណ)", key="lib_new_links", height=110)
                    if st.button("➕ បន្ថែមទៅបណ្ណាល័យ", key="lib_save_btn", use_container_width=True):
                        _file_items = _lib_read_file()
                        _have = {d["url"] for d in load_library()}
                        _added = 0
                        for _u in extract_links(_new):
                            if _u not in _have:
                                _file_items.append({"url": _u, "title": ""})
                                _added += 1
                        if _lib_write_file(_file_items):
                            st.success(f"បានបន្ថែម {_added} តំណ")
                            st.rerun()
                        else:
                            st.error("រក្សាទុកមិនបាន")
                    _file_now = _lib_read_file()
                    if _file_now:
                        _del = st.multiselect("លុបវីដេអូ", [d["url"] for d in _file_now], key="lib_del_sel")
                        if _del and st.button("🗑 លុបដែលបានជ្រើស", key="lib_del_btn", use_container_width=True):
                            _lib_write_file([d for d in _file_now if d["url"] not in _del])
                            st.rerun()
                    st.caption("ចំណាំ៖ នៅលើ Streamlit Cloud បញ្ជីដែលបន្ថែមតាមទីនេះអាចបាត់ពេល reboot/deploy ថ្មី។ "
                               "ដើម្បីរក្សាជាអចិន្ត្រៃយ៍ ដាក់ក្នុងបញ្ជី VIDEO_LIBRARY ក្នុងកូដ ឬក្នុង Secrets។")
            with st.expander("⚡ បកប្រែអូតូពី TikTok (Bookmarklet)"):
                st.markdown(
                    "១. ចម្លងកូដខាងក្រោម រួចបង្កើត Bookmark ថ្មីក្នុង Browser ហើយបិទភ្ជាប់កូដនេះជា «URL» (ដាក់ឈ្មោះ «បកប្រែខ្មែរ»)។\n\n"
                    "២. បើក TikTok រើសវីដេអូណាមួយ ហើយចុច Bookmark នោះ → កម្មវិធីនេះនឹងបើក ទាញវីដេអូ និងបកប្រែអូតូ។")
                st.code("javascript:(function(){location.href='" + app_base_url()
                        + "?link='+encodeURIComponent(location.href)+'&auto=1';})();", language="text")
            link_text = st.text_area(
                "តំណវីដេអូ TikTok (ដាក់បានច្រើនតំណ — មួយបន្ទាត់ ១ តំណ)",
                key="link_text_area",
                placeholder="បិទភ្ជាប់តំណវីដេអូនៅទីនេះ\nដាក់បានច្រើនតំណម្តងតែមួយ (មួយបន្ទាត់ ១ តំណ)",
                height=170)
            _all_links = extract_links(link_text)
            _link_lines = _all_links[:MAX_VIDEOS]
            if _all_links:
                st.caption(f"🔗 រកឃើញ {len(_all_links)} តំណ"
                           + (f" · ធ្វើបាន {MAX_VIDEOS} តំណដំបូង" if len(_all_links) > MAX_VIDEOS else ""))
            _search_label = "🔍 ស្វែងរក" + (f" ({len(_link_lines)} តំណ)" if len(_link_lines) > 1 else "")
            if st.button(_search_label, type="primary", use_container_width=True, key="link_search_btn",
                         disabled=(not _link_lines)):
                _cache0 = st.session_state.get("link_cache", {})
                for _u0 in _link_lines:
                    if _u0 in _cache0 and not _cache0[_u0].get("ok"):
                        _cache0.pop(_u0, None)
                st.session_state["link_searched"] = list(_link_lines)
            _searched = [u for u in st.session_state.get("link_searched", []) if u in _link_lines]
            drop_link_cache(keep=_searched)
            _link_lines = _searched
            if _link_lines:
                _need = [u for u in _link_lines if u not in st.session_state.get("link_cache", {})]
                if _need:
                    _ph = st.empty()
                    fetch_links_preview(_link_lines, _ph)
                    _ph.empty()
            _n_ok = 0
            _multi = len(_link_lines) > 1
            for _n, _u in enumerate(_link_lines, start=1):
                _ent = fetch_link_preview(_u)
                _box = (st.expander(f"🎬 វីដេអូទី {_n}", expanded=(_n == 1)) if _multi else st.container())
                with _box:
                    if _ent["ok"] and _ent["path"] and os.path.isfile(_ent["path"]):
                        _n_ok += 1
                        _mb = os.path.getsize(_ent["path"]) / (1024 * 1024)
                        _info = f"📦 {_mb:.0f}MB"
                        try:
                            _dur, _w0, _h0 = probe_media(_ent["path"])
                            _info += f" · ⏱ {_dur / 60:.1f} នាទី"
                            if _dur > SPLIT_SECONDS + 20:
                                _np = int(-(-_dur // SPLIT_SECONDS))
                                _info += f" · ✂️ នឹងបំបែកជា {_np} ផ្នែក (ក្នុងមួយផ្នែក ៦ នាទី)"
                        except Exception:
                            pass
                        st.caption(_info)
                        if _mb <= PREVIEW_MAX_MB:
                            try:
                                st.video(_ent["path"])
                            except Exception:
                                pass
                        if _mb <= 300:
                            with open(_ent["path"], "rb") as _fh:
                                dl_button(f"⬇️ ទាញយកវីដេអូទី {_n}", _fh, f"video_{_n}.mp4", "video/mp4",
                                          key=f"dl_link_{_n}", use_container_width=True)
                    else:
                        st.error("រកតំណមិនឃើញទេ ទោះបានព្យាយាមច្រើនលើកហើយ។ សូមចុចព្យាយាមម្តងទៀត។")
                        if _ent.get("err"):
                            st.caption(f"ព័ត៌មានបច្ចេកទេស (បានព្យាយាម {_ent.get('tries', 1)} លើក)")
                            st.code(_ent["err"])
                        if st.button("🔄 ព្យាយាមម្តងទៀត", key=f"retry_link_{_n}", use_container_width=True):
                            st.session_state.get("link_cache", {}).pop(_u, None)
                            st.rerun()
            if _multi:
                st.caption(f"✅ រកឃើញ {_n_ok} / {len(_link_lines)} វីដេអូ")
            if _n_ok:
                link_translate = st.button(
                    f"✨ បកប្រែ ({_n_ok} វីដេអូ)" if _n_ok > 1 else "✨ បកប្រែ",
                    type="primary", use_container_width=True, disabled=busy, key="link_translate_btn")
                if st.session_state.get("_auto_translate") and not busy:
                    st.session_state["_auto_translate"] = False
                    link_translate = True
            elif _link_lines and st.session_state.get("_auto_translate"):
                st.session_state["_auto_translate"] = False
        if mode.startswith("📁"):
            st.caption(f"រហូតដល់ {MAX_VIDEOS} វីដេអូ · រហូតដល់ {MAX_DURATION_MIN // 60} ម៉ោង")
        else:
            st.caption(f"រហូតដល់ {MAX_VIDEOS} តំណ · ប្រវែង និងទំហំប៉ុន្មានក៏បាន · វីដេអូវែងនឹងបំបែកជាផ្នែក ៦ នាទី ហើយធ្វើតាមលំដាប់")
        _ram_txt = server_ram_info()
        if _ram_txt:
            st.caption(_ram_txt)
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
        engine_options.append(ENGINE_FREE)
        if effective_gemini_key():
            engine_options.append(ENGINE_GEMINI)   # Gemini = ម៉ាស៊ីនបម្រុង
        engine_label = st.selectbox("ម៉ាស៊ីនបកប្រែ", engine_options, index=0)
        if effective_groq_key() and effective_gemini_key():
            st.caption("🔁 បើម៉ាស៊ីនទីមួយមានបញ្ហា ឬអស់កូតា កម្មវិធីប្តូរទៅ Gemini បម្រុងដោយស្វ័យប្រវត្តិ។")
        lc1, lc2 = st.columns(2)
        with lc1:
            language_label = st.selectbox("ភាសាដើម", list(LANGUAGES.keys()), index=0)
        with lc2:
            st.selectbox("បកប្រែទៅ", ["🇰🇭 ខ្មែរ"], disabled=True, key="target_lang")
    with st.container(border=True):
        st.caption("✅ អក្សររត់ខ្មែរ និងសំឡេងអានខ្មែរ ត្រូវបានបើកដោយស្វ័យប្រវត្តិ។")
    user_key_box()

# ============================ ផ្ទាំង ៣: សំឡេង ============================
with tab_voice:
    with st.container(border=True):
        # Keep only the simple voice choices requested by the user.
        voice_label = st.radio("ជ្រើសសំឡេងនិយាយ", list(TTS_VOICES.keys()), horizontal=True, key="voice_pick")

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


# ============================ ផ្ទាំង Logo + Blur ============================
BLUR_COLORS = ["#FF2D2D", "#FFE600", "#00E640", "#2F6BFF"]


def logo_preview_data(raw):
    """រូបតូចសម្រាប់ preview (មិនប៉ះឯកសារដើម)។"""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        iw, ih = im.size
        im.thumbnail((300, 300))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), iw, ih
    except Exception:
        return None, 1, 1


def render_fx_preview(aspect, logo, lx, ly, lsize, lop, tint, blurs):
    if aspect == "9:16":
        box = "height:260px;aspect-ratio:9/16;margin:6px auto;"
    elif aspect == "1:1":
        box = "height:240px;aspect-ratio:1/1;margin:6px auto;"
    else:
        box = "width:100%;aspect-ratio:16/9;margin:6px 0;"
    html = [f'<div style="position:relative;overflow:hidden;border-radius:14px;border:1px solid rgba(125,145,255,.22);'
            f'background:linear-gradient(160deg,#3A2C6E 0%,#1B2A5E 60%,#0E1636 100%);{box}">']
    for i, b in enumerate(blurs, start=1):
        c = BLUR_COLORS[(i - 1) % len(BLUR_COLORS)]
        html.append(
            f'<div style="position:absolute;left:{b["x"] * 100:.1f}%;top:{b["y"] * 100:.1f}%;width:{b["w"] * 100:.1f}%;height:{b["h"] * 100:.1f}%;'
            f'border:2px dashed {c};background:rgba(255,255,255,.14);backdrop-filter:blur(4px);display:flex;'
            f'align-items:center;justify-content:center;color:{c};font-weight:800;">{i}</div>')
    if logo and logo[0]:
        uri, iw, ih = logo
        pos = f"position:absolute;left:{lx}%;top:{ly}%;transform:translate(-50%,-50%);width:{lsize}%;opacity:{lop};"
        if tint:
            html.append(f'<div style="{pos}aspect-ratio:{iw}/{ih};background:{tint};'
                        f'-webkit-mask:url({uri}) center/contain no-repeat;mask:url({uri}) center/contain no-repeat;"></div>')
        else:
            html.append(f'<img src="{uri}" style="{pos}height:auto;">')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


fx_settings = None
with tab_fx:
    prev_fx = st.container()
    with st.container(border=True):
        st.markdown("**🖼 Logo**")
        logo_file = st.file_uploader("Upload logo (PNG ផ្ទៃថ្លាល្អបំផុត)", type=["png", "jpg", "jpeg", "webp"], key="logo_up")
        logo_x, logo_y, logo_size, logo_op, logo_tint = 90, 10, 15, 100, None
        if logo_file is not None:
            g1, g2 = st.columns(2)
            with g1:
                logo_x = st.slider("ទីតាំងឆ្វេង↔ស្តាំ (%)", 0, 100, 90, key="logo_x")
            with g2:
                logo_y = st.slider("ទីតាំងលើ↕ក្រោម (%)", 0, 100, 10, key="logo_y")
            g3, g4 = st.columns(2)
            with g3:
                logo_size = st.slider("ទំហំ (% នៃទទឹងវីដេអូ)", 3, 80, 15, key="logo_size")
            with g4:
                logo_op = st.slider("ភាពច្បាស់ (%)", 10, 100, 100, key="logo_op")
            if st.checkbox("🎨 ប្តូរពណ៌ Logo (ល្អសម្រាប់ logo ពណ៌តែមួយ)", key="logo_tint_on"):
                logo_tint = st.color_picker("ពណ៌ Logo", "#FFFFFF", key="logo_tint_col")
    with st.container(border=True):
        st.markdown("**🌫 Blur បិទបាំង**")
        n_blur = st.slider("ចំនួនកន្លែងត្រូវ Blur", 0, 4, 0, key="n_blur")
        blur_list = []
        for i in range(n_blur):
            c = BLUR_COLORS[i % len(BLUR_COLORS)]
            with st.expander(f"កន្លែងទី {i + 1}", expanded=(n_blur <= 2)):
                d = [(35, 80, 30, 12), (5, 5, 25, 12), (65, 5, 30, 12), (35, 40, 30, 20)][i]
                b1, b2 = st.columns(2)
                with b1:
                    bx = st.slider("ឆ្វេង (%)", 0, 95, d[0], key=f"bx{i}")
                with b2:
                    by = st.slider("ពីលើ (%)", 0, 95, d[1], key=f"by{i}")
                b3, b4 = st.columns(2)
                with b3:
                    bw = st.slider("ទទឹង (%)", 3, 100, d[2], key=f"bw{i}")
                with b4:
                    bh = st.slider("កម្ពស់ (%)", 3, 100, d[3], key=f"bh{i}")
                bs = st.slider("កម្លាំង Blur", 5, 60, 25, key=f"bs{i}")
                t0 = t1 = None
                if not st.checkbox("Blur ពេញមួយវីដេអូ", value=True, key=f"ball{i}"):
                    t1c, t2c = st.columns(2)
                    with t1c:
                        t0 = st.number_input("ចាប់ពី (វិនាទី)", min_value=0.0, value=0.0, step=0.5, key=f"bt0{i}")
                    with t2c:
                        t1 = st.number_input("ដល់ (វិនាទី)", min_value=0.5, value=5.0, step=0.5, key=f"bt1{i}")
                bw = min(bw, 100 - bx)
                bh = min(bh, 100 - by)
                blur_list.append({"x": bx / 100.0, "y": by / 100.0, "w": bw / 100.0, "h": bh / 100.0,
                                  "sigma": bs, "t0": t0, "t1": t1})
    if logo_file is not None or blur_list:
        fx_settings = {
            "blurs": blur_list,
            "logo_bytes": logo_file.getvalue() if logo_file is not None else None,
            "logo_x": logo_x / 100.0, "logo_y": logo_y / 100.0,
            "logo_size": logo_size, "logo_opacity": logo_op / 100.0,
            "logo_color": logo_tint,
        }
    with prev_fx:
        aspect = st.radio("ទម្រង់មើលជាមុន", ["16:9", "9:16", "1:1"], horizontal=True, key="fx_aspect")
        render_fx_preview(aspect, logo_preview_data(logo_file.getvalue()) if logo_file is not None else None,
                          logo_x, logo_y, logo_size, logo_op / 100.0, logo_tint, blur_list)
        if logo_file is None and not blur_list:
            st.caption("Upload logo ឬបន្ថែមកន្លែង Blur ដើម្បីមើលជាមុន។ បើមិនប្រើ វីដេអូមិនមានការផ្លាស់ប្តូរទេ។")

# ============================ បញ្ជីវីដេអូ ============================
items = []
too_many = False
if uploaded_files:
    # ឯកសារលើស ១០០MB មិនអនុញ្ញាតទេ (មិនបង្ហាញអក្សរ — គ្រាន់តែមិនទទួល)
    uploaded_files = [f for f in uploaded_files if f.size <= MAX_UPLOAD_MB * 1024 * 1024]
    _kept, _sum = [], 0
    for f in uploaded_files:
        if _sum + f.size > MAX_UPLOAD_MB * 1024 * 1024:
            continue
        _kept.append(f)
        _sum += f.size
    uploaded_files = _kept
    too_many = len(uploaded_files) > MAX_VIDEOS
    for f in uploaded_files[:MAX_VIDEOS]:
        items.append({"name": f.name, "file": f, "url": None})
else:
    lines = extract_links(link_text)
    _cache = st.session_state.get("link_cache", {})
    lines = [u for u in lines if _cache.get(u, {}).get("ok")]
    too_many = len(lines) > MAX_VIDEOS
    for i, url in enumerate(lines[:MAX_VIDEOS], start=1):
        items.append({"name": f"វីដេអូទី {i}", "file": None, "url": url, "cached": _cache[url]["path"]})

# ============================ ប៊ូតុងចាប់ផ្តើម (ជាប់ខាងក្រោម) ============================
run = False
with start_slot:
    if busy:
        st.button("⏳ កំពុងធ្វើការ... មើលនៅផ្ទាំង ⬇️", disabled=True, use_container_width=True)
    elif not items:
        st.button("📁 សូមជ្រើសវីដេអូជាមុនសិន", disabled=True, use_container_width=True)
    else:
        label = "✨ ចាប់ផ្តើមបង្កើតវីដេអូ"
        if len(items) > 1:
            label += f" ({len(items)})"
        run = st.button(label, type="primary", use_container_width=True)
    if too_many:
        st.caption(f"⚠️ ធ្វើបានត្រឹម {MAX_VIDEOS} វីដេអូដំបូង។")

if link_translate and items and not busy:
    run = True

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
        "gemini_key": effective_gemini_key(), "groq_key": effective_groq_key(), "fx": fx_settings,
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
        "narrate_on": False, "review_on": False,
        "style": {"align": POS_MAP[pos_pick], "bold": bold_, "italic": italic_, "box": BOX_OPTIONS[box_pick]},
    }
    old = st.session_state.get("job")
    if old:
        shutil.rmtree(old.folder, ignore_errors=True)
        st.session_state.pop("job", None)
        old = None
        gc.collect()
    job_folder = tempfile.mkdtemp(prefix="kac_")
    job_items = []
    for idx, it in enumerate(items, start=1):
        if it["file"] is not None:
            item = new_item(it["name"], url=it["url"])
            p = os.path.join(job_folder, f"upload_{idx}.bin")
            with open(p, "wb") as f:
                f.write(it["file"].getbuffer())
            item["path"] = p
            job_items.append(item)
        elif it.get("cached") and os.path.isfile(it["cached"]):
            with st.spinner(f"កំពុងរៀបចំវីដេអូទី {idx}..."):
                parts = split_video_parts(it["cached"], job_folder, idx)
            if parts:
                for k, pp in enumerate(parts, start=1):
                    item = new_item(f"{it['name']} · ផ្នែក {k}/{len(parts)}")
                    item["path"] = pp
                    job_items.append(item)
            else:
                item = new_item(it["name"], url=it["url"])
                p = os.path.join(job_folder, f"upload_{idx}.bin")
                link_or_copy(it["cached"], p)
                item["path"] = p
                job_items.append(item)
        else:
            job_items.append(new_item(it["name"], url=it["url"]))
    for _k, _it in enumerate(job_items):
        _it["seq"] = _k
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
            job.zip = build_zip(job.items, job.folder)
            job.zip_done = True
        reviewing = job.reviewing()
        refresh = REFRESH_SECONDS if (running and not reviewing) else None
        st.fragment(run_every=refresh)(work_area)(job, running, reviewing)
        st.markdown('<div id="download-area"></div>', unsafe_allow_html=True)
        st.fragment(run_every=(6 if refresh else None))(download_area)(job)
        if not running:
            if st.button("🗑 លុបលទ្ធផលទាំងអស់"):
                shutil.rmtree(job.folder, ignore_errors=True)
                st.session_state.pop("job", None)
                gc.collect()
                st.rerun()
