import os
import io
import re
import json
import gc
import time
import uuid
import hmac
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
MAINTENANCE_MODE = False
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
.stApp { background: radial-gradient(circle at 50% 0%, #E4DCFF 0%, #F4F7FF 60%) !important; }
header, [data-testid="stToolbar"], [data-testid="stSidebar"] { display: none !important; }
.kvai-maint {
  max-width: 460px; margin: 18vh auto 0; padding: 36px 26px; text-align: center;
  border: 1px solid rgba(177,60,255,.45); border-radius: 26px;
  background: rgba(255,255,255,.95); box-shadow: 0 8px 36px rgba(100,80,200,.18);
  font-family: 'Kantumruy Pro', 'Battambang', sans-serif; color: #1F2A44;
}
.kvai-maint .ic { font-size: 64px; line-height: 1; animation: kvai-spin 3.2s linear infinite; display: inline-block; }
.kvai-maint h1 { font-size: 28px; margin: 18px 0 8px; color: #1F2A44; }
.kvai-maint p { font-size: 17px; line-height: 1.7; margin: 6px 0; color: #44506E; }
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
#  THEME (Khmer Video AI — light)
# =====================================================================
for _k, _v in {
    "theme.base": "dark",
    "theme.primaryColor": "#FF2DAA",
    "theme.backgroundColor": "#070B22",
    "theme.secondaryBackgroundColor": "#10183D",
    "theme.textColor": "#F5F7FF",
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
  --ink: #1F2A44;
  --soft: #55627F;
  --bg: #F4F7FF;
  --card: #FFFFFF;
  --card2: #F1F5FF;
  --line: rgba(80,100,190,.25);
  --p1: #7C3AED;
  --p2: #2563EB;
  --gold: #B45309;
  --r-lg: 20px;
  --r-md: 14px;
  --r-sm: 12px;
}

#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
.stDeployButton, [data-testid="stStatusWidget"], [class*="viewerBadge"],
[data-testid="manage-app-button"] { display: none !important; }

html, body, .stApp, [data-testid="stAppViewContainer"] {
  background: radial-gradient(900px 480px at 15% -8%, #E4DCFF 0%, rgba(244,247,255,0) 60%), #F4F7FF !important;
  color: var(--ink);
  font-family: 'Kantumruy Pro', 'Noto Sans Khmer', 'Battambang', system-ui, sans-serif !important;
  color-scheme: light;
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
  font-weight: 800 !important; line-height: 1.2 !important; color: var(--ink) !important;
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
.kvai-nav a:hover { color: var(--ink) !important; }

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
  background: rgba(255,255,255,.94) !important;
  border: 1px solid var(--line) !important;
  border-radius: var(--r-lg) !important;
  box-shadow: 0 6px 22px rgba(70,90,170,.14);
  padding: 6px 4px;
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlockBorderWrapper"] {
  box-shadow: none; background: #F7F9FF !important;
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
  background: #FFFFFF !important; color: var(--ink) !important;
}
[data-baseweb="popover"] li:hover { background: rgba(124,58,237,.12) !important; }

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
  border: 1.5px solid #8C97C8 !important;
  background-color: var(--card2) !important;
}
[data-testid="stCheckbox"] label:has(input:checked) > span:first-child,
[data-baseweb="checkbox"]:has(input:checked) > span:first-child {
  background: linear-gradient(135deg, var(--p1), var(--p2)) !important;
  border-color: transparent !important;
}
[data-testid="stToggle"] label > div:first-child { background: #C3CBE6 !important; }
[data-testid="stToggle"] label:has(input:checked) > div:first-child {
  background: linear-gradient(90deg, var(--p1), var(--p2)) !important;
}

/* ---------- Slider ---------- */
[data-testid="stSlider"] [role="slider"] { background: #fff !important; border-color: var(--p1) !important; }
[data-testid="stSlider"] [data-testid="stThumbValue"] { color: var(--ink) !important; }
[data-testid="stSlider"] [data-testid="stTickBarMin"], [data-testid="stSlider"] [data-testid="stTickBarMax"] { color: var(--soft) !important; }

/* ---------- Uploader ---------- */
[data-testid="stFileUploaderDropzone"] {
  background: rgba(124,58,237,.06);
  border: 2px dashed var(--p2);
  border-radius: var(--r-lg);
  padding: 22px 16px;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--p1); background: rgba(124,58,237,.12); }
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
.stButton > button:disabled { background: #E3E8F5 !important; color: #7A85A6 !important; box-shadow: none; transform: none; }

/* ---------- Progress ---------- */
[data-testid="stProgress"] > div > div { background: #E3E8F5 !important; border-radius: 999px; }
[data-testid="stProgress"] > div > div > div { background: linear-gradient(90deg, var(--p1), var(--p2)) !important; border-radius: 999px; }

/* ---------- Metrics ---------- */
[data-testid="stMetric"] {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 12px 14px;
}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * { font-weight: 800; color: var(--ink) !important; }
[data-testid="stMetricLabel"] p { color: var(--soft) !important; font-weight: 500; }

/* ---------- Alerts ---------- */
[data-testid="stAlert"] { border-radius: var(--r-md); border: none; }
[data-testid="stAlert"] * { color: var(--ink) !important; }

/* ---------- Expander ---------- */
[data-testid="stExpander"] {
  background: #FFFFFF;
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

/* ---------- Light theme extras: input / code / placeholder ---------- */
.stTextInput input, .stNumberInput input, [data-baseweb="input"], [data-baseweb="input"] > div,
[data-baseweb="base-input"] {
  background: var(--card2) !important; color: var(--ink) !important;
  border-color: var(--line) !important; border-radius: var(--r-sm) !important;
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder { color: #7A85A6 !important; opacity: 1; }
[data-testid="stCodeBlock"] pre, .stCode pre { background: #EEF2FF !important; }
[data-testid="stCodeBlock"] code, .stCode code { color: #1F2A44 !important; }
[data-testid="stFileUploaderDropzone"] { background: rgba(124,58,237,.06) !important; }
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
  background: linear-gradient(180deg, rgba(244,247,255,0), #F4F7FF 35%);
}
.st-key-startbar .stButton > button { min-height: 52px; }
</style>
"""


def apply_theme():
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    st.markdown(COMPACT_CSS, unsafe_allow_html=True)


LANDSCAPE_NEON_CSS = """
<style>
:root{--ink:#F5F7FF;--soft:#B9C7F5;--bg:#070B22;--card:#10183D;--card2:#151F4B;--line:rgba(91,184,255,.42);--p1:#FF2DAA;--p2:#16CFFF;--gold:#FFD34E}
html,body,.stApp,[data-testid="stAppViewContainer"]{background:radial-gradient(ellipse at 8% 5%,rgba(255,34,170,.23),transparent 34%),radial-gradient(ellipse at 92% 8%,rgba(0,213,255,.22),transparent 34%),linear-gradient(135deg,#05091D,#10143B 48%,#080D29)!important;color:#F5F7FF!important}
.stApp:before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;background:linear-gradient(110deg,transparent,rgba(20,210,255,.04),transparent);background-size:220% 100%;animation:kvai-light-run 8s linear infinite}
@keyframes kvai-light-run{from{background-position:200% 0}to{background-position:-20% 0}}
.block-container{max-width:1600px!important;padding:.5rem .8rem 5rem!important;position:relative;z-index:1}
.stApp p,.stApp label,.stApp h1,.stApp h2,.stApp h3,.stApp li,.stApp [data-testid="stMarkdownContainer"],[data-testid="stWidgetLabel"] p{color:#F5F7FF!important}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:#B9C7F5!important}
.kvai-head{padding:8px 13px;border:1px solid rgba(65,195,255,.45);border-radius:18px;background:linear-gradient(105deg,rgba(255,45,170,.2),rgba(14,26,72,.94),rgba(22,207,255,.17));box-shadow:0 0 22px rgba(22,207,255,.15)}
.kvai-logo{background:linear-gradient(135deg,#FF2DAA,#7B42FF,#16CFFF)!important;box-shadow:0 0 22px rgba(255,45,170,.5)!important}
.kvai-title h1{color:white!important;text-shadow:0 0 16px rgba(22,207,255,.5)}
.kvai-title h1 span{background:linear-gradient(90deg,#FF55C8,#43E7FF,#FFE36A);-webkit-background-clip:text;background-clip:text;color:transparent!important}
.kvai-badge{color:#FFE36A!important;background:rgba(255,211,78,.12)!important;border-color:#FFD34E!important}
[data-baseweb="tab-list"]{display:flex!important;gap:5px!important;padding:5px!important;background:#080F30!important;border:1px solid rgba(70,190,255,.45)!important}
button[data-baseweb="tab"]{flex:1 1 0!important;min-width:max-content!important;height:43px!important;border:1px solid rgba(120,150,255,.22)!important;border-radius:12px!important;background:linear-gradient(145deg,#18234F,#101735)!important;color:#DCE7FF!important}
button[data-baseweb="tab"][aria-selected="true"]{background:linear-gradient(110deg,#F52AA7,#783BFF,#08BFEF)!important;box-shadow:0 0 17px rgba(211,45,255,.42)!important;color:white!important}
button[data-baseweb="tab"] p{color:inherit!important;font-weight:800!important;white-space:nowrap}
div[data-testid="stVerticalBlockBorderWrapper"]{background:linear-gradient(145deg,rgba(23,34,82,.97),rgba(10,17,48,.98))!important;border:1px solid rgba(75,190,255,.38)!important;border-radius:16px!important;box-shadow:0 7px 24px rgba(0,0,0,.22)!important}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlockBorderWrapper"]{background:rgba(25,36,83,.65)!important}
[data-baseweb="select"]>div,.stTextInput input,.stNumberInput input,.stTextArea textarea,[data-baseweb="textarea"]>div{background:#0C1538!important;color:white!important;border:1px solid #3B8FC8!important}
[data-baseweb="select"] *{color:white!important}
[data-baseweb="popover"] ul,[data-baseweb="popover"] li,[data-baseweb="menu"]{background:#101A43!important;color:white!important}
[data-testid="stFileUploaderDropzone"]{background:rgba(28,50,111,.65)!important;border:2px dashed #20D7FF!important;box-shadow:inset 0 0 20px rgba(22,207,255,.08)}
[data-testid="stFileUploaderDropzone"] *{color:white!important}
.stButton>button,.stDownloadButton>button{background:linear-gradient(145deg,#172451,#101735)!important;color:white!important;border:1px solid rgba(68,204,255,.65)!important;border-radius:12px!important;min-height:44px!important}
.stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"]{background:linear-gradient(100deg,#FF279F,#853CFF,#08C8EF)!important;color:white!important;border:0!important;box-shadow:0 0 20px rgba(211,45,255,.38)!important}
.stButton>button:hover,.stDownloadButton>button:hover{transform:translateY(-2px);border-color:#FFE36A!important;box-shadow:0 0 17px rgba(22,207,255,.35)!important}
[data-testid="stRadio"] label{background:#111D49!important;border-color:#3C75B5!important;color:white!important}
[data-testid="stRadio"] label:has(input:checked){background:linear-gradient(100deg,#E82CA9,#6745FF)!important}
[data-testid="stToggle"] label:has(input:checked)>div:first-child{background:linear-gradient(90deg,#FF2DAA,#16CFFF)!important}
[data-testid="stProgress"]>div>div>div{background:linear-gradient(90deg,#FF2DAA,#8B42FF,#16CFFF)!important}
[data-testid="stMetric"]{background:#111B43!important;border:1px solid #3C8FC5!important}
[data-testid="stMetricValue"],[data-testid="stMetricValue"] *{color:white!important}
[data-testid="stAlert"],[data-testid="stExpander"]{background:#111A40!important;border:1px solid #3B8FC8!important}
[data-testid="stVideo"] video{max-height:190px}
.kvai-prev{border-color:#27D9FF!important;box-shadow:0 0 20px rgba(22,207,255,.18)}
@media(orientation:landscape) and (max-height:600px){.block-container{padding:.25rem .55rem 4rem!important}.kvai-head{padding:5px 10px;margin-bottom:4px}.kvai-logo{width:34px;height:34px;font-size:19px}.kvai-title h1{font-size:1.12rem!important}.kvai-title p,.kvai-badge{font-size:.68rem}button[data-baseweb="tab"]{height:35px!important}[data-testid="stVerticalBlock"]{gap:.35rem!important}div[data-testid="stVerticalBlockBorderWrapper"]{padding:2px!important}[data-testid="stVideo"] video{max-height:115px}.kvai-prev{height:105px!important}.stButton>button,.stDownloadButton>button{min-height:35px!important}}
@media(max-width:700px){[data-baseweb="tab-list"]{overflow-x:auto!important}button[data-baseweb="tab"]{flex:0 0 auto!important;padding:0 9px!important}}
</style>
"""
def apply_neon_theme():
    st.markdown(LANDSCAPE_NEON_CSS, unsafe_allow_html=True)


# ---------- Neon cinematic dashboard polish (Angkor-inspired) ----------
CINEMATIC_DASHBOARD_CSS = """
<style>
:root{--ink:#F7F8FF;--soft:#D3DEFF;--bg:#05091F;--card:#091638;--line:rgba(44,213,255,.62);--p1:#FF1493;--p2:#00D9FF;--gold:#FFD84D}
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:radial-gradient(ellipse at 8% 8%,rgba(255,0,153,.22),transparent 28%),radial-gradient(ellipse at 92% 10%,rgba(0,190,255,.22),transparent 30%),linear-gradient(140deg,#020616,#10113D 50%,#06172E)!important;color:#fff!important}
.block-container{max-width:1800px!important;padding:.25rem .55rem 3.1rem!important}
.stApp p,.stApp label,.stApp h1,.stApp h2,.stApp h3,.stApp li,.stApp [data-testid="stMarkdownContainer"],[data-testid="stWidgetLabel"] p{color:#F7F8FF!important}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:#C4D2FF!important}
.kvai-head{position:relative;isolation:isolate;overflow:hidden;min-height:108px;margin:2px 0 7px!important;padding:12px 18px!important;border:1px solid rgba(42,220,255,.8)!important;border-radius:20px!important;background:linear-gradient(90deg,rgba(2,7,28,.92),rgba(4,15,42,.48) 52%,rgba(2,8,28,.72)),url("data:image/jpeg;base64,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") center 52%/cover no-repeat!important;box-shadow:0 0 25px rgba(0,195,255,.28),inset 0 0 24px rgba(0,195,255,.15)!important}
.kvai-head:before{content:"";position:absolute;z-index:-1;inset:0;background:linear-gradient(105deg,transparent 0%,rgba(255,20,147,.0) 28%,rgba(255,20,147,.52) 36%,transparent 43%,rgba(0,220,255,.5) 58%,transparent 67%);background-size:240% 100%;animation:kvai-light-run 5.5s linear infinite;mix-blend-mode:screen}
.kvai-head:after{content:"";position:absolute;z-index:-1;inset:0;background:repeating-linear-gradient(115deg,transparent 0 65px,rgba(0,220,255,.16) 66px 68px,transparent 69px 135px);background-size:220% 100%;animation:kvai-light-run 9s linear infinite;pointer-events:none}
@keyframes kvai-light-run{from{background-position:220% 0}to{background-position:-20% 0}}
.kvai-logo{background:linear-gradient(135deg,#FF1493,#843BFF,#00D9FF)!important;box-shadow:0 0 24px rgba(255,20,147,.7)!important}
.kvai-title h1{color:#fff!important;text-shadow:0 0 16px rgba(0,220,255,.75)!important}
.kvai-title h1 span{background:linear-gradient(90deg,#FF65C5,#00E5FF,#FFE36A)!important;-webkit-background-clip:text!important;background-clip:text!important}
.kvai-badge{background:rgba(5,13,39,.7)!important;border:1.5px solid #FFD84D!important;color:#FFE36A!important}
[data-baseweb="tab-list"]{display:flex!important;gap:5px!important;padding:4px!important;background:rgba(5,12,40,.96)!important;border:1px solid rgba(0,210,255,.55)!important;box-shadow:0 0 16px rgba(0,210,255,.16)}
button[data-baseweb="tab"]{flex:1 1 0!important;min-width:max-content!important;height:42px!important;border:1px solid rgba(87,165,255,.4)!important;border-radius:12px!important;background:linear-gradient(145deg,#17234F,#0A1435)!important;color:#EAF3FF!important}
button[data-baseweb="tab"][aria-selected="true"]{background:linear-gradient(105deg,#FF1493,#843BFF,#00CFFF)!important;box-shadow:0 0 18px rgba(255,20,147,.55)!important;color:white!important}
button[data-baseweb="tab"] p{color:inherit!important;font-weight:800!important;white-space:nowrap}
[data-baseweb="tab-panel"]{padding-top:.25rem!important}
div[data-testid="stVerticalBlockBorderWrapper"]{background:linear-gradient(145deg,rgba(15,29,75,.97),rgba(6,14,43,.98))!important;border:1px solid rgba(43,201,255,.55)!important;border-radius:15px!important;box-shadow:0 7px 22px rgba(0,0,0,.28),0 0 13px rgba(0,180,255,.1)!important;padding:5px!important}
[data-baseweb="select"]>div,.stTextInput input,.stNumberInput input,.stTextArea textarea,[data-baseweb="textarea"]>div{background:#091638!important;color:#fff!important;border:1px solid #328DC4!important}
[data-baseweb="select"] *{color:#fff!important}
[data-baseweb="popover"] ul,[data-baseweb="popover"] li,[data-baseweb="menu"]{background:#101A43!important;color:white!important}
[data-testid="stFileUploaderDropzone"]{background:linear-gradient(135deg,rgba(0,174,255,.16),rgba(174,30,255,.16))!important;border:2px dashed #00D9FF!important;box-shadow:inset 0 0 22px rgba(0,210,255,.13);padding:10px!important}
[data-testid="stFileUploaderDropzone"] *{color:#fff!important}
.stButton>button,.stDownloadButton>button{background:linear-gradient(145deg,#142451,#0A1538)!important;color:white!important;border:1px solid rgba(0,215,255,.7)!important;box-shadow:0 0 10px rgba(0,180,255,.15);min-height:38px!important}
.stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"]{background:linear-gradient(100deg,#FF1493,#853BFF,#00CFFF)!important;box-shadow:0 0 22px rgba(255,20,147,.48)!important}
.stButton>button:hover,.stDownloadButton>button:hover{box-shadow:0 0 22px rgba(0,220,255,.65)!important;border-color:#FFE36A!important;transform:translateY(-1px)}
[data-testid="stRadio"] label{background:#111D49!important;border-color:#328DC4!important;color:#fff!important;padding:5px 8px!important}
[data-testid="stRadio"] label:has(input:checked){background:linear-gradient(100deg,#FF1493,#743DFF)!important}
[data-testid="stMetric"]{background:#101B43!important;border:1px solid #328DC4!important}
[data-testid="stMetricValue"],[data-testid="stMetricValue"] *{color:#fff!important}
[data-testid="stAlert"],[data-testid="stExpander"]{background:#101A40!important;border:1px solid #328DC4!important}
.kvai-panel-title{display:flex;align-items:center;gap:9px;margin:0 0 7px;padding:7px 10px;border:1px solid rgba(0,210,255,.55);border-radius:13px;background:linear-gradient(100deg,rgba(255,20,147,.18),rgba(0,190,255,.16));font-weight:800;font-size:1.08rem;text-shadow:0 0 12px #00cfff}
.kvai-step{width:31px;height:31px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;font-weight:900;font-size:1rem;color:#fff;box-shadow:0 0 15px currentColor}
.kvai-step.pink{background:linear-gradient(135deg,#ff1493,#813cff)}.kvai-step.blue{background:linear-gradient(135deg,#00cfff,#176bff)}
.kvai-empty-preview{height:265px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;border:1px dashed #00d9ff;border-radius:16px;background:radial-gradient(circle at 50% 45%,rgba(0,200,255,.18),transparent 55%),linear-gradient(145deg,#0a1945,#060d28);text-align:center;color:#fff}
.kvai-empty-preview small{color:#a9c9f5}.kvai-play{width:64px;height:64px;display:grid;place-items:center;border-radius:50%;font-size:27px;background:linear-gradient(135deg,#ff1493,#773cff,#00cfff);box-shadow:0 0 25px #00cfff88}
.kvai-filmstrip{text-align:center;margin:8px 0;padding:7px;border-radius:10px;background:linear-gradient(90deg,#111b4a,#25105a,#102c54);border:1px solid #704cff;color:#fff;letter-spacing:7px}
[data-testid="stVideo"] video{max-height:290px!important;object-fit:contain;background:#020617;border:1px solid #00cfff;border-radius:12px}
.st-key-startbar{position:fixed!important;bottom:0!important;left:50%!important;transform:translateX(-50%)!important;width:min(100%,1500px)!important;z-index:999!important;background:linear-gradient(180deg,rgba(5,9,31,0),rgba(5,9,31,.97) 38%)!important;padding:8px 12px calc(7px + env(safe-area-inset-bottom))!important}
.st-key-startbar .stButton>button{min-height:46px!important;font-size:1.02rem!important}
@media (orientation:landscape) and (min-width:700px){
 html,body,.stApp,[data-testid="stAppViewContainer"]{height:100dvh!important;min-height:100dvh!important}
 [data-testid="stMain"]{height:100dvh!important;overflow:hidden!important}
 .block-container{height:100dvh!important;overflow:hidden!important;padding:.18rem .48rem 3.0rem!important}
 .kvai-head{min-height:82px!important;padding:7px 15px!important;margin:0 0 5px!important}
 .kvai-logo{width:42px!important;height:42px!important;font-size:22px!important}
 .kvai-title h1{font-size:1.32rem!important}.kvai-title p{font-size:.72rem!important}
 .kvai-badge{padding:4px 9px!important;font-size:.72rem!important}
 [data-baseweb="tab-list"]{padding:3px!important}
 button[data-baseweb="tab"]{height:36px!important}
 [data-testid="stVerticalBlock"]{gap:.28rem!important}
 [data-testid="stHorizontalBlock"]{gap:.45rem!important;flex-wrap:nowrap!important}
 [data-testid="stColumn"]{min-width:0!important}
 [data-baseweb="tab-panel"]{padding-top:.12rem!important}
 div[data-testid="stVerticalBlockBorderWrapper"]{padding:3px!important}
 [data-testid="stWidgetLabel"] p{font-size:.76rem!important;margin-bottom:1px!important}
 [data-testid="stFileUploaderDropzone"]{padding:5px!important;min-height:65px!important}
 [data-testid="stVideo"] video{max-height:210px!important}
 .kvai-empty-preview{height:210px!important}
 .stButton>button,.stDownloadButton>button{min-height:32px!important;font-size:.8rem!important}
 .st-key-startbar{padding:5px 10px calc(4px + env(safe-area-inset-bottom))!important}
 .st-key-startbar .stButton>button{min-height:38px!important}
}
@media(max-width:699px){[data-baseweb="tab-list"]{overflow-x:auto!important}button[data-baseweb="tab"]{flex:0 0 auto!important;padding:0 9px!important}}
</style>
"""



def render_header():
    st.markdown(
        """
        <div class="kvai-head">
          <div class="kvai-logo">🎬</div>
          <div class="kvai-title">
            <h1>Khmer <span>Video AI</span></h1>
            <p>បកប្រែវីដេអូ · បង្កើត Subtitle និងសំឡេងខ្មែរ ដោយ AI</p>
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
apply_neon_theme()
st.markdown(CINEMATIC_DASHBOARD_CSS, unsafe_allow_html=True)

# ---------- Final responsive polish: real full-page Angkor background + usable controls ----------
_ANGKOR_BG_URL = 'data:image/jpeg;base64,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'
FINAL_RESPONSIVE_CSS = f"""
<style>
/* Use the same Angkor scene as a real full-page background, not only the header banner. */
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMainBlockContainer"] {{
  background-color:#05091f !important;
  background-image:linear-gradient(115deg,rgba(2,6,24,.82),rgba(5,12,40,.72) 48%,rgba(3,8,29,.84)),
    url("{_ANGKOR_BG_URL}") !important;
  background-size:cover !important; background-position:center center !important;
  background-attachment:fixed !important; background-repeat:no-repeat !important;
  color:#f7f8ff !important;
}}
/* Moving neon beams and small glowing particles across the entire screen. */
.stApp::before {{
  content:""; position:fixed; inset:-20%; z-index:0; pointer-events:none;
  background:repeating-linear-gradient(112deg,transparent 0 13%,rgba(0,221,255,.075) 13.15%,transparent 13.45% 28%),
    linear-gradient(105deg,transparent 38%,rgba(255,35,175,.12) 49%,transparent 60%);
  background-size:180% 100%,220% 100%;
  animation:kvai-beam-run 10s linear infinite; opacity:.8;
}}
@keyframes kvai-beam-run {{ 0% {{background-position:180% 0,180% 0}} 100% {{background-position:-30% 0,-40% 0}} }}
/* Keep all Streamlit content above the animated background. */
[data-testid="stMain"] > div, .block-container {{position:relative;z-index:1}}
/* Compact header and remove the oversized blank gaps. */
.kvai-head {{min-height:82px !important;height:82px !important;max-height:82px !important;
  margin:1px 0 4px !important;padding:6px 13px !important;overflow:hidden !important;}}
.kvai-logo {{width:48px !important;height:48px !important;flex:0 0 48px !important;}}
.kvai-title h1 {{font-size:clamp(1.05rem,2.4vw,1.65rem) !important;}}
.kvai-title p {{font-size:clamp(.65rem,1.1vw,.85rem) !important;margin-top:1px !important;}}
[data-testid="stVerticalBlock"] {{gap:.35rem !important}}
[data-testid="stElementContainer"] {{margin-bottom:0 !important}}
/* Remove pale disabled button and the white-looking fixed footer. */
.st-key-startbar {{position:fixed !important;bottom:0 !important;left:50% !important;
  transform:translateX(-50%) !important;width:min(100%,1500px) !important;z-index:1000 !important;
  padding:5px 10px calc(5px + env(safe-area-inset-bottom)) !important;
  background:linear-gradient(180deg,rgba(3,8,29,0),rgba(3,8,29,.94) 35%,rgba(3,8,29,.98)) !important;
  border-top:1px solid rgba(0,220,255,.45) !important;box-shadow:0 -8px 28px rgba(0,0,0,.25) !important;
  backdrop-filter:blur(10px) !important;}}
.st-key-startbar [data-testid="stVerticalBlockBorderWrapper"],
.st-key-startbar [data-testid="stVerticalBlock"] {{background:transparent !important;border:0 !important;box-shadow:none !important;}}
.st-key-startbar .stButton>button,
.st-key-startbar .stButton>button:disabled {{
  min-height:42px !important;border:1px solid #18dfff !important;border-radius:13px !important;
  background:linear-gradient(100deg,#ff1493,#843bff,#00cfff) !important;
  color:#fff !important;opacity:1 !important;filter:none !important;
  box-shadow:0 0 18px rgba(0,207,255,.28),0 0 22px rgba(255,20,147,.2) !important;
}}
.st-key-startbar .stButton>button:disabled {{
  background:linear-gradient(100deg,rgba(255,20,147,.72),rgba(110,55,220,.78),rgba(0,170,220,.78)) !important;
  color:rgba(255,255,255,.94) !important;cursor:not-allowed !important;
}}
/* Inputs and cards remain dark; never let the Streamlit default light surface show through. */
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stExpander"],
[data-testid="stAlert"], [data-testid="stMetric"] {{background-color:rgba(7,18,53,.92) !important;}}
[data-baseweb="select"]>div, .stTextInput input, .stNumberInput input,
.stTextArea textarea, [data-baseweb="textarea"]>div {{background:#091638 !important;color:#fff !important;}}
@media (orientation:landscape) and (min-width:700px) {{
  html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"] {{height:100dvh !important;min-height:100dvh !important;}}
  [data-testid="stMain"] {{overflow:hidden !important;}}
  .block-container {{height:100dvh !important;max-width:1800px !important;
    overflow:hidden !important;padding:3px 10px 54px !important;}}
  .kvai-head {{height:76px !important;min-height:76px !important;max-height:76px !important;}}
  .kvai-logo {{width:42px !important;height:42px !important;flex-basis:42px !important;}}
  [data-baseweb="tab-list"] {{margin:2px 0 4px !important;padding:3px !important;}}
  button[data-baseweb="tab"] {{height:38px !important;}}
  [data-baseweb="tab-panel"] {{padding-top:2px !important;}}
  [data-testid="stVerticalBlock"] {{gap:.22rem !important;}}
  [data-testid="stHorizontalBlock"] {{gap:.4rem !important;flex-wrap:nowrap !important;}}
  [data-testid="stColumn"] {{min-width:0 !important;}}
  [data-testid="stWidgetLabel"] p {{font-size:.76rem !important;margin-bottom:0 !important;}}
  [data-testid="stFileUploaderDropzone"] {{min-height:56px !important;padding:4px !important;}}
  .stButton>button,.stDownloadButton>button {{min-height:34px !important;font-size:.78rem !important;}}
  .st-key-startbar .stButton>button {{min-height:38px !important;font-size:.9rem !important;}}
}}
@media (max-width:699px) {{
  .kvai-head {{height:auto !important;min-height:72px !important;max-height:none !important;}}
  .st-key-startbar {{width:100% !important;}}
}}
</style>
"""
st.markdown(FINAL_RESPONSIVE_CSS, unsafe_allow_html=True)

# ---------- Runtime usability fix: never clip Streamlit widgets ----------
# Previous CSS forced the whole app to 100dvh + overflow:hidden. On mobile
# landscape this clipped the tab panel and left controls visible but unusable.
USABILITY_FIX_CSS = """
<style>
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMainBlockContainer"] {
  height: auto !important; min-height: 100% !important;
  overflow-x: hidden !important; overflow-y: auto !important;
}
[data-testid="stMain"] { overflow: visible !important; }
.block-container {
  height: auto !important; min-height: 100dvh !important;
  max-height: none !important; overflow: visible !important;
  padding: 4px 10px 14px !important;
}
[data-baseweb="tab-panel"] {
  height: auto !important; max-height: none !important;
  overflow: visible !important; padding-bottom: 8px !important;
}
/* Keep the action button in normal layout so it cannot cover controls. */
.st-key-startbar {
  position: relative !important; inset: auto !important;
  transform: none !important; width: 100% !important;
  z-index: 5 !important; margin: 8px 0 4px !important;
  padding: 6px 8px calc(6px + env(safe-area-inset-bottom)) !important;
  background: linear-gradient(90deg,rgba(255,20,147,.22),rgba(8,18,55,.96),rgba(0,210,255,.22)) !important;
  border: 1px solid rgba(0,220,255,.72) !important;
  border-radius: 16px !important; box-shadow: 0 0 18px rgba(0,190,255,.18) !important;
}
.st-key-startbar [data-testid="stVerticalBlockBorderWrapper"],
.st-key-startbar [data-testid="stVerticalBlock"] {
  background: transparent !important; border: 0 !important; box-shadow: none !important;
}
.st-key-startbar .stButton > button,
.st-key-startbar .stButton > button:disabled {
  min-height: 44px !important; opacity: 1 !important;
  color: #fff !important; border: 1px solid #19ddff !important;
  background: linear-gradient(100deg,#ff1493,#843bff,#00cfff) !important;
}
/* API warning should be a compact banner, not consume the whole first screen. */
[data-testid="stAlert"] {
  padding: 7px 12px !important; margin: 4px 0 7px !important;
  border-radius: 12px !important; min-height: 0 !important;
}
[data-testid="stAlert"] p { font-size: .88rem !important; line-height: 1.35 !important; margin: 0 !important; }
/* Remove oversized gaps between header, orientation control and tabs. */
[data-testid="stVerticalBlock"] { gap: .35rem !important; }
[data-testid="stElementContainer"] { margin-bottom: 0 !important; }
@media (orientation: landscape) and (max-height: 700px) {
  .block-container { padding: 3px 8px 8px !important; }
  .kvai-head { height: 68px !important; min-height: 68px !important; max-height: 68px !important;
    margin: 0 0 3px !important; padding: 5px 10px !important; }
  .kvai-logo { width: 40px !important; height: 40px !important; flex-basis: 40px !important; }
  .kvai-title h1 { font-size: 1.15rem !important; }
  .kvai-title p { font-size: .68rem !important; }
  [data-baseweb="tab-list"] { margin: 2px 0 !important; padding: 3px !important; }
  button[data-baseweb="tab"] { height: 35px !important; }
  [data-testid="stWidgetLabel"] p { font-size: .74rem !important; }
  .stButton > button, .stDownloadButton > button { min-height: 34px !important; }
}
</style>
"""
st.markdown(USABILITY_FIX_CSS, unsafe_allow_html=True)


# ---------- Final landscape desktop-mode layout (last CSS wins) ----------
LANDSCAPE_DESKTOP_FINAL_CSS = """
<style>
/* Rich full-screen canvas with the Angkor artwork and animated neon beams. */
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMainBlockContainer"] {
  background-color:#05091d !important;
  background-color:#05091d !important;
  color:#f7f8ff !important;
}
/* The existing page background already embeds the Angkor image in FINAL_RESPONSIVE_CSS;
   keep it visible and animate light streaks above it without blocking clicks. */
.stApp::before {
  content:""; position:fixed; inset:0; z-index:0; pointer-events:none;
  background:repeating-linear-gradient(112deg,transparent 0 14%,rgba(0,220,255,.08) 14.1%,transparent 14.5% 29%),
    linear-gradient(105deg,transparent 34%,rgba(255,25,170,.13) 48%,transparent 61%);
  background-size:220% 100%,240% 100%; animation:kvai-final-beams 8s linear infinite;
}
@keyframes kvai-final-beams { from {background-position:220% 0,200% 0} to {background-position:-20% 0,-40% 0} }
[data-testid="stMain"] > div, .block-container {position:relative;z-index:1}
[data-testid="stHeader"], [data-testid="stToolbar"] {background:transparent !important}
.block-container {max-width:1800px !important;padding:3px 9px 54px !important}
.kvai-head {height:70px !important;min-height:70px !important;max-height:70px !important;
  margin:0 0 3px !important;padding:5px 12px !important}
.kvai-logo {width:43px !important;height:43px !important;flex:0 0 43px !important}
.kvai-title h1 {font-size:clamp(1.05rem,2vw,1.55rem) !important}
.kvai-title p {font-size:.72rem !important;margin:0 !important}
.kvai-badge {padding:4px 10px !important;font-size:.72rem !important}
/* Compact orientation button: no large blank band under the header. */
iframe[title="streamlit.components.v1.html"] {max-height:34px !important}
[data-baseweb="tab-list"] {display:flex !important;gap:4px !important;padding:3px !important;margin:2px 0 4px !important}
button[data-baseweb="tab"] {height:37px !important;min-width:0 !important;padding:0 9px !important}
button[data-baseweb="tab"] p {font-size:.82rem !important;white-space:nowrap !important}
[data-baseweb="tab-panel"] {padding:2px 0 6px !important}
[data-testid="stVerticalBlock"] {gap:.28rem !important}
[data-testid="stElementContainer"] {margin-bottom:0 !important}
[data-testid="stHorizontalBlock"] {gap:.45rem !important;flex-wrap:nowrap !important}
[data-testid="stColumn"] {min-width:0 !important}
.kvai-panel-title {margin:0 0 4px !important;padding:5px 8px !important;font-size:.92rem !important}
.kvai-step {width:25px !important;height:25px !important;font-size:.82rem !important}
div[data-testid="stVerticalBlockBorderWrapper"] {padding:3px 4px !important;border-radius:12px !important}
[data-testid="stWidgetLabel"] p, .stApp label {font-size:.76rem !important;margin-bottom:1px !important}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {font-size:.68rem !important;line-height:1.2 !important;margin:1px 0 !important}
[data-testid="stFileUploaderDropzone"] {min-height:48px !important;padding:3px 7px !important}
[data-testid="stFileUploaderDropzoneInstructions"] {padding:0 !important}
[data-testid="stVideo"] video {max-height:145px !important;object-fit:contain !important}
.kvai-empty-preview {height:145px !important;gap:5px !important}
.kvai-play {width:42px !important;height:42px !important;font-size:20px !important}
.kvai-filmstrip {margin:3px 0 !important;padding:3px !important;letter-spacing:3px !important}
[data-baseweb="select"] > div {min-height:34px !important}
.stTextInput input, .stNumberInput input {min-height:32px !important}
.stButton > button, .stDownloadButton > button {min-height:34px !important;padding:3px 8px !important;font-size:.78rem !important}
[data-testid="stRadio"] [role="radiogroup"] {gap:4px !important}
[data-testid="stRadio"] label {padding:4px 7px !important;font-size:.72rem !important}
[data-testid="stToggle"] {padding:0 !important}
[data-testid="stSlider"] {padding-top:0 !important;padding-bottom:0 !important}
[data-testid="stAlert"] {padding:5px 9px !important;margin:2px 0 !important}
[data-testid="stAlert"] p {font-size:.72rem !important;line-height:1.2 !important}
/* The start action stays visible, but its footer never covers the controls. */
.st-key-startbar {position:fixed !important;left:50% !important;bottom:0 !important;
  transform:translateX(-50%) !important;width:min(100%,1800px) !important;z-index:1000 !important;
  margin:0 !important;padding:4px 9px calc(4px + env(safe-area-inset-bottom)) !important;
  background:linear-gradient(180deg,rgba(4,9,30,0),rgba(4,9,30,.96) 35%) !important;
  border-top:1px solid rgba(0,220,255,.5) !important;backdrop-filter:blur(9px) !important}
.st-key-startbar [data-testid="stVerticalBlockBorderWrapper"],
.st-key-startbar [data-testid="stVerticalBlock"] {background:transparent !important;border:0 !important;box-shadow:none !important}
.st-key-startbar .stButton > button {min-height:39px !important;font-size:.9rem !important;
  background:linear-gradient(100deg,#ff1493,#843bff,#00cfff) !important;color:#fff !important;
  border:1px solid #20dfff !important;box-shadow:0 0 15px rgba(0,207,255,.3) !important}
@media (orientation:landscape) and (max-height:600px) {
  .block-container {padding:2px 7px 47px !important}
  .kvai-head {height:58px !important;min-height:58px !important;max-height:58px !important;padding:4px 9px !important}
  .kvai-logo {width:36px !important;height:36px !important;flex-basis:36px !important}
  .kvai-title h1 {font-size:1.08rem !important}
  .kvai-title p {display:none !important}
  .kvai-badge {font-size:.64rem !important;padding:3px 7px !important}
  button[data-baseweb="tab"] {height:31px !important;padding:0 6px !important}
  button[data-baseweb="tab"] p {font-size:.7rem !important}
  .kvai-panel-title {font-size:.78rem !important;padding:3px 6px !important}
  .kvai-step {width:21px !important;height:21px !important}
  [data-testid="stVideo"] video, .kvai-empty-preview {max-height:105px !important;height:105px !important}
  [data-testid="stFileUploaderDropzone"] {min-height:38px !important;padding:1px 5px !important}
  [data-testid="stWidgetLabel"] p, .stApp label {font-size:.67rem !important}
  .stButton > button, .stDownloadButton > button {min-height:29px !important;font-size:.68rem !important}
  .st-key-startbar .stButton > button {min-height:34px !important}
}
/* Portrait stays naturally scrollable and usable; landscape is compact desktop mode. */
@media (orientation:portrait) {
  .block-container {padding-bottom:16px !important}
  .st-key-startbar {position:relative !important;left:auto !important;bottom:auto !important;transform:none !important;width:100% !important}
}
</style>
"""
st.markdown(LANDSCAPE_DESKTOP_FINAL_CSS, unsafe_allow_html=True)


# ---------- Mobile landscape: fit the dashboard to one screen ----------
MOBILE_LANDSCAPE_FIT_CSS = """
<style>
@media (orientation: landscape) and (min-width: 600px) and (max-height: 900px) {
  /* Other tabs remain naturally usable; the Home dashboard is locked to one screen below. */
  html, body, .stApp, [data-testid="stAppViewContainer"],
  [data-testid="stMain"], [data-testid="stMainBlockContainer"] {
    height: auto !important; min-height: 100dvh !important;
    overflow-x: hidden !important; overflow-y: auto !important;
  }
  [data-testid="stHeader"], [data-testid="stToolbar"] { height: 0 !important; display: none !important; }
  [data-testid="stMain"] { overflow: visible !important; }
  .block-container {
    height: auto !important; min-height: 100dvh !important; max-height: none !important;
    overflow: visible !important; padding: 2px 7px 43px !important;
    max-width: 1800px !important;
  }
  .kvai-head {
    height: 54px !important; min-height: 54px !important; max-height: 54px !important;
    margin: 0 0 2px !important; padding: 3px 8px !important; gap: 7px !important;
    border-radius: 12px !important;
  }
  .kvai-logo { width: 34px !important; height: 34px !important; flex: 0 0 34px !important; font-size: 18px !important; }
  .kvai-title h1 { font-size: clamp(.9rem, 2.1vw, 1.25rem) !important; line-height: 1.05 !important; }
  .kvai-title p { font-size: .58rem !important; line-height: 1 !important; margin: 1px 0 0 !important; }
  .kvai-badge { padding: 3px 7px !important; font-size: .6rem !important; }
  iframe[title="streamlit.components.v1.html"] { height: 24px !important; max-height: 24px !important; }
  [data-baseweb="tab-list"] {
    display: flex !important; flex-wrap: nowrap !important; gap: 3px !important;
    padding: 2px !important; margin: 1px 0 3px !important; overflow: hidden !important;
  }
  button[data-baseweb="tab"] {
    flex: 1 1 0 !important; min-width: 0 !important; height: 30px !important;
    padding: 0 2px !important; border-radius: 7px !important;
  }
  button[data-baseweb="tab"] p {
    font-size: clamp(.55rem, .9vw, .7rem) !important;
    white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important;
  }
  [data-baseweb="tab-panel"] {
    height: auto !important; max-height: none !important;
    overflow: visible !important; padding: 0 !important;
  }
  /* Home is a true one-screen dashboard: no page or panel scrolling. */
  html:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]),
  body:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]),
  html:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]) .stApp,
  body:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]) .stApp,
  html:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]) [data-testid="stAppViewContainer"],
  body:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]) [data-testid="stAppViewContainer"],
  html:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]) [data-testid="stMain"],
  body:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]) [data-testid="stMain"] {
    height: 100dvh !important; min-height: 100dvh !important; overflow: hidden !important;
  }
  html:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]) .block-container,
  body:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]) .block-container {
    height: 100dvh !important; min-height: 0 !important; max-height: 100dvh !important;
    overflow: hidden !important;
  }
  html:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]) [data-baseweb="tab-panel"],
  body:has(button[data-baseweb="tab"]:first-of-type[aria-selected="true"]) [data-baseweb="tab-panel"] {
    height: calc(100dvh - 125px) !important; max-height: calc(100dvh - 125px) !important;
    overflow: hidden !important;
  }
  [data-testid="stVerticalBlock"] { gap: .18rem !important; }
  [data-testid="stElementContainer"] { margin-bottom: 0 !important; }
  [data-testid="stHorizontalBlock"] { gap: .3rem !important; flex-wrap: nowrap !important; }
  [data-testid="stColumn"] { min-width: 0 !important; }
  .kvai-panel-title { margin: 0 0 2px !important; padding: 3px 6px !important; font-size: .72rem !important; }
  .kvai-step { width: 19px !important; height: 19px !important; font-size: .65rem !important; }
  div[data-testid="stVerticalBlockBorderWrapper"] { padding: 2px 3px !important; border-radius: 9px !important; }
  [data-testid="stWidgetLabel"] p, .stApp label { font-size: .62rem !important; margin: 0 !important; }
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
    font-size: .56rem !important; line-height: 1.05 !important; margin: 0 !important;
  }
  [data-testid="stFileUploaderDropzone"] { min-height: 35px !important; padding: 1px 4px !important; }
  [data-testid="stFileUploaderDropzoneInstructions"] { padding: 0 !important; }
  [data-testid="stFileUploaderDropzoneInstructions"] span,
  [data-testid="stFileUploaderDropzoneInstructions"] small { font-size: .58rem !important; }
  .stTextArea textarea { min-height: 42px !important; height: 42px !important; }
  [data-testid="stVideo"] video, .kvai-empty-preview { max-height: 92px !important; height: 92px !important; }
  .kvai-play { width: 34px !important; height: 34px !important; font-size: 16px !important; }
  .kvai-filmstrip { display: none !important; }
  [data-baseweb="select"] > div { min-height: 28px !important; }
  .stTextInput input, .stNumberInput input { min-height: 27px !important; }
  .stButton > button, .stDownloadButton > button {
    min-height: 28px !important; padding: 2px 5px !important; font-size: .62rem !important;
  }
  [data-testid="stRadio"] [role="radiogroup"] { gap: 2px !important; }
  [data-testid="stRadio"] label { padding: 2px 5px !important; font-size: .6rem !important; }
  [data-testid="stToggle"], [data-testid="stCheckbox"], [data-testid="stSlider"] { padding: 0 !important; }
  [data-testid="stExpander"] summary { min-height: 26px !important; padding: 3px 7px !important; }
  [data-testid="stExpander"] summary p { font-size: .65rem !important; }
  [data-testid="stAlert"] { padding: 3px 6px !important; margin: 1px 0 !important; }
  [data-testid="stAlert"] p { font-size: .62rem !important; line-height: 1.1 !important; }
  .st-key-startbar {
    position: fixed !important; left: 50% !important; bottom: 0 !important;
    transform: translateX(-50%) !important; width: 100% !important; z-index: 1000 !important;
    margin: 0 !important; padding: 3px 7px !important; border-radius: 0 !important;
    background: linear-gradient(90deg,rgba(255,20,147,.18),rgba(4,9,30,.97),rgba(0,210,255,.18)) !important;
  }
  .st-key-startbar .stButton > button { min-height: 33px !important; font-size: .78rem !important; }
}
@media (orientation: landscape) and (min-width: 600px) and (max-height: 520px) {
  .kvai-head { height: 43px !important; min-height: 43px !important; max-height: 43px !important; }
  .kvai-logo { width: 28px !important; height: 28px !important; flex-basis: 28px !important; }
  .kvai-title p, .kvai-badge { display: none !important; }
  iframe[title="streamlit.components.v1.html"] { height: 19px !important; max-height: 19px !important; }
  button[data-baseweb="tab"] { height: 26px !important; }
  [data-baseweb="tab-panel"] { height: calc(100dvh - 105px) !important; max-height: calc(100dvh - 105px) !important; }
  [data-testid="stVideo"] video, .kvai-empty-preview { max-height: 72px !important; height: 72px !important; }
  .st-key-startbar .stButton > button { min-height: 28px !important; }
}
</style>
"""
st.markdown(MOBILE_LANDSCAPE_FIT_CSS, unsafe_allow_html=True)


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

# Gemini models are no longer used. xKiro handles text translation; Groq handles STT.
PREFERRED_MODELS = []

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
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
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


class _HtmlPage(Exception):
    pass


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
                raise _HtmlPage()
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
    except _HtmlPage:
        _download_with_ytdlp(url, path, progress)
        return
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
        k = k.strip().strip("[]()").strip('"').strip("'").strip("[]()").strip('"').strip("'")
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
_GROQ_LIMIT = {"t": 0.0}   # ម៉ោងចុងក្រោយដែលជួប 429 (អស់កូតា)
_MODEL_GOOD = {}     # provider -> ម៉ូដែលដែលបានជោគជ័យចុងក្រោយ


def model_cool(model, error_text):
    """កត់ត្រាថ្នាក់ម៉ូដែលខូច/ពេញកូតា ដើម្បីប្តូរទៅម៉ូដែលផ្សេងដោយស្វ័យប្រវត្តិ។"""
    low = str(error_text).lower()
    if "429" in low or "rate limit" in low:
        _GROQ_LIMIT["t"] = time.time()
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


_LEAK_TAG_RE = re.compile(r"\[\s*(?:speaker|max|SPEAKER)[^\]]*\]\s*", re.I)


def spk_tag(g):
    """ស្លាកភេទអ្នកនិយាយ ដែលផ្ញើទៅអ្នកបកប្រែ (M=ប្រុស, F=ស្រី)។ មិនស្គាល់ = គ្មានស្លាក។"""
    return {"M": "[speaker: male] ", "F": "[speaker: female] "}.get(g, "")


def _spk_differs(fn, a0, a1, b0, b1):
    """True ប្រសិនបើឃ្លាពីរមានអ្នកនិយាយផ្សេងភេទគ្នាច្បាស់លាស់ (មិនត្រូវបញ្ចូលគ្នា)។"""
    if fn is None:
        return False
    try:
        ga, gb = fn(a0, a1), fn(b0, b1)
    except Exception:
        return False
    return bool(ga and gb and ga != gb)


def clean_translation(out):
    out = str(out or "")
    out = _LEAK_TAG_RE.sub("", out)
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


TRANS_SYSTEM_FULL = (
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
    "(14) ACCURACY: before answering each line, check who does what to whom, when, how many and why; keep every negation, question, condition and number exactly. "
    "Chinese/foreign personal names: transliterate by SOUND the same way every time across all lines, never translate their meaning. Kinship words (older brother, aunt, boss, teacher) must match the real relationship. "
    "Chinese address terms depend on the relationship: 哥/大哥/姐 = បង, 弟/妹 = ប្អូន, 老板 = ថៅកែ, 老公 = ប្តី, 老婆 = ប្រពន្ធ, 妈 = ម៉ែ/ម៉ាក់, 爸 = ប៉ា/ឪពុក, 少爷/小姐 = ប្រើតាមបរិបទ; choose the Khmer word a real family or friend would use, never a stiff dictionary word. "
    "Preserve the feeling: crying, pleading, shouting, laughing and sighing lines must sound emotional in Khmer (short broken sentences for panic, soft long sentences for sadness) while still being one clean grammatical sentence. "
    "If an English hint and the original disagree, the original wins. If a word is unclear choose the most common meaning that fits the scene, never invent or censor content, and never output nonsense words. "
    "(15) SPEAKER GENDER: a line may start with the tag [speaker: male] or [speaker: female]. It is the TRUE gender of the person speaking, "
    "measured from the audio, so trust it over any guess from the text. Write Khmer that fits that speaker: the polite answer yes is បាទ for a man and ចាស for a woman; "
    "formal I is ខ្ញុំបាទ for a man and នាងខ្ញុំ for a woman (ordinary I is ខ្ញុំ for both); a man ends polite sentences with បាទ and a woman with ចាស. "
    "Never give a woman male-only words or a man female-only words, and keep each speaker consistent across all lines. If a line has no tag, stay gender-neutral. Never output the tag. "
    "Output Khmer script only (no English, no Chinese, no romanization). "
    "Return JSON {\"translations\": [...]} with exactly one item per input, same order."
)


# លំនាំដើម = prompt ពេញ (ត្រឹមត្រូវបំផុត)។ ចង់សន្សំ token → ដាក់ LITE_PROMPT=1 ក្នុង Secrets
TRANS_SYSTEM_LITE = (
    "You are a Cambodian Khmer dubbing translator. Translate the numbered lines (consecutive lines of ONE video) into natural "
    "everyday SPOKEN Khmer (Phnom Penh), not written/news Khmer and not word-for-word. "
    "Rules: keep exact meaning, names, numbers, negations and emotion; never add or drop facts; pick pronouns/politeness by relationship "
    "and keep them consistent; transliterate foreign names by sound the same way every time; translate idioms by meaning; "
    "one input line = exactly one complete Khmer sentence, same order, never merge or split. "
    "A [max N chars] tag is the speaking-time budget: use the shortest natural wording, drop fillers, never drop a fact; never output the tag. "
    "Output is read by TTS: Khmer script only, end with ។ ? or !, no commas, brackets, quotes, dashes, ellipses, emojis or symbols. "
    "A [speaker: male] or [speaker: female] tag is the true gender of the speaker: use បាទ / ខ្ញុំបាទ for a man and ចាស / នាងខ្ញុំ (formal) for a woman, never swap them; never output the tag. "
    "An English hint, if given, is only a hint; the original wins. "
    'Return JSON {"translations": [...]} with exactly one item per input.'
)
LITE_PROMPT = str(get_secret("LITE_PROMPT", "0")).strip().lower() in ("1", "true", "yes", "on")
TRANS_SYSTEM = TRANS_SYSTEM_LITE if LITE_PROMPT else TRANS_SYSTEM_FULL


def _groq_translate_chunk_impl(api_key, texts, budgets=None, system=None, to_english=False, rotate=False):
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


# =====================================================================
#  xKiro API (OpenAI-compatible) — សម្រាប់ការងារអត្ថបទ/បកប្រែ
#  Secrets: XKIRO_API_KEY, XKIRO_BASE_URL (optional), XKIRO_MODEL
# =====================================================================
OAI_KEY = get_secret("XKIRO_API_KEY", "").strip()
OAI_BASE = (get_secret("XKIRO_BASE_URL", "https://api.xkiro.com/v1").strip().rstrip("/") or "https://api.xkiro.com/v1")
OAI_MODEL = get_secret("XKIRO_MODEL", "qwen/qwen3.5-flash").strip()


# =====================================================================
#  CodeCraft API (OpenAI-compatible) — ម៉ាស៊ីនបកប្រែទី២ (ប្រើជាបម្រុង បន្ទាប់ពី xKiro)
#  Secrets: CODECRAFT_API_KEY, CODECRAFT_BASE_URL (ចាំបាច់), CODECRAFT_MODEL (ចាំបាច់)
#  ឧ. CODECRAFT_BASE_URL = "https://.../v1"  (ត្រូវបញ្ចប់ត្រឹម /v1 មុន /chat/completions)
# =====================================================================
CC_KEY = get_secret("CODECRAFT_API_KEY", "").strip()
CC_BASE = get_secret("CODECRAFT_BASE_URL", "").strip().rstrip("/")
CC_MODEL = get_secret("CODECRAFT_MODEL", "").strip()


def cc_enabled():
    return bool(CC_KEY and CC_BASE.startswith("http") and CC_MODEL)


# =====================================================================
#  Claude (Anthropic) API — ម៉ាស៊ីនបកប្រែល្អបំផុត (ត្រូវបានសាកមុនគេ បើមាន Key)
#  Secrets:
#    ANTHROPIC_API_KEY  (ឬ CLAUDE_API_KEY)  ← ដាក់បានច្រើន Key: ANTHROPIC_API_KEYS ឬ ANTHROPIC_API_KEY_1, _2 ...
#    ANTHROPIC_BASE_URL (មិនចាំបាច់ — លំនាំដើម https://api.laalaa.me
#                        បើប្រើ Claude Code API ពីហាង/proxy សូមដាក់ Base URL ដែលហាងផ្តល់ឱ្យ)
#    ANTHROPIC_MODEL    (មិនចាំបាច់ — លំនាំដើម claude-sonnet-5-5)
# =====================================================================
_claude_vals = [
    get_secret("ANTHROPIC_API_KEY", ""), get_secret("ANTHROPIC_API_KEYS", ""),
    get_secret("CLAUDE_API_KEY", ""), get_secret("CLAUDE_API_KEYS", ""),
]
for _ci in range(1, 21):
    _claude_vals.append(get_secret(f"ANTHROPIC_API_KEY_{_ci}", ""))
CLAUDE_KEYS = split_keys(_claude_vals)
CLAUDE_BASE = (str(get_secret("ANTHROPIC_BASE_URL", "https://api.laalaa.me") or "").strip().rstrip("/")
               or "https://api.laalaa.me")
CLAUDE_MODEL = (str(get_secret("ANTHROPIC_MODEL", "claude-sonnet-5-5") or "").strip() or "claude-sonnet-5-5")
_CLAUDE_SECRET_PROVIDERS = [(f"Claude #{_i}", (_k, CLAUDE_BASE, CLAUDE_MODEL)) for _i, _k in enumerate(CLAUDE_KEYS, start=1)]
_CLAUDE_PROVIDERS = list(_CLAUDE_SECRET_PROVIDERS)   # បញ្ជីដែលកំពុងប្រើ (Key ផ្ទាល់ខ្លួនមុន រួច Secrets) — ធ្វើបច្ចុប្បន្នភាពពេលចុច «ចាប់ផ្តើម»
_CLAUDE_COOL = {}


def claude_enabled():
    return bool(_CLAUDE_PROVIDERS)


_CLAUDE_FALLBACK_MODELS = ["claude-sonnet-5-5", "claude-sonnet-5"]   # ដក Opus ចេញ (ថ្លៃជាង ៥ដង)
_CLAUDE_GOOD_MODEL = {}
_CLAUDE_LAST_CALL = {"t": 0.0}
_CLAUDE_MIN_GAP = 2.2   # laalaa មាន 30 request/នាទី → ទុកគម្លាត ≥2.2វិ រវាងការហៅ


def _claude_throttle():
    gap = _CLAUDE_MIN_GAP - (time.time() - _CLAUDE_LAST_CALL["t"])
    if gap > 0:
        time.sleep(min(gap, _CLAUDE_MIN_GAP))
    _CLAUDE_LAST_CALL["t"] = time.time()


def claude_translate_chunk(texts, budgets=None, system=None, to_english=False, cfg=None, raw=False):
    """ហៅ Claude តាម Anthropic Messages API (/v1/messages) ហើយទទួលលទ្ធផល JSON {"translations": [...]}។"""
    _key, _base, _model = cfg
    if not (_key and _base and _model):
        raise RuntimeError("Claude: សូមកំណត់ ANTHROPIC_API_KEY ក្នុង Secrets។")
    numbered = "\n".join(
        f"{i + 1}. " + (f"[max {budgets[i]} chars] " if budgets and i < len(budgets) and budgets[i] else "") + str(t)
        for i, t in enumerate(texts)
    )
    sys_text = (system or TRANS_SYSTEM) + ' Return ONLY the JSON object {"translations": [...]} with no other text.'
    url = _base + ("/messages" if _base.endswith("/v1") else "/v1/messages")
    use_temp = True
    _first = _CLAUDE_GOOD_MODEL.get(_key) or _model
    models = [_first] + [m for m in [_model] + _CLAUDE_FALLBACK_MODELS if m != _first]
    mi = 0
    last = "Claude: មិនទាន់ទទួលបានចម្លើយ"
    for attempt in range(5):
        payload = {
            "model": models[mi],
            "max_tokens": min(4096, 300 + 160 * len(texts)),
            "system": sys_text,
            "messages": [{"role": "user", "content": numbered}],
        }
        if use_temp:
            payload["temperature"] = 0.1
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "x-api-key": _key,
                "Authorization": f"Bearer {_key}",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        _claude_throttle()
        try:
            with urllib.request.urlopen(request, timeout=90) as r:
                data = json.loads(r.read().decode("utf-8"))
            content = "".join(b.get("text", "") for b in (data.get("content") or []) if b.get("type") == "text")
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
            content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
            match = re.search(r"\{.*\}", content, flags=re.S)
            parsed = json.loads(match.group(0) if match else content)
            items = parsed.get("translations") or []
            if len(items) == len(texts):
                _CLAUDE_GOOD_MODEL[_key] = models[mi]
                if raw:
                    return list(items)
                return [((str(x).strip() or None) if to_english else clean_translation(x)) for x in items]
            last = "Claude: ឆ្លើយតបមិនគ្រប់ចំនួនបន្ទាត់"
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "ignore")[:220]
            except Exception:
                pass
            last = f"Claude HTTP {e.code}: {detail}".strip()
            if e.code == 400 and use_temp and attempt < 4:
                use_temp = False          # ម៉ូដែលខ្លះមិនទទួល temperature → សាកដោយគ្មាន
                continue
            if e.code in (404, 503, 529) and mi + 1 < len(models):
                mi += 1                   # model នេះគ្មាន account ទំនេរ → សាក model បន្ទាប់
                time.sleep(1.2)
                continue
            if e.code in (429, 500, 502, 503, 504, 529) and attempt < 4:
                _wait = 0.0
                try:
                    _wait = float(e.headers.get("Retry-After", "0") or 0)
                except Exception:
                    _wait = 0.0
                time.sleep(min(max(_wait, 3.0 * (attempt + 1)), 15.0))   # រង់ចាំកើនឡើង 3,6,9,12វិ
                continue
            raise RuntimeError(last)
        except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
            last = f"Claude បណ្តាញ/Timeout: {e}"
            if attempt < 1:
                time.sleep(2)
                continue
            raise RuntimeError(last)
        except Exception as e:
            last = f"Claude: {e}"
    raise RuntimeError(last[:400])


# Additional OpenAI-compatible providers. Add only providers for which the owner
# has supplied a key. Free-tier availability/quota is controlled by each provider.
# Cloudflare BASE_URL must include the account id, e.g. .../accounts/<ID>/ai/v1.
_EXTRA_PROVIDER_SPECS = [
    ("OpenRouter", "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "OPENROUTER_MODEL", "https://openrouter.ai/api/v1", "openrouter/free"),
    ("Cloudflare Workers AI", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_BASE_URL", "CLOUDFLARE_MODEL", "", "@cf/meta/llama-3.1-8b-instruct"),
    ("Mistral AI", "MISTRAL_API_KEY", "MISTRAL_BASE_URL", "MISTRAL_MODEL", "https://api.mistral.ai/v1", "mistral-small-latest"),
    ("NVIDIA NIM", "NVIDIA_API_KEY", "NVIDIA_BASE_URL", "NVIDIA_MODEL", "https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct"),
    ("Cohere Compatibility", "COHERE_API_KEY", "COHERE_BASE_URL", "COHERE_MODEL", "https://api.cohere.com/compatibility/v1", "command-r7b-12-2024"),
    ("SambaNova", "SAMBANOVA_API_KEY", "SAMBANOVA_BASE_URL", "SAMBANOVA_MODEL", "https://api.sambanova.ai/v1", "Meta-Llama-3.3-70B-Instruct"),
]
_EXTRA_PROVIDERS = []
for _pname, _pkey, _pbase, _pmodel, _default_base, _default_model in _EXTRA_PROVIDER_SPECS:
    _pb = str(get_secret(_pbase, _default_base) or _default_base).strip().rstrip("/")
    _pm = str(get_secret(_pmodel, _default_model) or _default_model).strip()

    # OpenRouter supports a list of keys. Try every configured key as its own
    # provider entry, so one 429/invalid key does not stop the other keys.
    if _pname == "OpenRouter":
        _key_values = [
            get_secret("OPENROUTER_API_KEY", ""),
            get_secret("OPENROUTER_API_KEYS", ""),
        ]
        for _key_i in range(1, 21):
            _key_values.append(get_secret(f"OPENROUTER_API_KEY_{_key_i}", ""))
        _keys = split_keys(_key_values)
        if _pb.startswith("https://") and _pm:
            for _idx, _pk in enumerate(_keys, start=1):
                if _pk:
                    _EXTRA_PROVIDERS.append((f"OpenRouter #{_idx}", (_pk, _pb, _pm)))
        continue

    _pk = str(get_secret(_pkey, "") or "").strip()
    if _pk and _pb.startswith("https://") and _pm:
        _EXTRA_PROVIDERS.append((_pname, (_pk, _pb, _pm)))


def extra_provider_enabled():
    return bool(_EXTRA_PROVIDERS)


_API_LOCAL = threading.local()

def oai_cfg():
    # Worker ម្នាក់ៗប្រើ Key របស់ session ខ្លួនឯង មិនចែករំលែក Key រវាងអ្នកប្រើ។
    c = getattr(_API_LOCAL, "xk_cfg", None)
    if c is not None:
        return c
    return (OAI_KEY, OAI_BASE.rstrip("/"), OAI_MODEL)


def xk_enabled():
    k, b, m = oai_cfg()
    return bool(k and b and m)


def oai_enabled():
    """មានម៉ាស៊ីនបកប្រែ OpenAI-compatible យ៉ាងហោចណាស់មួយ។"""
    return claude_enabled() or xk_enabled() or cc_enabled() or extra_provider_enabled()


def oai_translate_chunk(texts, budgets=None, system=None, to_english=False, cfg=None, raw=False):
    """ការបកប្រែ xKiro ដោយសន្សំ token និងកាត់បន្ថយ API calls។"""
    _key, _base, _model = cfg if cfg else oai_cfg()
    if not (_key and _base and _model):
        raise RuntimeError("សូមបញ្ចូល xKiro API Key ផ្ទាល់ខ្លួន។")
    numbered = "\\n".join(
        f"{i + 1}. " + (f"[max {budgets[i]} chars] " if budgets and i < len(budgets) and budgets[i] else "") + str(t)
        for i, t in enumerate(texts)
    )
    payload = {
        "model": _model,
        "temperature": 0,
        "max_tokens": min(4096, max(256, sum(len(str(t)) for t in texts) * 3 + 160)),
        "messages": [
            {"role": "system", "content": system or TRANS_SYSTEM},
            {"role": "user", "content": numbered},
        ],
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    last = "xKiro: មិនទាន់ទទួលបានចម្លើយ"
    for attempt in range(2):
        request = urllib.request.Request(
            _base.rstrip("/") + "/chat/completions", data=body, method="POST",
            headers={"Authorization": f"Bearer {_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=35) as r:
                data = json.loads(r.read().decode("utf-8"))
            content = data["choices"][0]["message"].get("content") or ""
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
            content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
            match = re.search(r"\\{.*\\}", content, flags=re.S)
            parsed = json.loads(match.group(0) if match else content)
            items = parsed.get("translations") or []
            if len(items) != len(texts):
                raise RuntimeError("xKiro: ម៉ូដែលឆ្លើយតបមិនគ្រប់ចំនួនបន្ទាត់")
            if raw:
                return list(items)
            return [((str(x).strip() or None) if to_english else clean_translation(x)) for x in items]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:180]
            last = f"xKiro HTTP {e.code}: {detail}"
            if e.code in (429, 500, 502, 503, 504) and attempt == 0:
                time.sleep(1)
                continue
            raise RuntimeError(last)
        except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
            raise RuntimeError(f"xKiro បណ្តាញ/Timeout: {e}")
    raise RuntimeError(last)


def oai_test(key, base, model):
    """សាកល្បង xKiro: ត្រឡប់ (True/False, សារ)។"""
    key, base, model = str(key).strip(), str(base).strip().rstrip("/"), str(model).strip()
    if not (key and base and model):
        return False, "សូមបំពេញ Key, Base URL និងឈ្មោះម៉ូដែលឱ្យគ្រប់។"
    if not base.startswith("http"):
        return False, "Base URL ត្រូវចាប់ផ្តើមដោយ https://"
    try:
        out = oai_translate_chunk(["hello"], None, 'Translate each line to Khmer. Return JSON {"translations": [...]} only.', cfg=(key, base, model))
        return (True, "") if out else (False, "មិនមានចម្លើយ")
    except Exception as e:
        return False, "សាកមិនបាន៖ " + str(e)[:220]


def groq_translate_chunk(api_key, texts, budgets=None, system=None, to_english=False, rotate=False):
    """លំដាប់៖ Groq (ម៉ាស៊ីនសំខាន់) → OpenRouter → CodeCraft → xKiro (ម៉ាស៊ីនបម្រុង)។"""
    groq_err = None
    if claude_enabled() and CLAUDE_FIRST:
        for _cn, _cc in _CLAUDE_PROVIDERS:
            _cl = _CLAUDE_COOL.setdefault(_cn, {"until": 0.0})
            if _cl.get("until", 0) > time.time():
                continue
            _cr = _try_provider(_cl, _cc, texts, budgets, system, to_english, False, name=_cn, fn=claude_translate_chunk)
            if _cr is not None:
                return _cr
    if api_key:
        try:
            return _groq_translate_chunk_impl(api_key, texts, budgets, system, to_english, rotate)
        except Exception as e:
            groq_err = e
    if oai_enabled():
        _r = oai_try(texts, budgets, system, to_english)
        if _r is not None:
            return _r
    if claude_enabled() and not CLAUDE_FIRST:
        for _cn, _cc in _CLAUDE_PROVIDERS:
            _cl = _CLAUDE_COOL.setdefault(_cn, {"until": 0.0})
            if _cl.get("until", 0) > time.time():
                continue
            _cr = _try_provider(_cl, _cc, texts, budgets, system, to_english, False, name=_cn, fn=claude_translate_chunk)
            if _cr is not None:
                return _cr
    parts = [f"Groq: {str(groq_err)[:150]}"] if groq_err else []
    if _LAST_AI_ERR:
        parts.append("; ".join(f"{k}: {v}"[:110] for k, v in list(_LAST_AI_ERR.items())[:4]))
    parts.append("ស្ថានភាព៖ " + provider_status())
    raise RuntimeError(" | ".join(parts))


_OAI_COOL = {"until": 0.0}
_CC_COOL = {"until": 0.0}
_EXTRA_COOL = {}


_LAST_AI_ERR = {}


def _try_provider(cool, cfg, texts, budgets, system, to_english, raw, name="xKiro", fn=None):
    for attempt in range(2):
        try:
            return (fn or oai_translate_chunk)(texts, budgets, system, to_english, cfg=cfg, raw=raw)
        except Exception as e:
            _LAST_AI_ERR[name] = str(e)[:260]   # ទុកមូលហេតុពិត ដើម្បីបង្ហាញអ្នកប្រើ
            if "ចំនួនបន្ទាត់" in str(e):
                continue   # ម៉ូដែលឆ្លើយខុសចំនួនបន្ទាត់ → សាកម្តងទៀត មិនសម្រាកទាំងមូល
            _m = str(e)
            if any(f"HTTP {c}" in _m for c in (401, 402, 403, 404)):
                _cd = 600      # Key/URL/model ខុស → សម្រាកយូរ
            elif any(f"HTTP {c}" in _m for c in (429, 503, 529)):
                _cd = 25       # Rate limit បណ្តោះអាសន្ន → សម្រាកខ្លី រួចសាកវិញ
            else:
                _cd = 60       # server/បណ្តាញមានបញ្ហា
            cool["until"] = time.time() + _cd
            return None
    return None


def provider_status():
    """សង្ខេបស្ថានភាពម៉ាស៊ីន AI នីមួយៗ (បានកំណត់ឬអត់ / កំពុងសម្រាក) ដើម្បីបង្ហាញក្នុងសារកំហុស។"""
    now = time.time()
    def _cool(c):
        left = int(c.get("until", 0) - now)
        return f" (សម្រាក {left}វិ)" if left > 0 else ""
    out = []
    try:
        out.append("Groq ✓" if (GROQ_KEY or has_user_keys()) else "Groq ✗ (គ្មាន key)")
    except Exception:
        out.append("Groq ?")
    if claude_enabled():
        out.append(f"Claude ×{len(_CLAUDE_PROVIDERS)} ✓")
    else:
        out.append("Claude ✗ (គ្មាន ANTHROPIC_API_KEY)")
    names = [n for n, _ in _EXTRA_PROVIDERS]
    n_or = sum(1 for n in names if n.startswith("OpenRouter"))
    out.append(f"OpenRouter ×{n_or}" if n_or else "OpenRouter ✗ (គ្មាន key)")
    for n in names:
        if not n.startswith("OpenRouter"):
            out.append(f"{n} ✓" + _cool(_EXTRA_COOL.get(n, {})))
    if cc_enabled():
        out.append("CodeCraft ✓" + _cool(_CC_COOL))
    else:
        miss = [k for k, v in (("API_KEY", CC_KEY), ("BASE_URL", CC_BASE.startswith("http") and CC_BASE), ("MODEL", CC_MODEL)) if not v]
        out.append("CodeCraft ✗ (ខ្វះ CODECRAFT_" + ", CODECRAFT_".join(miss) + ")")
    out.append("xKiro ✓" + _cool(_OAI_COOL) if xk_enabled() else "xKiro ✗ (គ្មាន XKIRO_API_KEY)")
    return " · ".join(out)


def oai_try(texts, budgets=None, system=None, to_english=False, raw=False):
    """ម៉ាស៊ីនបម្រុងក្រៅពី Groq តាមលំដាប់៖ OpenRouter(+ផ្សេងៗ) → CodeCraft → xKiro
    (មានកំណត់ពេលសរុប ១២០ វិនាទីក្នុងមួយបាច់)។"""
    if getattr(_API_LOCAL, "isolated", False):
        _cfg = oai_cfg()
        if not all(_cfg):
            return None
        try:
            return oai_translate_chunk(texts, budgets, system, to_english, cfg=_cfg, raw=raw)
        except Exception as e:
            _API_LOCAL.last_error = str(e)[:200]
            return None
    t_end = time.time() + 120
    def _claude_pass():
        for _name, _cfg in _CLAUDE_PROVIDERS:
            if time.time() >= t_end:
                break
            _cool = _CLAUDE_COOL.setdefault(_name, {"until": 0.0})
            if _cool.get("until", 0) > time.time():
                continue
            r = _try_provider(_cool, _cfg, texts, budgets, system, to_english, raw, name=_name, fn=claude_translate_chunk)
            if r is not None:
                return r
        return None
    if CLAUDE_FIRST:
        r = _claude_pass()
        if r is not None:
            return r
    for _name, _cfg in []:
        if time.time() >= t_end:
            break
        _cool = _CLAUDE_COOL.setdefault(_name, {"until": 0.0})
        if _cool.get("until", 0) > time.time():
            continue
        r = _try_provider(_cool, _cfg, texts, budgets, system, to_english, raw, name=_name, fn=claude_translate_chunk)
        if r is not None:
            return r
    for _name, _cfg in _EXTRA_PROVIDERS:
        if time.time() >= t_end:
            break
        _cool = _EXTRA_COOL.setdefault(_name, {"until": 0.0})
        if _cool.get("until", 0) > time.time():
            continue
        r = _try_provider(_cool, _cfg, texts, budgets, system, to_english, raw, name=_name)
        if r is not None:
            return r
    if cc_enabled() and _CC_COOL.get("until", 0) <= time.time() and time.time() < t_end:
        r = _try_provider(_CC_COOL, (CC_KEY, CC_BASE, CC_MODEL), texts, budgets, system, to_english, raw, name="CodeCraft")
        if r is not None:
            return r
    if xk_enabled() and _OAI_COOL.get("until", 0) <= time.time() and time.time() < t_end:
        r = _try_provider(_OAI_COOL, oai_cfg(), texts, budgets, system, to_english, raw, name="xKiro")
        if r is not None:
            return r
    if not CLAUDE_FIRST:
        return _claude_pass()
    return None


EN_SYSTEM = (
    "You are a careful transcription-correction and meaning bridge for dubbing. The numbered lines are consecutive lines from ONE video; "
    "use surrounding context to resolve only obvious Whisper errors, speaker references, slang, and idioms. Render each line as clear, "
    "faithful English that preserves every meaningful detail, emotion and tone (anger, sarcasm, sadness, affection). Do not translate beyond what the audio supports, add explanations, "
    "embellish, or guess at unclear words; mark genuinely unclear audio as [unclear]. "
    "mark genuinely unclear audio as [unclear] rather than making up dialogue. Keep exactly one output for each input line, same order. "
    "Return JSON {\"translations\": [...]} only."
)


def gemini_translate_khmer(api_key, texts, english=None, budgets=None, story=None, groq_key=None, speakers=None):
    """បកជាខ្មែរ៖ Groq មុន រួច OpenRouter → CodeCraft → xKiro ជាបម្រុង (មិនហៅ Gemini)។"""
    rows = []
    for i, text in enumerate(texts):
        row = spk_tag(speakers[i] if speakers and i < len(speakers) else None) + str(text)
        if english and i < len(english) and english[i] and "[unclear]" not in str(english[i]):
            row += f" (English meaning: {english[i]})"
        rows.append(row)
    system = (
        TRANS_SYSTEM
        + " Some lines include an English meaning in parentheses to help you understand; "
          "translate the true meaning into Khmer and never output English text or tags."
        + ((" STORY SO FAR (context only, do NOT translate): " + story) if story else "")
    )
    if groq_key:
        return groq_translate_chunk(groq_key, rows, budgets, system=system)
    result = oai_try(rows, budgets, system)
    if result is not None:
        return result
    _why = " | ".join(f"{k}: {v}" for k, v in _LAST_AI_ERR.items()) or "គ្មាន API Key ដែលបានកំណត់"
    raise RuntimeError("ម៉ាស៊ីន AI បកប្រែមិនបាន។ មូលហេតុ៖ " + _why + " | ស្ថានភាព៖ " + provider_status())


REFINE_SYSTEM = (
    "You are a senior Khmer (Cambodian) dubbing editor and bilingual proofreader. For EVERY item first back-translate the KHMER DRAFT into English in your head and compare it with the ORIGINAL: any difference in meaning (an idea added or missing, a lost negation, wrong subject or object, wrong number or name, wrong tense or mood, changed emotion or tone) must be fixed. Each numbered item has an ORIGINAL line, "
    "sometimes an ENGLISH meaning, and a KHMER DRAFT. Check the KHMER DRAFT against the ORIGINAL: fix wrong or missing meaning, "
    "mistranslated words, wrong pronouns/politeness, literal word-for-word phrasing, unnatural or ungrammatical Khmer, and any leftover "
    "foreign words (except names). Rewrite into natural everyday SPOKEN Khmer that a native Phnom Penh speaker would say and instantly understand, "
    "keeping exactly the same facts, names, numbers, emotion and tone. Do not add or remove information. If the draft is already correct and natural, "
    "return it unchanged. Use the neighbouring items as story context (who speaks to whom). One complete sentence per item, same order, "
    "Khmer script only, end with ។ (or ? !), no commas, brackets, quotes, dashes, ellipses, emojis or symbols. "
    "Also verify: every negation, question, number, name (same transliteration in every line), kinship word and who-does-what-to-whom is exactly right, and the Khmer has no invented or nonsense words. "
    "Return JSON {\"translations\": [...]} with exactly one item per input."
)


def refine_khmer(texts, englishes, drafts, gemini_key, groq_key, progress=None, shift=1, speakers=None):
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
            if speakers and i < len(speakers) and speakers[i]:
                row += " | SPEAKER: " + ("male" if speakers[i] == "M" else "female")
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
        _r = oai_try(rows, None, REFINE_SYSTEM + " " + story)
        if _r is not None:
            return idxs, _r
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


SPEAKER_NOTE = (
    " If an item has SPEAKER: male or SPEAKER: female, that is the TRUE gender of the speaker measured from the audio. "
    "The Khmer must fit it: male uses បាទ and ខ្ញុំបាទ (formal I); female uses ចាស and នាងខ្ញុំ (formal I); never use the other gender's polite words. "
    "Fix any line where the particles do not match the speaker. Never output the SPEAKER field."
)
REFINE_SYSTEM = REFINE_SYSTEM + SPEAKER_NOTE
JUDGE_SYSTEM = JUDGE_SYSTEM + SPEAKER_NOTE


def judge_khmer(texts, englishes, cand_a, cand_b, gemini_key, groq_key, progress=None, shift=2, speakers=None):
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
            if speakers and i < len(speakers) and speakers[i]:
                row += " | SPEAKER: " + ("male" if speakers[i] == "M" else "female")
            row += f" | A: {cand_a[i]} | B: {cand_b[i]}"
            rows.append(row)
        prev = [str(cand_a[j]) for j in range(max(0, idxs[0] - 3), idxs[0]) if cand_a[j]]
        nxt = [str(cand_a[j]) for j in range(idxs[-1] + 1, min(n, idxs[-1] + 3)) if cand_a[j]]
        ctx = ""
        if prev:
            ctx += "PREVIOUS LINES (context only): " + " / ".join(prev) + " "
        if nxt:
            ctx += "NEXT LINES (context only): " + " / ".join(nxt)
        _r = oai_try(rows, None, JUDGE_SYSTEM + " " + ctx)
        if _r is not None:
            return idxs, _r
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
    _r = oai_try([body], None,
                 "Read the video transcript line. In under 120 words of English, state: the topic, who the speakers are and how they relate "
                 "(gender, age, formal or casual), the mood, and any recurring names or terms. No translation. "
                 'Return JSON {"translations": ["<summary>"]}.', to_english=True)
    if _r and _r[0]:
        return str(_r[0])[:900]
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
    _r = oai_try(rows, None, system, to_english=(not khmer))
    if _r is not None:
        return _r
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


try:
    TRANS_BATCH = max(4, min(16, int(get_secret("TRANS_BATCH", "8") or 8)))
except Exception:
    TRANS_BATCH = 8
# REVIEW_MODE: off = បកម្តងគត់ (ថោកបំផុត) | refine = បក+កែ ១ជុំ | full = បក+កែ+ជ្រើស (ថ្លៃបំផុត)
REVIEW_MODE = str(get_secret("REVIEW_MODE", "full")).strip().lower()
# CLAUDE_FIRST=0 (លំនាំដើម): Claude ជាបម្រុងចុងក្រោយ (Groq/ឥតគិតថ្លៃមុន) | 1 = Claude មុនគេ
CLAUDE_FIRST = str(get_secret("CLAUDE_FIRST", "0")).strip().lower() in ("1", "true", "yes", "on")
# FIT_MODE=off (លំនាំដើម): មិនហៅ AI តម្រឹមប្រវែង | on = បង្រួមឃ្លាវែងដោយ AI
FIT_MODE = str(get_secret("FIT_MODE", "off")).strip().lower() in ("1", "true", "yes", "on")
FAST_TRANSLATE = str(get_secret("FAST_TRANSLATE", "0")).strip().lower() not in ("0", "false", "no", "off")


def translate_texts(texts, groq_key=None, budgets=None, gemini_key=None, progress=None, speakers=None):
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
    if (groq_key or oai_enabled()) and not FAST_TRANSLATE:
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
    if n > 2 and not FAST_TRANSLATE:
        if groq_key or oai_enabled():
            synopsis = make_synopsis(english, texts, None, groq_key)
        if not synopsis and gemini_key:
            synopsis = make_synopsis(english, texts, gemini_key, None)
    # ជំហាន ២: Gemini បកជាខ្មែរមុន (ល្អបំផុតសម្រាប់ខ្មែរ) ដោយមានបរិបទមុន/ក្រោយ
    missing = [i for i, o in enumerate(outs) if o is None]
    batches = [missing[k:k + TRANS_BATCH] for k in range(0, len(missing), TRANS_BATCH)]
    if (gemini_key or oai_enabled()) and missing:
        def _km(idxs):
            try:
                prev_ctx = [english[j] or str(texts[j]) for j in range(max(0, idxs[0] - 3), idxs[0])]
                story = " / ".join(str(x).strip() for x in prev_ctx if x) or None
                if synopsis:
                    story = "VIDEO SUMMARY: " + synopsis + " || " + (story or "")
                nxt_ctx = [english[j] or str(texts[j]) for j in range(idxs[-1] + 1, min(n, idxs[-1] + 3))]
                if nxt_ctx:
                    story = (story or "") + " || NEXT LINES (context only): " + " / ".join(str(x).strip() for x in nxt_ctx if x)
                return idxs, gemini_translate_khmer(
                    gemini_key, [str(texts[i]).strip() for i in idxs],
                    [english[i] for i in idxs], [budgets[i] for i in idxs] if budgets else None,
                    story=story, groq_key=groq_key,
                    speakers=[speakers[i] for i in idxs] if speakers else None,
                ), None
            except Exception as e:
                return idxs, None, e
        done = 0
        with ThreadPoolExecutor(max_workers=5) as pool:
            for idxs, res, err in pool.map(_km, batches):
                if err:
                    errors.append(f"xKiro: {err}"[:200])
                else:
                    for i, r in zip(idxs, res):
                        outs[i] = r
                done += len(idxs)
                _say(f"កំពុងបកជាខ្មែរ {done}/{n} ឃ្លា...")
    xkiro_ok = {i for i, o in enumerate(outs) if o is not None}
    # ជំហាន ២ខ: Groq ជាបម្រុង ប្រសិនបើ xKiro មិនបាន
    missing = [i for i, o in enumerate(outs) if o is None]
    if missing and groq_key:
        _say(f"កំពុងបកជាខ្មែរតាមសាច់រឿង (Groq ជាបម្រុង) 0/{len(missing)} ឃ្លា...")
        groups = [missing[k:k + 8] for k in range(0, len(missing), 8)]
        def _gkm(idxs):
            try:
                prev = [english[j] or str(texts[j]) for j in range(max(0, idxs[0] - 6), idxs[0])]
                story = " / ".join(str(x).strip() for x in prev if x)
                if synopsis:
                    story = "VIDEO SUMMARY: " + synopsis + " || " + story
                lines_ = []
                for i in idxs:
                    row = spk_tag(speakers[i] if speakers else None) + str(texts[i]).strip()
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
                _say(f"កំពុងបកជាខ្មែរតាមសាច់រឿង (Groq ជាបម្រុង) {done_}/{len(missing)} ឃ្លា...")
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
    if missing and (gemini_key or oai_enabled()):
        for k in range(0, len(missing), 8):
            idxs = missing[k:k + 8]
            try:
                res = gemini_translate_khmer(
                    gemini_key, [str(texts[i]).strip() for i in idxs],
                    [english[i] for i in idxs],
                    [budgets[i] for i in idxs] if budgets else None,
                    groq_key=groq_key,
                    speakers=[speakers[i] for i in idxs] if speakers else None,
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
                    groq_key, [spk_tag(speakers[i] if speakers else None) + str(texts[i]).strip() for i in idxs],
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
            spk_ = [speakers[i]] if speakers else None
            r = None
            if (gemini_key or oai_enabled()) and dead["gemini"] < 2:
                try:
                    r = gemini_translate_khmer(gemini_key, one, [english[i]], bud, groq_key=groq_key, speakers=spk_)[0]
                    dead["gemini"] = 0
                except Exception as e:
                    _fail("gemini", f"gemini-1: {e}")
            if (not r or not has_khmer(str(r))) and groq_key and dead["groq"] < 2 and time.time() < t_end:
                try:
                    r = groq_translate_chunk(groq_key, [spk_tag(spk_[0] if spk_ else None) + one[0]], bud)[0]
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
    only_groq = not (gemini_key or oai_enabled())
    _quota_ok = time.time() - _GROQ_LIMIT["t"] > 900   # មិនជួប 429 ក្នុង ១៥ នាទីចុងក្រោយ
    if REVIEW_MODE in ("refine", "full") and allidx and (groq_key or gemini_key or oai_enabled()) and (not only_groq or _quota_ok) and all(o and has_khmer(str(o)) for o in outs):
        try:
            cand_a = list(outs)
            cand_b = refine_khmer([texts[i] for i in allidx], [english[i] for i in allidx], cand_a,
                                  gemini_key, groq_key, progress=progress, shift=1, speakers=speakers)
            cand_b = [b or a for a, b in zip(cand_a, cand_b)]
            if REVIEW_MODE == "full":
                outs = judge_khmer([texts[i] for i in allidx], [english[i] for i in allidx], cand_a, cand_b,
                                   gemini_key, groq_key, progress=progress, shift=2, speakers=speakers)
            else:
                outs = cand_b
        except Exception as e:
            errors.append(f"refine/judge: {e}"[:200])
    # តម្រឹមប្រវែងឃ្លាខ្មែរឱ្យសមនឹងពេលមាត់តួអង្គនិយាយ (lip-sync)
    if FIT_MODE and budgets and all(o and has_khmer(str(o)) for o in outs):
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


def merge_for_translate(segs, max_chars=200, max_gap=1.0, max_len=11.0, gender_fn=None):
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
            if _spk_differs(gender_fn, ps, pe, s, e):
                cont = False   # អ្នកនិយាយប្តូរភេទ → មិនបញ្ចូលគ្នា (ឃ្លានីមួយៗមានសំឡេងតែមួយ)
            gap_ok = (s - pe) <= (max_gap if not ended else 0.5)
            if cont and gap_ok and len(pt) + len(t) + 1 <= max_chars and e - ps <= max_len:
                out[-1] = (ps, max(pe, e), (pt + " " + t).strip())
                continue
        out.append((s, e, t))
    return out


def transcribe_free(groq_key, audio_path, duration, source_language, status, speech=None, khmer_ok=True, dub=False, gemini_key=None, keep_failed=False, gender_fn=None):
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
        keep = merge_for_translate(keep, gender_fn=gender_fn)
        speakers = None
        if gender_fn is not None:
            try:
                speakers = [gender_fn(_s, _e) for _s, _e, _t in keep]
                if not any(speakers):
                    speakers = None
            except Exception:
                speakers = None
        # បកប្រែតាមប្រវែងឃ្លាចិន៖ ឃ្លាខ្លីអាចពន្យល់ខ្មែរបន្ថែម,
        # ឃ្លាវែងត្រូវសង្ខេបខ្មែរឱ្យខ្លី ដើម្បីសមនឹងចន្លោះសំឡេង។
        # ប្រវែងគោល (soft hint): ~១០ តួអក្សរខ្មែរ/វិនាទី តាមពេលមាត់និយាយ ឱ្យស្របចង្វាក់ lip-sync
        # (prompt ហាមកាត់អត្ថន័យ ដូច្នេះនេះគ្រាន់តែជាការណែនាំ)
        budgets = lip_budgets(keep)  # ប្រវែងអក្សរតាមពេលមាត់និយាយ ឱ្យសំឡេងចប់ត្រូវមាត់
        outs, errs = translate_texts([t for _, _, t in keep], groq_key, budgets, gemini_key, progress=lambda m: status.write("៣/៤ " + m), speakers=speakers)
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
        # ផ្លាស់ប្តូររបៀបអានបន្តិចបន្តួចតាមអត្ថបទ ដើម្បីកុំឱ្យស្តាប់ដូចម៉ាស៊ីនអានដដែលៗ
        # ល្បឿន/កម្រិតសំឡេងថេរ ស្រាលៗ ដើម្បីឱ្យច្បាស់ និងមិនប្រែប្រួលចៃដន្យ
        kw = {"rate": "-2%", "pitch": "+0Hz"}
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
            g0, g1 = _label_clusters(hz0, hz1)
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
        info.update({"two": False, "single": single})
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
    info.update({"two": True, "hz_m": hz_m, "hz_f": hz_f})
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


def _label_clusters(hz0, hz1):
    """កំណត់ភេទនៃក្រុមសំឡេង ២ (ទាប/ខ្ពស់)។ មិនយកក្រុមខ្ពស់ជាស្រី ប្រសិនបើប្រុស ២ នាក់ដែលសំឡេងខុសគ្នាបន្តិច
    (ឧ. ប្រុស 130Hz + ប្រុស 170Hz ត្រូវតែនៅជាប្រុសទាំងពីរ)។"""
    r = hz1 / max(hz0, 1.0)
    if hz0 <= 150:
        g0 = "M"
    elif hz0 >= 185:
        g0 = "F"
    else:
        g0 = "M" if (r >= 1.3 and hz1 >= 190) else "F"
    if hz1 >= 180:
        g1 = "F"
    elif hz1 <= 150:
        g1 = "M"
    else:
        g1 = "F" if (hz0 <= 150 and r >= 1.4) else g0
    return g0, g1


class SpeakerMap:
    """ផែនទីអ្នកនិយាយ ប្រុស/ស្រី តាមពេលវេលា។ វាស់តាមឃ្លានីមួយៗ (មិនត្រូវការ MIN_TURN ២វិ ដូច timeline)
    ដូច្នេះប្រុស/ស្រីឆ្លើយគ្នាលឿនៗ ក៏មិនច្រឡំសំឡេងដែរ។ អ្នកប្រើអាចបង្ខំភេទបាន (overrides)។"""

    def __init__(self, times=None, f0=None, mode="none", hz_m=None, hz_f=None, single=None):
        self.t = times
        self.f0 = f0
        self.mode = mode          # "two" | "single" | "none"
        self.hz_m = hz_m
        self.hz_f = hz_f
        self.single = single
        self.over = []
        self.summary = ""
        self._cache = {}

    def set_overrides(self, items):
        self.over = [(float(a), float(b), g) for a, b, g in (items or []) if g in ("M", "F")]
        self._cache = {}

    def _forced(self, a, b):
        if not self.over:
            return None
        tot = {"M": 0.0, "F": 0.0}
        for x, y, g in self.over:
            ov = min(b, y) - max(a, x)
            if ov > 0:
                tot[g] += ov
        best = "M" if tot["M"] >= tot["F"] else "F"
        span = max(0.05, b - a)
        return best if tot[best] >= 0.4 * span else None

    def _measure(self, a, b):
        if self.mode == "single":
            return self.single
        if self.mode != "two" or self.t is None or len(self.t) == 0:
            return None
        import numpy as np
        m = (self.t >= a) & (self.t <= b) & (self.f0 > 0)
        n = int(m.sum())
        if n < 4:
            return None
        lg = np.log2(self.f0[m])
        cut = 0.5 * (np.log2(self.hz_m) + np.log2(self.hz_f))
        nf = int((lg > cut).sum())
        nm = n - nf
        if abs(nf - nm) / float(n) < 0.2:
            return None
        return "F" if nf > nm else "M"

    def gender_at(self, a, b):
        key = (round(float(a), 2), round(float(b), 2))
        if key in self._cache:
            return self._cache[key]
        g = self._forced(a, b)
        if g is None:
            g = self._measure(a, b)
        self._cache[key] = g
        return g

    def fill(self, segs, default=None, max_gap=2.5):
        """ភេទរបស់ឃ្លានីមួយៗ។ ឃ្លាខ្លីពេកដែលវាស់មិនបាន ប្រើអ្នកនិយាយជិតបំផុតតាមពេល។"""
        raw = [self.gender_at(sg[0], sg[1]) for sg in segs]
        out = list(raw)
        for i in range(len(segs)):
            if out[i] is not None:
                continue
            best, bd = None, 1e9
            for j in range(len(segs)):
                if raw[j] is None:
                    continue
                d = max(segs[i][0] - segs[j][1], segs[j][0] - segs[i][1], 0.0)
                if d < bd:
                    best, bd = raw[j], d
            out[i] = best if (best and bd <= max_gap) else default
        return out


def build_speaker_map(tracks, duration, default_voice):
    try:
        times, f0, rms = tracks
        runs, info = gender_timeline(None, duration, default_voice, tracks=tracks)
    except Exception:
        return None
    if runs is None or "two" not in info:
        return None
    if info["two"]:
        sm = SpeakerMap(times, f0, "two", hz_m=info["hz_m"], hz_f=info["hz_f"])
    else:
        sm = SpeakerMap(times, f0, "single", single=info["single"])
    sm.summary = info.get("summary", "")
    return sm


def voices_from_map(smap, segs, default_voice, runs=None):
    """សំឡេង (ប្រុស/ស្រី) សម្រាប់ឃ្លានីមួយៗ។ ប្រុស → Piseth, ស្រី → Sreymom ជានិច្ច។"""
    if smap is None:
        if runs is None:
            return None
        return [dominant_voice(a, b, runs, default_voice) for a, b, _t in segs]
    out = []
    for g, (a, b, _t) in zip(smap.fill(segs, default=None), segs):
        if g == "M":
            out.append(VOICE_MALE)
        elif g == "F":
            out.append(VOICE_FEMALE)
        elif runs is not None:
            out.append(dominant_voice(a, b, runs, default_voice))
        else:
            out.append(default_voice)
    return out


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
    if oai_enabled():
        _esys = EMO_SYSTEM.replace('"emotions"', '"translations"')
        _out = []
        for _k in range(0, len(texts), 25):
            _part = texts[_k:_k + 25]
            _r = oai_try(_part, None, _esys, to_english=True, raw=True)
            if _r is None or len(_r) != len(_part):
                _out = None
                break
            _out.extend(parse_emo_item(x) for x in _r)
        if _out:
            return _out
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
    rate = int(max(-26, min(26, rate * k * 1.1)))
    pitch = int(max(-20, min(20, pitch * k * 0.95))) if use_pitch else 0
    vol = int(max(-35, min(35, vol * k * 0.8)))
    if rate == 0 and pitch == 0 and vol == 0:
        return None
    return {"rate": f"{rate:+d}%", "pitch": f"{pitch:+d}Hz", "volume": f"{vol:+d}%"}





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


def merge_for_dub(segments, max_chars=260, max_gap=1.6, max_len=18.0, gender_fn=None):
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
                    and len(pt) + len(t) + 1 <= max_chars and e - ps <= max_len \
                    and not _spk_differs(gender_fn, ps, pe, s, e):
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
        _lim = max(6, int(slot * 11))
        _r = oai_try([text], None, "Shorten the Khmer sentence to at most " + str(_lim)
                     + " characters. Keep the meaning. Khmer script only. "
                     'Return JSON {"translations": ["<sentence>"]}.')
        if _r and _r[0] and has_khmer(_r[0]) and len(_r[0]) < len(text):
            return _r[0]
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


# ធ្វើឱ្យសំឡេងស្តាប់ទន់ ក្តៅ និងដូចមនុស្សនិយាយក្នុងបន្ទប់ (មិនស្ងួតដូចម៉ាស៊ីន)
VOICE_POLISH = ("highpass=f=70,"
                "acompressor=threshold=0.14:ratio=2:attack=12:release=180,"
                "equalizer=f=180:t=q:w=1:g=1.5,"
                "equalizer=f=3200:t=q:w=1.2:g=2.0")

# ល្បឿនអតិបរមា ដើម្បីឱ្យសំឡេងច្បាស់ មិនលឿនពេកស្តាប់មិនទាន់ (ប្តូរបានក្នុង Secrets)
try:
    MAX_DUB_SPEEDUP = max(1.0, min(1.6, float(get_secret("MAX_DUB_SPEEDUP", "1.25") or 1.25)))
    MAX_TTS_RATE = max(0, min(60, int(get_secret("MAX_TTS_RATE", "35") or 35)))
except Exception:
    MAX_DUB_SPEEDUP, MAX_TTS_RATE = 1.25, 35


def assign_characters(dub_segments, chars, info):
    """បែងចែកអ្នកនិយាយក្នុងវីដេអូតាម pitch ហើយផ្គូផ្គងទៅសំឡេងគំរូ (ទាប→ខ្ពស់)។
    ត្រឡប់ (seg_voices, targets, seg_char, char_bands, notes)។"""
    import numpy as np
    k = len(chars)
    n = len(dub_segments)
    order = sorted(range(k), key=lambda i: chars[i]["f0"])
    own = [median_pitch(info, sg[0], sg[1]) if info else None for sg in dub_segments]
    idx = [i for i, o in enumerate(own) if o]
    label = [None] * n
    if k == 1 or len(idx) < 2:
        label = [0] * n
    else:
        x = np.log2(np.array([own[i] for i in idx]))
        cen = np.percentile(x, np.linspace(10, 90, k))
        for _ in range(30):
            lab = np.argmin(np.abs(x[:, None] - cen[None, :]), axis=1)
            new = np.array([x[lab == c].mean() if np.any(lab == c) else cen[c] for c in range(k)])
            if np.allclose(new, cen, atol=1e-4):
                break
            cen = new
        rank = {int(c): r for r, c in enumerate(np.argsort(cen))}
        lab = np.argmin(np.abs(x[:, None] - cen[None, :]), axis=1)
        for i, l_ in zip(idx, lab):
            label[i] = rank[int(l_)]
        last = None
        for i in range(n):
            if label[i] is None:
                label[i] = last
            else:
                last = label[i]
        nxt = None
        for i in range(n - 1, -1, -1):
            if label[i] is None:
                label[i] = nxt if nxt is not None else 0
            else:
                nxt = label[i]
    seg_voices, targets, seg_char = [], [], []
    for l_ in label:
        ci = order[min(int(l_), k - 1)]
        c = chars[ci]
        seg_voices.append(VOICE_FEMALE if c["f0"] >= 165 else VOICE_MALE)
        targets.append(c["f0"])
        seg_char.append(ci)
    notes = []
    for ci, c in enumerate(chars):
        cnt = sum(1 for v in seg_char if v == ci)
        who = "ស្រី" if c["f0"] >= 165 else "ប្រុស"
        notes.append(f"🎤 តួអង្គទី {c['n']}: ~{int(c['f0'])}Hz → សំឡេង{who} ({cnt} ឃ្លា)")
    return seg_voices, targets, seg_char, [c["bands"] for c in chars], notes


def make_dub(folder, segments, voice, duration, keep_bg, client, model,
             seg_voices=None, targets=None, notes=None, emotions=None, groq_key=None,
             ref_bands=None, offset=0.0, tight=True, bg_vol=0.08,
             seg_char=None, char_bands=None):
    inputs, filters = [], []
    n = 0
    if keep_bg:
        inputs += ["-i", "audio.mp3"]
        filters.append(f"[0:a]volume={float(bg_vol):.3f}[bg]")
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
                        new_rate = int(round(max(-30, min(MAX_TTS_RATE, (mult_ - 1.0) * 100))))
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
            d_, p_cur_ = _fit_rate(t_, d_, p_cur_)
            # នៅតែវែងពេក៖ បង្រួមឃ្លាបន្តិច (រក្សាអត្ថន័យ) រួចតម្រឹមល្បឿនម្តងទៀត
            if d_ > slot0 * 1.6 and len(t_) > 30:
                short_ = condense_for_slot(t_, slot0, client, model, groq_key)
                if short_ != t_:
                    path3_ = os.path.join(folder, f"tts_{i}_s.mp3")
                    if tts_retry(short_, voices_[i], path3_, p_cur_, tries=2):
                        d3_, _, _ = probe_media(path3_)
                        if d3_ < d_ * 0.9:
                            shutil.move(path3_, path_)
                            d_ = d3_
                            d_, p_cur_ = _fit_rate(short_, d_, p_cur_)
            f0_ = None
            if targets is not None and i < len(targets) and targets[i]:
                f0_ = tts_median_pitch(path_)
            tb_ = None
            if ref_bands or char_bands:
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
    if ref_bands:
        import numpy as np
        for v_ in set(voices_):
            arrs = [r_[2] for k_, r_ in enumerate(results) if r_ and r_[2] and voices_[k_] == v_]
            if arrs:
                eqs = eq_filters(ref_bands, np.mean(arrs, axis=0).tolist())
                if eqs:
                    voice_eq[v_] = eqs
        if notes is not None and voice_eq:
            notes.append("🎚 ផ្គូផ្គងពណ៌សំឡេងស្រដៀងសំឡេងគំរូ")
    char_eq = {}
    if char_bands and seg_char:
        import numpy as np
        for c_ in set(seg_char):
            arrs = [r_[2] for k_, r_ in enumerate(results)
                    if r_ and r_[2] and k_ < len(seg_char) and seg_char[k_] == c_]
            if arrs and char_bands[c_]:
                eqs = eq_filters(char_bands[c_], np.mean(arrs, axis=0).tolist())
                if eqs:
                    char_eq[c_] = eqs
        if notes is not None and char_eq:
            notes.append("🎚 ផ្គូផ្គងពណ៌សំឡេងតាមតួអង្គនីមួយៗ")
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
        speed = min(MAX_DUB_SPEEDUP, max(1.0, speed))
        # តួអង្គនិយាយយឺត/បន្ថយសំឡេង៖ បើសំឡេង AI ខ្លីជាងពេលមាត់ ច្រើន ធ្វើឱ្យយឺតបន្តិច (មិនឱ្យសំឡេងចប់មុនមាត់)
        mouth = max(0.5, e - s)
        if d < mouth * 0.82 and speed == 1.0:
            speed = max(0.85, d / (mouth * 0.92))
        cursor = max(cursor, start + d / speed + 0.08)
        target = targets[i] if (targets is not None and i < len(targets) and targets[i]) else None
        plan.append({"name": f"tts_{i}.mp3", "start": start, "speed": speed,
                     "voice": voices_[i], "f0": f0 if target else None, "target": target,
                     "eq": (char_eq.get(seg_char[i], "") if (seg_char and i < len(seg_char)) else voice_eq.get(voices_[i], ""))})
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
        chain += "," + VOICE_POLISH
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
    return "Groq + xKiro"


def run_worker(job, item, settings, fonts_data):
    _API_LOCAL.isolated = True
    _API_LOCAL.xk_cfg = tuple(settings.get("user_xk_cfg") or ("", "", ""))
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
            if (duration <= 600
                    and (settings["auto_gender"]
                         or (settings["dub_on"] and (settings["voice_match"] or settings["emotion"] or settings.get("timbre"))))):
                analysis_pool = ThreadPoolExecutor(max_workers=1)
                def _analyze():
                    pcm_ = load_pcm(master_path)
                    return pcm_, pitch_track(pcm_)
                analysis_future = analysis_pool.submit(_analyze)
            _smap_cache = {}

            def get_smap():
                """ផែនទីអ្នកនិយាយ (ប្រុស/ស្រី) សាងសង់ម្តងគត់ ពីការវិភាគ pitch ដែលរត់ស្របពេលស្តាប់សំឡេង។"""
                if "v" not in _smap_cache:
                    v_ = None
                    if analysis_future is not None and settings["auto_gender"]:
                        try:
                            _pcm_, _trk_ = analysis_future.result()
                            v_ = build_speaker_map(_trk_, duration, settings["voice"])
                        except Exception:
                            v_ = None
                    _smap_cache["v"] = v_
                return _smap_cache["v"]

            def _gender_fn(a_, b_):
                sm_ = get_smap()
                return sm_.gender_at(a_, b_) if sm_ is not None else None

            item["pct"] = 0.25
            rep.write("៣/៤ កំពុងស្តាប់ និងបកប្រែជាភាសាខ្មែរ...")
            order = ["free"] if settings["groq_key"] else []
            segments = None
            used_engine = ""
            used_model = ""
            failed_chunks = 0
            engine_errors = []
            for idx, engine in enumerate(order):
                try:
                    if engine == "free":
                        segments, used_model, failed_chunks = transcribe_free(settings["groq_key"], audio_path, duration, settings["language"], rep, speech=speech, dub=settings["dub_on"], gemini_key=settings["gemini_key"], keep_failed=False, gender_fn=_gender_fn)
                    else:
                        raise RuntimeError("ម៉ាស៊ីនសម្គាល់សំឡេងនេះត្រូវបានបិទ។")
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
            if settings.get("review_on"):
                item["pct"] = 0.56
                _sm_r = get_smap()
                _gens_r = [(_sm_r.gender_at(a_, b_) if _sm_r is not None else None) for a_, b_, _t_ in segments]
                segments = review_segments_wait(item, segments, genders=_gens_r)
                _forced_r = item.pop("forced_voices", None)
                if _forced_r:
                    if get_smap() is None:
                        _smap_cache["v"] = SpeakerMap()
                    get_smap().set_overrides(_forced_r)
                rep.write("កំពុងបន្តជាមួយអក្សរដែលអ្នកបានកែ...")
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
                    _sm_d = get_smap()
                    dub_segments = merge_for_dub(segments, gender_fn=(_sm_d.gender_at if _sm_d is not None else None))
                    seg_voices = None
                    targets = None
                    emotions = None
                    voice_notes = []
                    pitch_inf = None
                    runs_ = None
                    ref_bands = None
                    seg_char = None
                    char_bands = None
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
                            if settings["auto_gender"]:
                                try:
                                    runs_, _info = gender_timeline(pcm, duration, settings["voice"], tracks=tracks)
                                    if runs_ is not None:
                                        seg_voices = voices_from_map(get_smap(), dub_segments, settings["voice"], runs_)
                                        voice_notes = voice_notes + [f"🗣 ប្រុស {sum(1 for v_ in seg_voices if v_ == VOICE_MALE)} / ស្រី {sum(1 for v_ in seg_voices if v_ == VOICE_FEMALE)} ឃ្លា"]
                                except Exception:
                                    seg_voices = None
                                    runs_ = None
                            if settings["voice_match"]:
                                targets = compute_targets(dub_segments, seg_voices, pitch_inf, runs_)
                            if settings.get("timbre_samples"):
                                import numpy as np
                                chars_ = []
                                for _n_, _raw_ in enumerate(settings["timbre_samples"]):
                                    try:
                                        _sp = os.path.join(folder, f"timbre_{_n_}.bin")
                                        with open(_sp, "wb") as _f:
                                            _f.write(_raw_)
                                        _pc = load_pcm(_sp)
                                        _t_, _f0_, _r_ = pitch_track(_pc)
                                        _vv = _f0_[_f0_ > 0]
                                        _med = float(np.median(_vv)) if len(_vv) >= 25 else None
                                        chars_.append({"f0": _med, "bands": band_levels(_pc), "n": _n_ + 1})
                                    except Exception:
                                        continue
                                _pc = None
                                _all_chars = len(chars_)
                                chars_ = [c_ for c_ in chars_ if c_["f0"]]
                                if len(chars_) < len(settings["timbre_samples"]):
                                    item["warn"].append("សំឡេងគំរូខ្លះមិនអាចវាស់ pitch បាន (ខ្លី ឬមិនច្បាស់) ត្រូវបានរំលង។")
                                if chars_:
                                    seg_voices, targets, seg_char, char_bands, _cn = assign_characters(dub_segments, chars_, pitch_inf)
                                    voice_notes = voice_notes + _cn
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
                            seg_char = None
                            char_bands = None
                            item["warn"].append("វិភាគសំឡេងអ្នកនិយាយមិនបាន ប្រើសំឡេងតែមួយតាមដែលបានជ្រើស។")
                    if seg_voices is None:
                        _smf = get_smap()
                        if _smf is not None and (_smf.over or _smf.mode != "none"):
                            seg_voices = voices_from_map(_smf, dub_segments, settings["voice"], None)
                    if settings["emotion"]:
                        try:
                            rep.write("🎭 កំពុងវិភាគអារម្មណ៍...")
                            emotions, emo_lines = plan_emotions(dub_segments, seg_voices, pitch_inf, runs_, settings["groq_key"], settings["gemini_key"])
                            voice_notes = voice_notes + emo_lines
                        except Exception:
                            emotions = None
                            item["warn"].append("វិភាគអារម្មណ៍មិនបាន ប្រើសំឡេងធម្មតា។")
                    rep.write("🎙 កំពុងបង្កើតសំឡេងខ្មែរ...")
                    match_notes = []
                    dub_ok = make_dub(folder, dub_segments, settings["voice"], duration, settings["keep_bg"], client, dub_model, seg_voices=seg_voices, targets=targets, notes=match_notes, emotions=emotions, groq_key=settings["groq_key"], ref_bands=ref_bands, offset=0.0, tight=True, bg_vol=settings.get("bg_vol", 0.08), seg_char=seg_char, char_bands=char_bands)
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


def review_segments_wait(item, segments, timeout=900, genders=None):
    """ផ្អាកដើម្បីឱ្យអ្នកប្រើកែអក្សរ Subtitle (ខ្មែរ) មុនបង្កើតសំឡេង និងដាក់ចូលវីដេអូ។"""
    ev = threading.Event()
    item["review_final"] = None
    item["review_final_genders"] = None
    item["review_genders"] = list(genders) if genders else [None] * len(segments)
    item["review_segments"] = [[float(a), float(b), str(t)] for a, b, t in segments]
    item["review_event"] = ev
    item["stage"] = "✏️ រង់ចាំអ្នកពិនិត្យ និងកែអក្សរ..."
    item["state"] = "review"
    _PIPELINE_SLOTS.release()   # ដោះជួរ ឱ្យវីដេអូផ្សេងធ្វើបានពេលរង់ចាំ
    try:
        got = ev.wait(timeout=timeout)
    finally:
        _PIPELINE_SLOTS.acquire()
    final = item.get("review_final")
    item["review_segments"] = None
    item["review_event"] = None
    item["review_final"] = None
    item["state"] = "running"
    if not got or not final:
        return segments
    out = []
    forced = []
    picks = item.get("review_final_genders") or []
    for k_, (a, b, t) in enumerate(final):
        t = fix_khmer(t)
        if t:
            out.append((float(a), float(b), t))
            g_ = picks[k_] if k_ < len(picks) else None
            if g_ in ("M", "F"):
                forced.append((float(a), float(b), g_))
    item["forced_voices"] = forced
    item["review_genders"] = None
    item["review_final_genders"] = None
    return out or segments


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


SPLIT_SECONDS = 6 * 60   # លំនាំដើម: បំបែកវីដេអូជាផ្នែកប្រវែង ៦ នាទី
SPLIT_PRESETS = {
    "៣០ វិនាទី": 30, "១ នាទី": 60, "២ នាទី": 120, "៣ នាទី": 180,
    "៥ នាទី": 300, "៦ នាទី": 360, "១០ នាទី": 600, "១៥ នាទី": 900,
}
SPLIT_QUEUE_MAX = 30   # ចំនួនផ្នែកអតិបរមាដែលផ្ញើទៅបកប្រែម្តង


def get_split_seconds():
    """ប្រវែងមួយផ្នែក (វិនាទី) តាមការកំណត់ក្នុងផ្ទាំងវីដេអូ។ 0 = មិនបំបែក។"""
    if not st.session_state.get("auto_split_toggle", True):
        return 0
    return SPLIT_PRESETS.get(st.session_state.get("split_len_pick"), SPLIT_SECONDS)


def fmt_len(sec):
    sec = int(sec)
    return f"{sec // 60} នាទី" if sec >= 60 and sec % 60 == 0 else f"{sec} វិនាទី"


def fmt_clock(sec):
    sec = int(round(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def link_or_copy(src, dst):
    """បង្កើត hard link (លឿន មិនចំណាយទំហំថ្មី) បើមិនបានទើបចម្លង។"""
    try:
        os.link(src, dst)
    except Exception:
        shutil.copyfile(src, dst)


def cut_clips(src, folder, prefix, seg_seconds, exact=False):
    """កាត់វីដេអូជាផ្នែកប្រវែង seg_seconds។
    លំនាំដើម: កាត់ដោយមិន encode (លឿន) ហើយបើបរាជ័យ ប្តូរទៅ encode ឡើងវិញដោយស្វ័យប្រវត្តិ។
    exact=True: encode ឡើងវិញជានិច្ច ដើម្បីកាត់ឱ្យចំពេលវេលា។
    ត្រឡប់បញ្ជីឯកសារតាមលំដាប់ (អាចទទេ)។"""
    seg = max(5, int(seg_seconds))
    pattern = os.path.join(folder, f"{prefix}%03d.mp4")

    def _list():
        out = sorted(os.path.join(folder, fn) for fn in os.listdir(folder)
                     if fn.startswith(prefix) and fn.endswith(".mp4"))
        return [pp for pp in out if os.path.getsize(pp) > 1000]

    def _clean():
        for fn in os.listdir(folder):
            if fn.startswith(prefix) and fn.endswith(".mp4"):
                try:
                    os.remove(os.path.join(folder, fn))
                except OSError:
                    pass

    base = ["-i", src, "-map", "0:v:0", "-map", "0:a:0?"]
    tail = ["-f", "segment", "-segment_time", str(seg), "-reset_timestamps", "1", pattern]
    copy_args = base + ["-c", "copy"] + tail
    enc_args = base + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-b:a", "128k",
                       "-force_key_frames", f"expr:gte(t,n_forced*{seg})"] + tail
    for args in ([enc_args] if exact else [copy_args, enc_args]):
        _clean()
        try:
            run_ffmpeg(args)
        except Exception:
            continue
        parts = _list()
        if parts:
            return parts
    return []


def split_video_parts(src, folder, idx, seg_seconds=None, exact=False):
    """បំបែកវីដេអូវែងជាផ្នែកខ្លីៗ ត្រឡប់បញ្ជីផ្លូវឯកសារតាមលំដាប់ ឬ None បើមិនចាំបាច់/បរាជ័យ។"""
    seg = int(seg_seconds or SPLIT_SECONDS)
    try:
        duration, _w, _h = probe_media(src)
    except Exception:
        return None
    if duration <= seg + 20:
        return None
    parts = cut_clips(src, folder, f"part_{idx}_", seg, exact)
    return parts if len(parts) > 1 else None


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


KM_UNITS = ["", "មួយ", "ពីរ", "បី", "បួន", "ប្រាំ", "ប្រាំមួយ", "ប្រាំពីរ", "ប្រាំបី", "ប្រាំបួន"]
KM_TENS = {1: "ដប់", 2: "ម្ភៃ", 3: "សាមសិប", 4: "សែសិប", 5: "ហាសិប",
           6: "ហុកសិប", 7: "ចិតសិប", 8: "ប៉ែតសិប", 9: "កៅសិប"}
ANN_VOICE = "km-KH-SreymomNeural"
_ANN_CACHE = {}


def khmer_number_word(n):
    n = int(n)
    if n <= 0 or n >= 100:
        return str(n)
    t, u = divmod(n, 10)
    return (KM_TENS[t] if t else "") + KM_UNITS[u]


def done_announcement_b64(n):
    """សំឡេងខ្មែរប្រកាសថាវីដេអូទី n បានធ្វើរួច (mp3 → base64) ។ រក្សាទុកក្នុង cache។"""
    text = f"វីដេអូទី{khmer_number_word(n)} បានធ្វើរួចហើយ។ អ្នកស្រី លោកម្ចាស់ អាចដោនឡូតបានហើយ។"
    if text in _ANN_CACHE:
        return _ANN_CACHE[text]
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        if not tts_retry(text, ANN_VOICE, path, tries=3):
            return None
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    _ANN_CACHE[text] = b64
    return b64


def announce_html(ann_id, b64):
    """លេងសំឡេងដោយស្វ័យប្រវត្តិ (ប្រើ Audio របស់ទំព័រមេ ដូច្នេះមិនដាច់ពេល element ត្រូវ refresh) ។
    បើ browser ហាមលេងស្វ័យប្រវត្តិ នឹងបង្ហាញប៊ូតុង «🔊» ឱ្យចុច។"""
    return """<script>
(function(){
  var P = window.parent || window;
  try {
    P.__kvPlayed = P.__kvPlayed || {};
    P.__kvQ = P.__kvQ || [];
    var id = "__ID__";
    if (P.__kvPlayed[id]) return;
    P.__kvPlayed[id] = 1;
    P.__kvQ.push("data:audio/mpeg;base64,__B64__");
    var next = function(){
      if (P.__kvBusy) return;
      var s = P.__kvQ.shift();
      if (!s) return;
      P.__kvBusy = true;
      var a = new P.Audio(s);
      var done = function(){ P.__kvBusy = false; next(); };
      a.onended = done; a.onerror = done;
      var pr = a.play();
      if (pr && pr.catch) pr.catch(function(){
        var d = P.document;
        if (d.getElementById("kv-ann-btn")) { P.__kvBusy = false; P.__kvQ.unshift(s); return; }
        var b = d.createElement("button");
        b.id = "kv-ann-btn";
        b.textContent = "🔊 ចុចដើម្បីស្តាប់សារ";
        b.style.cssText = "position:fixed;left:50%;bottom:90px;transform:translateX(-50%);z-index:99999;padding:14px 22px;border:0;border-radius:999px;background:#7C3AED;color:#fff;font-size:16px;font-weight:700;box-shadow:0 6px 20px rgba(0,0,0,.3)";
        b.onclick = function(){
          b.remove();
          a.onended = done; a.onerror = done;
          a.play().catch(done);
        };
        d.body.appendChild(b);
      });
    };
    next();
  } catch (e) {}
})();
</script>""".replace("__ID__", str(ann_id)).replace("__B64__", b64)


def announce_new_done(job):
    """ប្រកាសសំឡេងសម្រាប់វីដេអូដែលទើបធ្វើរួច (ម្តងមួយដង)។ ត្រឡប់ True បើមានការប្រកាស។"""
    if not st.session_state.get("announce_toggle", True):
        return False
    played = False
    for i, it in enumerate(job.items, start=1):
        if it["state"] == "done" and not it.get("announced"):
            it["announced"] = True
            try:
                b64 = done_announcement_b64(i)
            except Exception:
                b64 = None
            if b64:
                components.html(announce_html(f"{job.id}_{i}", b64), height=0)
                played = True
    return played


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
            elif it["state"] == "review" and it.get("review_segments") is not None:
                st.info("✏️ ពិនិត្យ និងកែអក្សរខ្មែរ រួចចុច «បន្ត» ដើម្បីបង្កើតសំឡេង និងដាក់អក្សរចូលវីដេអូ។ លុបអក្សរឃ្លាណាឱ្យទទេ ដើម្បីរំលងឃ្លានោះ។")
                with st.form(key=f"rvform_{job.id}_{i}"):
                    _edited = []
                    _picks = []
                    _gl = it.get("review_genders") or []
                    _gopts = ["🤖 ស្វ័យប្រវត្តិ", "♂ សំឡេងប្រុស", "♀ សំឡេងស្រី"]
                    for _k, (_a, _b, _t) in enumerate(it["review_segments"]):
                        _new = st.text_area(f"{_k + 1}. {fmt_clock(_a)} → {fmt_clock(_b)}", value=_t,
                                            key=f"rv_{job.id}_{i}_{_k}", height=80)
                        _g0 = _gl[_k] if _k < len(_gl) else None
                        _pick = st.selectbox("🎙 សំឡេងអាន (ប្រុស/ស្រី)", _gopts,
                                             index={"M": 1, "F": 2}.get(_g0, 0),
                                             key=f"rvg_{job.id}_{i}_{_k}")
                        _picks.append({"♂ សំឡេងប្រុស": "M", "♀ សំឡេងស្រី": "F"}.get(_pick))
                        _edited.append((_a, _b, _new))
                    _fc1, _fc2 = st.columns(2)
                    _go = _fc1.form_submit_button("✅ បន្ត (ប្រើអក្សរដែលកែ)", type="primary", use_container_width=True)
                    _skip = _fc2.form_submit_button("⏭ បន្តដោយមិនកែ", use_container_width=True)
                if _go or _skip:
                    it["review_final"] = _edited if _go else None
                    it["review_final_genders"] = _picks if _go else None
                    it["state"] = "running"
                    it["stage"] = "កំពុងបន្តជាមួយអក្សរដែលបានកែ..."
                    _ev = it.get("review_event")
                    if _ev is not None:
                        _ev.set()
                    time.sleep(0.5)
                    st.rerun()
            else:
                st.progress(max(0.0, min(1.0, it["pct"])), text=it["stage"])
            for w in it["warn"]:
                st.warning(w)
    _played = announce_new_done(job)
    if (was_running and not job.running()) or (reviewing != job.reviewing()):
        if _played:
            time.sleep(1.5)   # ឱ្យ browser ទទួលនិងចាប់ផ្តើមលេងសំឡេងសិន មុន rerun
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
<div id="m" style="color:#B42318;font-size:14px;margin-top:6px;font-family:system-ui,sans-serif;"></div>
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
      + '<a href="https://www.tiktok.com/tiktokstudio/upload" target="_blank" style="color:#1D4ED8">បើកទំព័រ TikTok</a>';
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
            if getattr(job, "text_only", False):
                st.markdown(f"**🎬 {it['name']}**")
                _vp0 = it.get("video_path")
                if _vp0 and os.path.isfile(_vp0):
                    with open(_vp0, "rb") as _vf0:
                        dl_button("⬇️ ទាញយកវីដេអូ", _vf0, f"{safe_filename(it['name'])}_khmer.mp4", "video/mp4",
                                  key=f"dl_{job.id}_{i}", use_container_width=True)
                for text in it["captions"]:
                    st.write(text)
                continue
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
    if getattr(job, "text_only", False) and done:
        _all_txt = "\n\n".join(f"== {_it['name']} ==\n" + "\n".join(_it["captions"]) for _i, _it in done)
        dl_button("📝 ទាញយកអក្សរបកប្រែទាំងអស់ (.txt)", _all_txt.encode("utf-8"), "khmer_text.txt", "text/plain",
                  key=f"txt_{job.id}", use_container_width=True)
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
# អាចប្រើ GROQ_API_KEY_1, GROQ_API_KEY_2 ... បាន។
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


# =====================================================================
#  API Key ផ្ទាល់ខ្លួនរបស់អ្នកប្រើ — ដាក់បានច្រើន Key + សេវទុកក្នុង Browser
#  Key រក្សាទុកក្នុង localStorage របស់ Browser អ្នកប្រើផ្ទាល់ (មិនផ្ញើទៅរក្សាទុកលើម៉ាស៊ីនមេទេ)
#  ពេលចូលលើកក្រោយ កម្មវិធីអានវិញដោយស្វ័យប្រវត្តិ
# =====================================================================
_LS_HTML = """<!doctype html><html><body><script>
(function () {
  var KEY = "kvai_user_keys_v1", lastNonce = null, sent = false;
  function send(type, data) {
    window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*");
  }
  function readStore() { try { return localStorage.getItem(KEY) || ""; } catch (e) { return ""; } }
  window.addEventListener("message", function (ev) {
    var d = ev.data;
    if (!d || d.type !== "streamlit:render") return;
    var a = d.args || {};
    if (a.nonce !== undefined && a.nonce !== lastNonce) {
      lastNonce = a.nonce;
      if (a.save !== null && a.save !== undefined) {
        try {
          if (a.save === "") localStorage.removeItem(KEY); else localStorage.setItem(KEY, a.save);
        } catch (e) {}
      }
    }
    if (!sent) {
      sent = true;
      send("streamlit:setComponentValue", {value: {data: readStore()}, dataType: "json"});
    }
  });
  send("streamlit:componentReady", {apiVersion: 1});
  send("streamlit:setFrameHeight", {height: 0});
})();
</script></body></html>"""


@st.cache_resource(show_spinner=False)
def _kv_component():
    folder = os.path.join(tempfile.gettempdir(), "kvai_ls_component")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(_LS_HTML)
    return components.declare_component("kvai_local_storage", path=folder)


def _ls_persist():
    """រៀបចំទិន្នន័យ Key ដើម្បីសរសេរចូល localStorage នៅពេល rerun បន្ទាប់។"""
    ss = st.session_state
    groq = list(ss.get("user_groq_keys", []))
    oai = {"key": ss.get("user_oai_key", ""), "base": ss.get("user_oai_base", "https://api.xkiro.com/v1"),
           "model": ss.get("user_oai_model", "qwen/qwen3.5-flash")}
    claude = {"keys": list(ss.get("user_claude_keys", [])),
              "base": ss.get("user_claude_base", "https://api.laalaa.me"),
              "model": ss.get("user_claude_model", "claude-sonnet-5-5")}
    if not ss.get("remember_keys", True) or not (groq or oai["key"] or claude["keys"]):
        payload = ""
    else:
        payload = json.dumps({"groq": groq, "oai": oai, "claude": claude})
    ss["_ls_payload"] = payload
    ss["_ls_nonce"] = ss.get("_ls_nonce", 0) + 1


def ls_sync():
    """ហៅមួយដងក្នុងមួយ run: សរសេរ Key ថ្មីចូល Browser និងអាន Key ដែលបានរក្សាទុកពីមុនមកវិញ។"""
    try:
        res = _kv_component()(save=st.session_state.get("_ls_payload"),
                              nonce=st.session_state.get("_ls_nonce", 0),
                              default=None, key="kv_ls")
    except Exception:
        return
    if not res or st.session_state.get("_ls_loaded"):
        return
    st.session_state["_ls_loaded"] = True
    raw = (res.get("data") if isinstance(res, dict) else "") or ""
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        return
    sk, name = "user_groq_keys", "groq"
    merged = split_keys([st.session_state.get(sk, []), data.get(name) or []])
    if merged:
        st.session_state[sk] = merged
    oai = data.get("oai") or {}
    if isinstance(oai, dict) and oai.get("key") and not st.session_state.get("user_oai_key"):
        st.session_state["user_oai_key"] = str(oai.get("key", "")).strip()
        st.session_state["user_oai_base"] = str(oai.get("base", "")).strip()
        st.session_state["user_oai_model"] = str(oai.get("model", "")).strip()
    cl = data.get("claude") or {}
    if isinstance(cl, dict) and cl.get("keys"):
        _merged_c = split_keys([st.session_state.get("user_claude_keys", []), cl.get("keys") or []])
        if _merged_c:
            st.session_state["user_claude_keys"] = _merged_c
            if cl.get("base") and not st.session_state.get("user_claude_base"):
                st.session_state["user_claude_base"] = str(cl.get("base")).strip()
            if cl.get("model") and not st.session_state.get("user_claude_model"):
                st.session_state["user_claude_model"] = str(cl.get("model")).strip()


def has_user_keys():
    ss = st.session_state
    return bool(ss.get("user_groq_keys") or ss.get("user_oai_key") or ss.get("user_claude_keys"))


def effective_groq_key():
    """Key របស់អ្នកប្រើ (បើមាន) មុន ហើយ key របស់កម្មវិធីជាបម្រុង។"""
    mine = st.session_state.get("user_groq_keys", [])
    return "\n".join(split_keys([mine, GROQ_KEY])) if mine else GROQ_KEY


def effective_gemini_key():
    # Gemini removed by request. Do not load or call Gemini keys/models.
    return ""


def mask_key(k):
    k = str(k)
    return (k[:4] + "…" + k[-4:]) if len(k) > 10 else "…"


def _classify_http(code):
    if code == 200:
        return "ok", "ប្រើបាន"
    if code in (401, 403):
        return "bad", "Key មិនត្រឹមត្រូវ ឬត្រូវបានបិទ"
    if code == 402:
        return "bad", "អស់ credit / ត្រូវបង់ប្រាក់"
    if code == 404:
        return "bad", "URL ឬឈ្មោះម៉ូដែលខុស"
    if code in (503, 529):
        return "limit", "Key ត្រឹមត្រូវ តែម៉ាស៊ីនមេរវល់ ឬគ្មាន account ទំនេរបណ្តោះអាសន្ន"
    if code == 429:
        return "limit", "Key ត្រឹមត្រូវ តែអស់កូតា ឬ Rate limit បណ្តោះអាសន្ន"
    return "error", f"HTTP {code}"


def _http_probe(url, headers, payload=None, timeout=30, secret=""):
    """ហៅម្តង (គ្មាន retry) ហើយត្រឡប់ (state, សារ, ms)។ មិនបង្ហាញ Key ក្នុងសារ។"""
    t0 = time.time()
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(2000)
        return "ok", "ប្រើបាន", int((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        state, msg = _classify_http(e.code)
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:160].replace("\n", " ")
        except Exception:
            pass
        if secret:
            detail = detail.replace(secret, "***")
        if detail and state in ("error", "bad", "limit"):
            msg += " · HTTP " + str(e.code) + " · " + detail
        return state, msg, int((time.time() - t0) * 1000)
    except Exception as e:
        return "error", "បណ្តាញ/Timeout: " + str(e)[:120], int((time.time() - t0) * 1000)


def check_groq_key(cfg):
    key = cfg[0]
    return _http_probe(GROQ_MODELS_URL, {"Authorization": f"Bearer {key}", "User-Agent": "Mozilla/5.0"}, secret=key)


def check_claude_key(cfg):
    key, base, model = cfg
    base = str(base).rstrip("/")
    url = base + ("/messages" if base.endswith("/v1") else "/v1/messages")
    headers = {"x-api-key": key, "Authorization": f"Bearer {key}", "anthropic-version": "2023-06-01",
               "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    models = [model] + [m for m in _CLAUDE_FALLBACK_MODELS if m != model]
    res = ("error", "មិនទាន់សាក", 0)
    for m in models:
        payload = {"model": m, "max_tokens": 8, "messages": [{"role": "user", "content": "hi"}]}
        res = _http_probe(url, headers, payload, secret=key)
        if res[0] == "ok":
            _CLAUDE_GOOD_MODEL[key] = m
            if m != model:
                return "ok", f"ប្រើបាន (model «{m}» ដំណើរការ — សូមដាក់ឈ្មោះនេះក្នុងប្រអប់ Model)", res[2]
            return res
        if res[0] == "bad" and "មិនត្រឹមត្រូវ" in res[1]:
            return res      # Key ខុស — មិនបាច់សាក model ផ្សេង
        time.sleep(1.2)
    return res[0], res[1] + " · (សាកគ្រប់ model ហើយ៖ " + ", ".join(models) + ")", res[2]


def check_openai_key(cfg):
    key, base, model = cfg
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    payload = {"model": model, "max_tokens": 8, "messages": [{"role": "user", "content": "hi"}]}
    return _http_probe(str(base).rstrip("/") + "/chat/completions", headers, payload, secret=key)


def key_check_targets():
    """ពិនិត្យតែ API Key ផ្ទាល់ខ្លួនរបស់ session នេះប៉ុណ្ណោះ។"""
    ss = st.session_state
    rows = []
    for i, k in enumerate(ss.get("user_claude_keys", []), start=1):
        _b = ss.get("user_claude_base", "https://api.laalaa.me")
        _m = ss.get("user_claude_model", "claude-sonnet-5-5")
        rows.append((f"Claude ផ្ទាល់ខ្លួន #{i}", mask_key(k), "claude", (k, _b, _m), _m))
    for i, k in enumerate(ss.get("user_groq_keys", []), start=1):
        rows.append((f"Groq ផ្ទាល់ខ្លួន #{i}", mask_key(k), "groq", (k,), "whisper + chat"))
    if ss.get("user_oai_key"):
        _cfg = (ss["user_oai_key"], ss.get("user_oai_base", "https://api.xkiro.com/v1"),
                ss.get("user_oai_model", "qwen/qwen3.5-flash"))
        rows.append(("xKiro ផ្ទាល់ខ្លួន", mask_key(_cfg[0]), "openai", _cfg, _cfg[2]))
    return rows


def run_key_checks():
    targets = key_check_targets()
    fn = {"groq": check_groq_key, "claude": check_claude_key, "openai": check_openai_key}

    def one(t):
        name, masked, kind, cfg, model = t
        try:
            state, msg, ms = fn[kind](cfg)
        except Exception as e:
            state, msg, ms = "error", str(e)[:140], 0
        return {"name": name, "key": masked, "model": model, "state": state, "msg": msg, "ms": ms}

    if not targets:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
        return list(pool.map(one, targets))


def user_key_box():
    """ប្រអប់ឱ្យអ្នកប្រើដាក់ API Key ផ្ទាល់ខ្លួនបានច្រើន (Groq / xKiro) ហើយសេវទុកក្នុង Browser។"""
    if st.session_state.pop("_clear_key_input", False):
        st.session_state.pop("user_key_input", None)
        st.session_state.pop("user_keys_bulk", None)
        st.session_state.pop("user_claude_bulk", None)
    with st.container(border=True):
        st.markdown("**🔑 API Key ផ្ទាល់ខ្លួន (ដាក់បានច្រើន Key)**")
        st.caption("បើ API របស់កម្មវិធីអស់កូតា ឬបរាជ័យ សូមដាក់ Groq Key សម្រាប់សម្គាល់សំឡេង និង xKiro Key សម្រាប់បកប្រែ។ "
                   "ដាក់បានច្រើន Key — Key មួយអស់កូតា កម្មវិធីប្តូរទៅ Key បន្ទាប់ដោយស្វ័យប្រវត្តិ។")
        _msg = st.session_state.pop("_key_msg", None)
        if _msg:
            (st.success if _msg[0] == "ok" else st.warning)(_msg[1])
        any_saved = False
        for name, sk in (("Claude", "user_claude_keys"), ("Groq", "user_groq_keys")):
            lst = list(st.session_state.get(sk, []))
            if not lst:
                continue
            any_saved = True
            st.markdown(f"✅ **{name}** · {len(lst)} Key")
            for n, k in enumerate(lst):
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"`{mask_key(k)}`")
                if c2.button("🗑", key=f"del_{sk}_{n}", help="លុប Key នេះ"):
                    st.session_state[sk] = [x for i, x in enumerate(lst) if i != n]
                    _ls_persist()
                    st.rerun()
        if st.session_state.get("user_oai_key"):
            any_saved = True
            st.success(f"✅ កំពុងប្រើ xKiro Key របស់អ្នក (…{st.session_state['user_oai_key'][-4:]})")
            if st.button("🗑 ឈប់ប្រើ xKiro Key", key="remove_user_oai_key"):
                for _k in ("user_oai_key", "user_oai_base", "user_oai_model"):
                    st.session_state.pop(_k, None)
                _ls_persist()
                st.rerun()
        provider = st.radio("ប្រភេទ Key", ["Claude", "Groq", "xKiro"], horizontal=True, key="user_key_provider")
        oai_base_in = oai_model_in = ""
        typed = ""
        if provider == "Claude":
            typed = st.text_area("Claude API Key (មួយបន្ទាត់ ១ Key — ដាក់បានច្រើន)",
                                 placeholder="sk-...", height=100, key="user_claude_bulk")
            oai_base_in = st.text_input("Base URL (ដាក់តាមហាង បើមិនមាន ទុកលំនាំដើម)",
                                        value=st.session_state.get("user_claude_base", "https://api.laalaa.me"),
                                        key="user_claude_base_input")
            oai_model_in = st.text_input("ឈ្មោះម៉ូដែល",
                                         value=st.session_state.get("user_claude_model", "claude-sonnet-5-5"),
                                         key="user_claude_model_input")
            st.caption("Claude ប្រើសម្រាប់បកប្រែ និងកែសម្រួលអត្ថបទជាខ្មែរ (សាកមុនគេ)។ ការស្តាប់សំឡេងនៅតែត្រូវការ Groq Key ព្រោះ Claude មិនស្តាប់សំឡេងទេ។")
        elif provider == "xKiro":
            typed = st.text_input("xKiro API Key", type="password", placeholder="xkiro_...", key="user_key_input")
            oai_base_in = st.text_input("Base URL", value=st.session_state.get("user_oai_base", "https://api.xkiro.com/v1"),
                                        key="user_oai_base_input")
            oai_model_in = st.text_input("ឈ្មោះម៉ូដែល", value=st.session_state.get("user_oai_model", "qwen/qwen3.5-flash"),
                                         key="user_oai_model_input")
            st.caption("xKiro ប្រើសម្រាប់បកប្រែ និងកែសម្រួលអត្ថបទ។ ការសម្គាល់សំឡេងវីដេអូនៅតែត្រូវការ Groq ព្រោះ xKiro មិនមាន Speech-to-Text API។")
        else:
            typed = st.text_area("Groq API Key (មួយបន្ទាត់ ១ Key ឬបំបែកដោយក្បៀស — ដាក់បានច្រើន)",
                                 placeholder="gsk_...\ngsk_...", height=120, key="user_keys_bulk")
        st.toggle("💾 ចងចាំ Key ក្នុងឧបករណ៍/Browser នេះ (ចូលលើកក្រោយមិនបាច់ដាក់ម្តងទៀត)", value=True,
                  key="remember_keys", on_change=_ls_persist)
        st.caption("🔒 Key រក្សាទុកក្នុង Browser របស់អ្នកតែប៉ុណ្ណោះ (localStorage) មិនត្រូវបានរក្សាទុកលើម៉ាស៊ីនមេទេ។ "
                   "កុំប្រើលើកុំព្យូទ័រ/ទូរស័ព្ទសាធារណៈ។ បើលុបទិន្នន័យ Browser Key នឹងបាត់។")
        if st.button("✅ ពិនិត្យ និងបន្ថែម Key", key="user_key_save", use_container_width=True):
            if provider == "Claude":
                _new = [_x for _x in split_keys(typed) if _x.startswith("sk-") and "=" not in _x][:20]
                _base = (oai_base_in or "https://api.laalaa.me").strip().rstrip("/")
                _model = (oai_model_in or "claude-sonnet-5-5").strip()
                _have = list(st.session_state.get("user_claude_keys", []))
                if not _new:
                    st.error("សូមបិទភ្ជាប់ Key យ៉ាងតិច ១។")
                elif not _base.startswith("http"):
                    st.error("Base URL ត្រូវចាប់ផ្តើមដោយ https://")
                else:
                    _added, _dup, _bad = 0, 0, []
                    with st.spinner("កំពុងពិនិត្យ Key..."):
                        for _k in _new:
                            if _k in _have:
                                _dup += 1
                                continue
                            _st, _msg, _ms = check_claude_key((_k, _base, _model))
                            if _st in ("ok", "limit"):
                                _have.append(_k)
                                _added += 1
                            else:
                                _bad.append(f"{mask_key(_k)}: {_msg}")
                    if _added:
                        st.session_state["user_claude_keys"] = _have
                        st.session_state["user_claude_base"] = _base
                        st.session_state["user_claude_model"] = _model
                        _ls_persist()
                    _text = f"បានបន្ថែម {_added} Claude Key ✅"
                    if _dup:
                        _text += f" · ស្ទួន {_dup}"
                    if _bad:
                        _text += f" · មិនត្រឹមត្រូវ {len(_bad)}:\n\n" + "\n\n".join(_bad)
                    st.session_state["_key_msg"] = ("ok" if _added else "warn", _text)
                    if _added:
                        st.session_state["_clear_key_input"] = True
                    st.rerun()
            elif provider == "xKiro":
                ok, msg = oai_test(typed, oai_base_in or "https://api.xkiro.com/v1", oai_model_in or "qwen/qwen3.5-flash")
                if ok:
                    st.session_state["user_oai_key"] = typed.strip()
                    st.session_state["user_oai_base"] = (oai_base_in or "https://api.xkiro.com/v1").strip().rstrip("/")
                    st.session_state["user_oai_model"] = (oai_model_in or "qwen/qwen3.5-flash").strip()
                    _ls_persist()
                    st.session_state["_clear_key_input"] = True
                    st.session_state["_key_msg"] = ("ok", "បានបន្ថែម xKiro Key ✅")
                    st.rerun()
                else:
                    st.error(msg)
            else:
                sk = "user_groq_keys"
                check = validate_groq_key
                new_keys = split_keys(typed)[:20]
                have = list(st.session_state.get(sk, []))
                if not new_keys:
                    st.error("សូមបិទភ្ជាប់ Key យ៉ាងតិច ១។")
                else:
                    added, dup, bad = 0, 0, []
                    with st.spinner("កំពុងពិនិត្យ Key..."):
                        for k in new_keys:
                            if k in have:
                                dup += 1
                                continue
                            ok, msg = check(k)
                            if ok:
                                have.append(k)
                                added += 1
                            else:
                                bad.append(f"{mask_key(k)}: {msg}")
                    if added:
                        st.session_state[sk] = have
                        _ls_persist()
                    text = f"បានបន្ថែម {added} Key ✅"
                    if dup:
                        text += f" · ស្ទួន {dup}"
                    if bad:
                        text += f" · មិនត្រឹមត្រូវ {len(bad)}:\n\n" + "\n\n".join(bad)
                    st.session_state["_key_msg"] = ("ok" if added else "warn", text)
                    if added:
                        st.session_state["_clear_key_input"] = True
                    st.rerun()
        if st.button("🔍 ពិនិត្យ Key ទាំងអស់ — ណាប្រើបាន ណាប្រើមិនបាន", key="user_key_check_all", use_container_width=True):
            with st.spinner("កំពុងពិនិត្យ..."):
                st.session_state["_key_check"] = {"t": time.time(), "rows": run_key_checks()}
        _kc = st.session_state.get("_key_check")
        if _kc:
            if not _kc["rows"]:
                st.info("មិនទាន់មាន Key ណាមួយទេ។")
            else:
                _icon = {"ok": "✅ ប្រើបាន", "limit": "⚠️ Limit/រវល់", "bad": "❌ មិនត្រឹមត្រូវ", "error": "❌ កំហុស"}
                _c1, _c2, _c3 = st.columns(3)
                _c1.metric("✅ ប្រើបាន", sum(1 for r in _kc["rows"] if r["state"] == "ok"))
                _c2.metric("⚠️ Limit/រវល់", sum(1 for r in _kc["rows"] if r["state"] == "limit"))
                _c3.metric("❌ ប្រើមិនបាន", sum(1 for r in _kc["rows"] if r["state"] in ("bad", "error")))
                st.dataframe(
                    [{"ស្ថានភាព": _icon[r["state"]], "Provider": r["name"], "Key": r["key"],
                      "ម៉ូដែល": r["model"], "ms": r["ms"], "ព័ត៌មាន": r["msg"]} for r in _kc["rows"]],
                    use_container_width=True, hide_index=True)
                for _r in _kc["rows"]:
                    if _r["state"] != "ok":
                        st.warning(f"{_r['name']} · {_r['key']} · {_r['model']}\n\n{_r['msg']}")
                st.caption("ពិនិត្យនៅម៉ោង " + time.strftime("%H:%M:%S", time.localtime(_kc["t"]))
                           + " · ⚠️ = Key ត្រឹមត្រូវ តែ Rate limit/ម៉ាស៊ីនមេរវល់បណ្តោះអាសន្ន (មិនទាន់ច្បាស់ថាអស់កូតាទេ)។")
        if any_saved and st.button("🧹 លុប Key ផ្ទាល់ខ្លួនទាំងអស់ (រួមទាំងក្នុង Browser)", key="user_key_clear_all", use_container_width=True):
            for _k in ("user_groq_keys", "user_oai_key", "user_oai_base", "user_oai_model",
                       "user_claude_keys", "user_claude_base", "user_claude_model"):
                st.session_state.pop(_k, None)
            _ls_persist()
            st.rerun()


# =====================================================================
#  ចូលប្រើតាមគណនី Google (Gmail) — ត្រូវចូលមុនទើបប្រើកម្មវិធីបាន
#  ► បិទបាន៖ ដាក់ REQUIRE_LOGIN = "0" ក្នុង Secrets
#  ► កំណត់អ្នកអនុញ្ញាត (មិនចាំបាច់)៖ ALLOWED_EMAILS = "a@gmail.com, b@gmail.com"
# =====================================================================
REQUIRE_LOGIN = str(get_secret("REQUIRE_LOGIN", "1")).strip().lower() not in ("0", "false", "no", "off")

_AUTH_SETUP_HELP = """# .streamlit/secrets.toml (ឬ Streamlit Cloud → Settings → Secrets)
[auth]
redirect_uri = "https://ឈ្មោះកម្មវិធីរបស់អ្នក.streamlit.app/oauth2callback"
cookie_secret = "ដាក់អក្សរចៃដន្យវែងៗ ៣២ តួឡើង"

[auth.google]
client_id = "xxxx.apps.googleusercontent.com"
client_secret = "xxxx"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
"""


def _auth_configured():
    try:
        _a = st.secrets["auth"]
        return bool(_a.get("cookie_secret")) and bool(_a.get("redirect_uri")) and "google" in _a
    except Exception:
        return False


def _user_field(key, default=""):
    try:
        v = st.user.get(key)
        return default if v is None else v
    except Exception:
        try:
            v = getattr(st.user, key)
            return default if v is None else v
        except Exception:
            return default


def _allowed_email_set():
    raw = get_secret("ALLOWED_EMAILS", "")
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = re.split(r"[,\n;\s]+", str(raw or ""))
    return {str(x).strip().lower() for x in items if str(x).strip()}


_GOOGLE_G_URI = "data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2048%2048%22%3E%3Cpath%20fill%3D%22%23EA4335%22%20d%3D%22M24%209.5c3.54%200%206.71%201.22%209.21%203.6l6.85-6.85C35.9%202.38%2030.47%200%2024%200%2014.62%200%206.51%205.38%202.56%2013.22l7.98%206.19C12.43%2013.72%2017.74%209.5%2024%209.5z%22%2F%3E%3Cpath%20fill%3D%22%234285F4%22%20d%3D%22M46.98%2024.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58%202.96-2.26%205.48-4.78%207.18l7.73%206c4.51-4.18%207.09-10.36%207.09-17.65z%22%2F%3E%3Cpath%20fill%3D%22%23FBBC05%22%20d%3D%22M10.53%2028.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92%2016.46%200%2020.12%200%2024c0%203.88.92%207.54%202.56%2010.78l7.97-6.19z%22%2F%3E%3Cpath%20fill%3D%22%2334A853%22%20d%3D%22M24%2048c6.48%200%2011.93-2.13%2015.89-5.81l-7.73-6c-2.15%201.45-4.92%202.3-8.16%202.3-6.26%200-11.57-4.22-13.47-9.91l-7.98%206.19C6.51%2042.62%2014.62%2048%2024%2048z%22%2F%3E%3C%2Fsvg%3E"

_LOGIN_CSS = """<style>
.st-key-kv_login{max-width:460px;margin:3vh auto 0;padding:30px 24px 22px;border-radius:26px;
background:linear-gradient(165deg,rgba(26,36,92,.97),rgba(11,16,48,.97));
border:1px solid rgba(130,150,255,.38);box-shadow:0 20px 60px rgba(0,0,0,.5);}
.st-key-kv_login .kv-ic{width:68px;height:68px;margin:0 auto 16px;border-radius:20px;display:flex;align-items:center;justify-content:center;font-size:34px;
background:linear-gradient(135deg,#FF2DAA,#7B5CFF 60%,#19B7FF);box-shadow:0 10px 28px rgba(123,92,255,.45);}
.st-key-kv_login .kv-t{margin:0 0 6px;text-align:center;font-size:24px;font-weight:800;color:#FFFFFF!important;line-height:1.5;}
.st-key-kv_login .kv-s{margin:0 0 16px;text-align:center;font-size:15px;line-height:1.7;color:#B9C4EE!important;}
.st-key-kv_login .kv-l{margin:0 0 20px;padding:10px 14px;border-radius:14px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);}
.st-key-kv_login .kv-l div{font-size:14px;line-height:1.95;color:#DCE3FF!important;}
.st-key-kv_login .kv-f{margin-top:14px;text-align:center;font-size:12.5px;line-height:1.6;color:#8E9BCB!important;}
.st-key-kv_login_btn button,.st-key-kv_logout_unverified button,.st-key-kv_logout_denied button{
width:100%;min-height:54px;border-radius:14px!important;border:none!important;background:#FFFFFF!important;
box-shadow:0 8px 22px rgba(0,0,0,.35);transition:transform .12s ease,box-shadow .12s ease;}
.st-key-kv_login_btn button:hover{transform:translateY(-1px);box-shadow:0 12px 28px rgba(0,0,0,.45);}
.st-key-kv_login_btn button p,.st-key-kv_logout_unverified button p,.st-key-kv_logout_denied button p{color:#1F2A44!important;font-weight:700;font-size:16px;}
.st-key-kv_login_btn button p::before{content:"";display:inline-block;width:22px;height:22px;margin-right:12px;vertical-align:-5px;
background:url("data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2048%2048%22%3E%3Cpath%20fill%3D%22%23EA4335%22%20d%3D%22M24%209.5c3.54%200%206.71%201.22%209.21%203.6l6.85-6.85C35.9%202.38%2030.47%200%2024%200%2014.62%200%206.51%205.38%202.56%2013.22l7.98%206.19C12.43%2013.72%2017.74%209.5%2024%209.5z%22%2F%3E%3Cpath%20fill%3D%22%234285F4%22%20d%3D%22M46.98%2024.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58%202.96-2.26%205.48-4.78%207.18l7.73%206c4.51-4.18%207.09-10.36%207.09-17.65z%22%2F%3E%3Cpath%20fill%3D%22%23FBBC05%22%20d%3D%22M10.53%2028.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92%2016.46%200%2020.12%200%2024c0%203.88.92%207.54%202.56%2010.78l7.97-6.19z%22%2F%3E%3Cpath%20fill%3D%22%2334A853%22%20d%3D%22M24%2048c6.48%200%2011.93-2.13%2015.89-5.81l-7.73-6c-2.15%201.45-4.92%202.3-8.16%202.3-6.26%200-11.57-4.22-13.47-9.91l-7.98%206.19C6.51%2042.62%2014.62%2048%2024%2048z%22%2F%3E%3C%2Fsvg%3E") center/contain no-repeat;}
</style>"""

_ACCOUNT_CSS = """<style>
.st-key-kv_account{margin:2px 0 10px;padding:8px 12px;border-radius:16px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);}
.st-key-kv_account [data-testid="stHorizontalBlock"]{flex-direction:row!important;flex-wrap:nowrap!important;align-items:center;gap:8px!important;}
.st-key-kv_account [data-testid="stColumn"],.st-key-kv_account [data-testid="column"]{min-width:0!important;}
.st-key-kv_account [data-testid="stColumn"]:last-child,.st-key-kv_account [data-testid="column"]:last-child{flex:0 0 auto!important;width:auto!important;}
.st-key-kv_account .kv-u{display:flex;align-items:center;gap:10px;min-width:0;}
.st-key-kv_account .kv-u img,.st-key-kv_account .kv-u .kv-av{width:36px;height:36px;border-radius:50%;flex:0 0 36px;object-fit:cover;}
.st-key-kv_account .kv-av{display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#FF2DAA,#7B5CFF);color:#fff;font-weight:800;}
.st-key-kv_account .kv-n{font-weight:700;font-size:14px;color:#FFFFFF!important;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.st-key-kv_account .kv-m{font-size:12px;color:#B9C4EE!important;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.st-key-kv_account .kv-t2{min-width:0;}
.st-key-kv_account button{min-height:38px;padding:0 14px;border-radius:12px;}
</style>"""


def _login_screen(icon, title, sub, items=None):
    """បង្ហាញកាតចូលប្រើតាម theme ងងឹត ហើយត្រឡប់ container ដើម្បីដាក់ប៊ូតុងក្នុងកាត។"""
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    box = st.container(key="kv_login")
    with box:
        html = f'<div class="kv-ic">{icon}</div><div class="kv-t">{title}</div><div class="kv-s">{sub}</div>'
        if items:
            html += '<div class="kv-l">' + "".join(f"<div>{x}</div>" for x in items) + "</div>"
        st.markdown(html, unsafe_allow_html=True)
    return box


def require_login():
    """បិទមិនឱ្យប្រើកម្មវិធី ទាល់តែចូលតាមគណនី Google។ គណនីថ្មីត្រូវបានបង្កើតស្វ័យប្រវត្តិពេលចូលលើកដំបូង។"""
    if not REQUIRE_LOGIN:
        return
    if not (hasattr(st, "login") and hasattr(st, "user")):
        st.error("Streamlit ចាស់ពេក — សូមដាក់ `streamlit>=1.42.0` និង `Authlib>=1.3.2` ក្នុង requirements.txt។")
        st.stop()
    if not _auth_configured():
        _login_screen("⚙️", "កម្មវិធីកំពុងរៀបចំ", "អ្នកគ្រប់គ្រងមិនទាន់កំណត់ Google Login ទេ។ សូមត្រឡប់មកវិញពេលក្រោយ។")
        with st.expander("🛠️ សម្រាប់អ្នកគ្រប់គ្រង — របៀបកំណត់"):
            st.markdown(
                "1. Google Cloud Console → APIs & Services → Credentials → **Create OAuth client ID** (Web application)។\n"
                "2. ដាក់ **Authorized redirect URI** ជា `https://ឈ្មោះកម្មវិធី.streamlit.app/oauth2callback` "
                "(ក្នុងម៉ាស៊ីនខ្លួនឯង៖ `http://localhost:8501/oauth2callback`)។\n"
                "3. ដាក់ Secrets ដូចខាងក្រោម ហើយដាក់ `Authlib>=1.3.2` ក្នុង requirements.txt។"
            )
            st.code(_AUTH_SETUP_HELP, language="toml")
        st.stop()

    if not _user_field("is_logged_in", False):
        box = _login_screen(
            "🎬", "ចូលប្រើ Khmer Video AI",
            "ចូលតាមគណនី Google របស់អ្នក ដើម្បីចាប់ផ្តើមបកប្រែវីដេអូ",
            ["🎙️ បកប្រែវីដេអូជាសំឡេង និង Subtitle ខ្មែរ",
             "⚡ គណនីថ្មីត្រូវបានបង្កើតស្វ័យប្រវត្តិ",
             "🔒 យើងមិនឃើញពាក្យសម្ងាត់ Google របស់អ្នកទេ"],
        )
        with box:
            st.button("ចូលតាម Google", key="kv_login_btn", use_container_width=True,
                      on_click=st.login, args=("google",))
            st.markdown('<div class="kv-f">ត្រូវការគណនី Gmail ឬ Google ដើម្បីប្រើកម្មវិធី</div>', unsafe_allow_html=True)
        st.stop()

    _email = str(_user_field("email", "")).strip().lower()
    if not _email or _user_field("email_verified", True) is False:
        box = _login_screen("⚠️", "អ៊ីមែលមិនទាន់បញ្ជាក់", "គណនី Google នេះមិនទាន់បញ្ជាក់អ៊ីមែលទេ។ សូមប្រើគណនីផ្សេង។")
        with box:
            st.button("ចាកចេញ", key="kv_logout_unverified", on_click=st.logout, use_container_width=True)
        st.stop()
    _allowed = _allowed_email_set()
    if _allowed and _email not in _allowed:
        from html import escape as _esc
        box = _login_screen("⛔", "គ្មានសិទ្ធិប្រើ", f"គណនី <b>{_esc(_email)}</b> មិនមានក្នុងបញ្ជីអនុញ្ញាតទេ។")
        with box:
            st.button("ចាកចេញ", key="kv_logout_denied", on_click=st.logout, use_container_width=True)
        st.stop()

    from html import escape as _esc
    _name = str(_user_field("name", "") or _email)
    _pic = str(_user_field("picture", "") or "")
    st.markdown(_ACCOUNT_CSS, unsafe_allow_html=True)
    with st.container(key="kv_account"):
        _a, _b = st.columns([6, 2])
        with _a:
            _av = (f'<img src="{_esc(_pic)}" referrerpolicy="no-referrer">' if _pic.startswith("https://")
                   else f'<div class="kv-av">{_esc(_name[:1].upper())}</div>')
            st.markdown(
                f'<div class="kv-u">{_av}<div class="kv-t2"><div class="kv-n">{_esc(_name)}</div>'
                f'<div class="kv-m">{_esc(_email)}</div></div></div>',
                unsafe_allow_html=True,
            )
        with _b:
            st.button("ចាកចេញ", key="kv_logout_btn", on_click=st.logout)


GEMINI_KEY = ""  # Gemini API ត្រូវបានបិទ និងមិនត្រូវបានប្រើ។
GROQ_KEY = collect_api_keys("GROQ_API_KEY")

render_header()
require_login()
# Mobile-first interface: landscape/fullscreen rotation control intentionally removed.
ls_sync()

if not GROQ_KEY and not oai_enabled() and not has_user_keys():
    # Keep the missing-key notice compact so it does not push the dashboard below the fold.
    st.caption("⚠️ មិនទាន់មាន API Key — បញ្ចូលនៅផ្ទាំង «🌐 បកប្រែ» ដើម្បីចាប់ផ្ដើមប្រើ AI។")

ENGINE_FREE = "⭐ Groq សម្គាល់សំឡេង + AI API បកប្រែ (Fallback ស្វ័យប្រវត្តិ)"

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
timbre = False
timbre_file = None
dub_offset = 0.0
tight_sync = False

# ប៊ូតុងចាប់ផ្តើម៖ បង្កើត placeholder ក្រោយផ្ទាំងមុខងារ ដើម្បីកុំឱ្យវាទុកចន្លោះទទេនៅលើ Dashboard។

tab_vid, tab_cut, tab_trans, tab_voice, tab_text, tab_fx, tab_out = st.tabs(
    ["🏠 វីដេអូ", "✂️ កាត់", "🌐 បកប្រែ", "🎙 សំឡេង", "🔤 អក្សរ", "🖼 Logo", "⬇️ ទាញយក"]
)

# ============================ ផ្ទាំង ១: វីដេអូ ============================
link_limit = MAX_VIDEOS
with tab_vid:
    col_upload, col_preview, col_controls = st.columns([1.02, 1.05, 1.02], gap="small")
    with col_upload:
        st.markdown('<div class="kvai-panel-title"><span class="kvai-step pink">1</span> បញ្ចូលវីដេអូ</div>', unsafe_allow_html=True)
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
                st.caption("ក្នុង TikTok ចុច Share → Copy link រួចបិទភ្ជាប់តំណក្នុងប្រអប់ខាងក្រោម។")
                link_text = st.text_area(
                    "តំណវីដេអូ TikTok (ដាក់បានច្រើនតំណ — មួយបន្ទាត់ ១ តំណ)",
                    key="link_text_area",
                    placeholder="បិទភ្ជាប់តំណវីដេអូនៅទីនេះ\nដាក់បានច្រើនតំណម្តងតែមួយ (មួយបន្ទាត់ ១ តំណ)",
                    height=68)
                _all_links = extract_links(link_text)
                _link_lines = _all_links[:link_limit]
                if _all_links:
                    st.caption(f"🔗 រកឃើញ {len(_all_links)} តំណ"
                               + (f" · ធ្វើបាន {link_limit} តំណដំបូង" if len(_all_links) > link_limit else ""))
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
                                _ssec = get_split_seconds()
                                if _ssec and _dur > _ssec + 20:
                                    _np = int(-(-_dur // _ssec))
                                    _info += f" · ✂️ នឹងបំបែកជា {_np} ផ្នែក (ក្នុងមួយផ្នែក {fmt_len(_ssec)})"
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
                st.caption(f"រហូតដល់ {MAX_VIDEOS} តំណ · ប្រវែង និងទំហំប៉ុន្មានក៏បាន · វីដេអូវែងអាចបំបែកជាផ្នែកខ្លីៗ (មើលការកំណត់ខាងក្រោម) ហើយធ្វើតាមលំដាប់")
            _ram_txt = server_ram_info()
            if _ram_txt:
                st.caption(_ram_txt)
        with st.expander("⚙️ ការកំណត់វីដេអូបន្ថែម", expanded=False):
            with st.container(border=True):
                quality_label = st.radio("📈 គុណភាពវីដេអូ", list(QUALITY.keys()), index=1,
                                         horizontal=True, key="quality_pick")
            with st.container(border=True):
                st.markdown("**✂️ កាត់វីដេអូវែងជាផ្នែកខ្លីៗ មុនបកប្រែ**")
                auto_split = st.toggle("បំបែកវីដេអូវែងជាផ្នែកខ្លីៗ ហើយបកប្រែម្តងមួយផ្នែក",
                                       value=False, key="auto_split_toggle")
                split_sec = 0
                split_exact = False
                if auto_split:
                    _split_labels = list(SPLIT_PRESETS.keys())
                    _split_lbl = st.selectbox("ប្រវែងមួយផ្នែក", _split_labels,
                                              index=_split_labels.index("៦ នាទី"), key="split_len_pick")
                    split_sec = SPLIT_PRESETS[_split_lbl]
                    split_exact = st.checkbox("🎯 កាត់ឱ្យចំពេលវេលា (យឺតជាង — encode ឡើងវិញ)", key="split_exact_pick")
                    st.caption(f"វីដេអូវែងជាង {fmt_len(split_sec + 20)} នឹងត្រូវបំបែក ហើយផ្នែកនីមួយៗបកប្រែតាមលំដាប់។ "
                               "ចង់កាត់ទាញយកទុកតែមួយៗ សូមប្រើផ្ទាំង «✂️ កាត់»។")

 
    with col_preview:
        st.markdown('<div class="kvai-panel-title"><span class="kvai-step blue">2</span> មើលជាមុន</div>', unsafe_allow_html=True)
        _dash_preview = uploaded_files[0] if uploaded_files else None
        if _dash_preview is None:
            _dash_cache = st.session_state.get("link_cache", {})
            for _u in st.session_state.get("link_searched", []):
                _ent = _dash_cache.get(_u, {})
                if _ent.get("ok") and _ent.get("path") and os.path.isfile(_ent["path"]):
                    _dash_preview = _ent["path"]
                    break
        if _dash_preview is not None:
            try:
                # Use stable bytes for UploadedFile previews so the player can load reliably.
                _preview_payload = (_dash_preview.getvalue()
                                    if hasattr(_dash_preview, "getvalue") else _dash_preview)
                st.video(_preview_payload)
                if uploaded_files:
                    st.caption(f"🎬 {uploaded_files[0].name}")
            except Exception:
                st.info("មិនអាចបង្ហាញ Preview បានទេ។")
        else:
            st.markdown('<div class="kvai-empty-preview"><div class="kvai-play">▶</div><b>វីដេអូរបស់អ្នកនឹងបង្ហាញនៅទីនេះ</b><small>Upload ឬដាក់ Link ដើម្បីមើលជាមុន</small></div>', unsafe_allow_html=True)
        st.markdown('<div class="kvai-filmstrip">🎞️　✨　🎬　✨　🎞️</div>', unsafe_allow_html=True)
        st.caption("គាំទ្រ MP4 · MOV · MKV · AVI · WEBM")
    with col_controls:
        st.markdown('<div class="kvai-panel-title"><span class="kvai-step pink">3</span> កំណត់ AI</div>', unsafe_allow_html=True)
        with st.container(border=True):
            voice_label = st.radio("🎙 សំឡេងនិយាយ", list(TTS_VOICES.keys()), horizontal=True, key="voice_pick")
            keep_bg = st.toggle("🎵 រក្សាសំឡេងដើម", value=False, key="keep_bg_toggle")
            bg_level = st.slider("កម្រិតសំឡេងដើម (%)", 2, 60, 8, key="bg_level_pick") if keep_bg else 8
            auto_gender = True
            st.caption("AI បង្កើតសំឡេងខ្មែរដោយស្វ័យប្រវត្តិ")
        with st.expander("🔤 កំណត់ Subtitle និងរូបរាងអក្សរ", expanded=False):
            review_on = st.toggle("✏️ ពិនិត្យអក្សរមុនបង្កើត", value=False, key="review_toggle")
            _f1, _f2 = st.columns(2)
            with _f1:
                font_name = st.selectbox("Font", [f[2] for f in FONT_SOURCES], index=0, key="font_pick")
                color_pick = st.selectbox("ពណ៌អក្សរ", list(COLOR_OPTIONS.keys()), index=0, key="color_pick")
            with _f2:
                box_pick = st.selectbox("ផ្ទៃក្រោយ", list(BOX_OPTIONS.keys()), index=0, key="box_pick")
                style_pick = st.selectbox("បែបអក្សរ", list(STYLE_OPTIONS.keys()), index=0, key="style_pick")
            font_size_on = st.toggle("កែទំហំអក្សរ", value=False, key="font_size_on")
            font_size = st.slider("ទំហំអក្សរ", 16, 36, 16, key="font_size_pick") if font_size_on else 16
            outline_size = st.slider("គែមអក្សរ", 1, 5, 2, key="outline_size_pick")
            pos_pick = st.radio("ទីតាំងអក្សរ", list(POS_MAP.keys()), index=7, horizontal=True, key="pos")
        bold_, italic_ = STYLE_OPTIONS[style_pick]
# ============================ ផ្ទាំង កាត់វីដេអូ ============================
with tab_cut:
    with st.container(border=True):
        st.markdown("**✂️ កាត់វីដេអូវែងជាវីដេអូខ្លីៗ**")
        st.caption("កាត់វីដេអូវែងជាផ្នែកខ្លីៗ រួចទាញយកទុក ឬផ្ញើទៅបកប្រែម្តងមួយផ្នែក។")
        _cache_c = st.session_state.get("link_cache", {})
        _link_src = [(u, _cache_c[u]["path"]) for u in st.session_state.get("link_searched", [])
                     if _cache_c.get(u, {}).get("ok") and _cache_c[u].get("path")
                     and os.path.isfile(_cache_c[u]["path"])]
        _src_opts = ["📁 Upload", "🔗 Link"] + (["🎬 ពីផ្ទាំងវីដេអូ"] if _link_src else [])
        cut_src_mode = st.radio("ប្រភព", _src_opts, horizontal=True,
                                key="cut_src_mode", label_visibility="collapsed")
        cut_path = None
        cut_name = "video"
        cut_up = None
        if cut_src_mode.startswith("📁"):
            cut_up = st.file_uploader("ជ្រើសវីដេអូវែង", type=["mp4", "mov", "mkv", "avi", "webm"],
                                      key="cut_upload")
            if cut_up is not None:
                cut_name = os.path.splitext(cut_up.name)[0]
        elif cut_src_mode.startswith("🔗"):
            st.caption("បិទភ្ជាប់តំណវីដេអូ (TikTok ឬតំណផ្សេង) ១ តំណ រួចចុច «ស្វែងរកវីដេអូ» — ទំហំនិងប្រវែងប៉ុន្មានក៏បាន។")
            _cut_url_text = st.text_area("តំណវីដេអូ", key="cut_link_text", height=90,
                                         placeholder="បិទភ្ជាប់តំណវីដេអូនៅទីនេះ")
            _cut_urls = extract_links(_cut_url_text)
            _cl = st.session_state.get("cut_link")
            if st.button("🔍 ស្វែងរកវីដេអូ", use_container_width=True, disabled=not _cut_urls,
                         key="cut_link_search"):
                if _cl and _cl.get("path"):
                    shutil.rmtree(os.path.dirname(_cl["path"]), ignore_errors=True)
                _ph_c = st.empty()

                def _cb_c(attempt):
                    _ph_c.info(f"⏳ កំពុងរកវីដេអូ · ព្យាយាមលើកទី {attempt}/{LINK_RETRIES}")

                _ent_c = _fetch_one(_cut_urls[0], _cb_c)
                _ph_c.empty()
                st.session_state["cut_link"] = dict(_ent_c, url=_cut_urls[0])
                _cl = st.session_state["cut_link"]
            if _cl and _cl.get("url") in _cut_urls:
                if _cl.get("ok") and _cl.get("path") and os.path.isfile(_cl["path"]):
                    cut_path = _cl["path"]
                    cut_name = "video_link"
                    _info_c = f"📦 {os.path.getsize(cut_path) / (1024 * 1024):.0f}MB"
                    try:
                        _info_c += f" · ⏱ {fmt_clock(probe_media(cut_path)[0])}"
                    except Exception:
                        pass
                    st.success("✅ រកឃើញវីដេអូហើយ · " + _info_c)
                else:
                    st.error("រកតំណមិនឃើញទេ។ សូមសាកម្តងទៀត។")
                    if _cl.get("err"):
                        st.code(_cl["err"])
            elif _cut_urls:
                st.caption("ចុច «ស្វែងរកវីដេអូ» ជាមុនសិន។")
        else:
            _pick = st.selectbox("ជ្រើសវីដេអូ", list(range(len(_link_src))),
                                 format_func=lambda i: f"វីដេអូទី {i + 1}", key="cut_link_pick")
            cut_path = _link_src[_pick][1]
            cut_name = f"video_{_pick + 1}"
            try:
                _cd, _cw, _ch = probe_media(cut_path)
                st.caption(f"⏱ {fmt_clock(_cd)}")
            except Exception:
                pass
        _cut_opts = list(SPLIT_PRESETS.keys()) + ["✏️ កំណត់ខ្លួនឯង"]
        _cut_default = next((i for i, v in enumerate(_cut_opts) if "១ នាទី" in v or "1 នាទី" in v or "60" in v), 0)
        _cut_lbl = st.selectbox("ប្រវែងមួយផ្នែក", _cut_opts, index=_cut_default, key="cut_len_pick")
        if _cut_lbl.startswith("✏️"):
            cut_sec = int(st.number_input("ប្រវែងមួយផ្នែក (វិនាទី)", min_value=5, max_value=3600,
                                          value=90, step=5, key="cut_len_custom"))
        else:
            cut_sec = SPLIT_PRESETS[_cut_lbl]
        cut_exact = st.checkbox("🎯 កាត់ឱ្យចំពេលវេលា (យឺតជាង — encode ឡើងវិញ)", key="cut_exact_pick")
        st.caption("លំនាំដើមកាត់ដោយមិន encode ដូច្នេះលឿនណាស់ តែចុងផ្នែកអាចខុសពីប្រវែងដែលជ្រើសបន្តិច (កាត់តាម keyframe)។")
        _can_cut = (cut_up is not None) or bool(cut_path)
        _gc1, _gc2 = st.columns(2)
        with _gc1:
            _go_cut = st.button("✂️ កាត់ទុក", type="primary", use_container_width=True,
                                disabled=not _can_cut, key="cut_go_btn")
        with _gc2:
            _go_cut_tr = st.button("✂️✨ កាត់ ហើយបកប្រែតែម្តង", type="primary", use_container_width=True,
                                   disabled=(not _can_cut) or busy, key="cut_go_tr_btn")
        if _go_cut or _go_cut_tr:
            _old = st.session_state.pop("cut_result", None)
            if _old:
                shutil.rmtree(_old["folder"], ignore_errors=True)
            st.session_state.pop("_cut_sent", None)
            st.session_state.pop("_split_queue", None)
            _fold = tempfile.mkdtemp(prefix="kcut_")
            try:
                with st.spinner("កំពុងកាត់វីដេអូ..."):
                    _own = False
                    if cut_up is not None and cut_src_mode.startswith("📁"):
                        _csrc = os.path.join(_fold, "src.bin")
                        with open(_csrc, "wb") as _fh:
                            _fh.write(cut_up.getbuffer())
                        _own = True
                    else:
                        _csrc = cut_path
                    _cdur = probe_media(_csrc)[0]
                    if _cdur <= cut_sec + 1:
                        raise UserError("វីដេអូខ្លីជាងប្រវែងដែលបានជ្រើស។ សូមជ្រើសប្រវែងខ្លីជាងនេះ។")
                    _files = cut_clips(_csrc, _fold, "clip_", cut_sec, cut_exact)
                    if _own:
                        try:
                            os.remove(_csrc)
                        except OSError:
                            pass
                    if not _files:
                        raise UserError("កាត់វីដេអូមិនបានទេ។ សូមសាកម្តងទៀត ឬបើក «កាត់ឱ្យចំពេលវេលា»។")
                    _parts, _t = [], 0.0
                    for _k, _pp in enumerate(_files, start=1):
                        try:
                            _d = probe_media(_pp)[0]
                        except Exception:
                            _d = float(cut_sec)
                        _parts.append({"name": f"{safe_filename(cut_name)}_part{_k:02d}.mp4",
                                       "label": f"ផ្នែក {_k}", "path": _pp, "start": _t, "dur": _d,
                                       "mb": os.path.getsize(_pp) / (1024 * 1024)})
                        _t += _d
                    _zip = None
                    if sum(x["mb"] for x in _parts) <= MAX_ZIP_MB:
                        _zip = os.path.join(_fold, "clips.zip")
                        with zipfile.ZipFile(_zip, "w", zipfile.ZIP_STORED) as _z:
                            for x in _parts:
                                _z.write(x["path"], x["name"])
                    st.session_state["cut_result"] = {"folder": _fold, "parts": _parts,
                                                      "zip": _zip, "base": cut_name}
            except Exception as _e:
                shutil.rmtree(_fold, ignore_errors=True)
                st.error(str(_e) if isinstance(_e, UserError) else friendly_message(_e))
            _cr = st.session_state.get("cut_result")
            if _go_cut_tr and _cr:
                _nn = len(_cr["parts"])
                st.session_state["_split_queue"] = [
                    {"name": f"{_cr['base']} · ផ្នែក {k}/{_nn}", "path": x["path"]}
                    for k, x in enumerate(_cr["parts"], start=1)]
                st.session_state["_run_split"] = True
                st.session_state["_cut_sent"] = min(_nn, SPLIT_QUEUE_MAX)
                st.rerun()

    if st.session_state.get("_cut_sent") and st.session_state.get("job"):
        st.info(f"✅ បានផ្ញើ {st.session_state['_cut_sent']} ផ្នែកទៅបកប្រែហើយ — មើលនៅផ្ទាំង ⬇️ ទាញយក។")

    _res = st.session_state.get("cut_result")
    if _res and all(os.path.isfile(x["path"]) for x in _res["parts"]):
        _n = len(_res["parts"])
        with st.container(border=True):
            st.markdown(f"**✅ កាត់បាន {_n} ផ្នែក**")
            for _i, x in enumerate(_res["parts"], start=1):
                with st.container(border=True):
                    st.markdown(f"**{x['label']}** · {fmt_clock(x['start'])} → "
                                f"{fmt_clock(x['start'] + x['dur'])} · {x['mb']:.0f}MB")
                    _bc1, _bc2 = st.columns(2)
                    with _bc1:
                        with open(x["path"], "rb") as _fh:
                            dl_button("⬇️ ទាញយក", _fh, x["name"], "video/mp4",
                                      key=f"cutdl_{_i}", use_container_width=True)
                    with _bc2:
                        if st.button("✨ បកប្រែ", type="primary", use_container_width=True,
                                     disabled=busy, key=f"cut_tr_{_i}"):
                            st.session_state["_split_queue"] = [
                                {"name": f"{_res['base']} · {x['label']}/{_n}", "path": x["path"]}]
                            st.session_state["_run_split"] = True
                            st.session_state["_cut_sent"] = 1
                            st.rerun()
                    if x["mb"] <= PREVIEW_MAX_MB:
                        with st.expander("▶️ មើលវីដេអូ"):
                            st.video(x["path"])
            if _res.get("zip") and os.path.isfile(_res["zip"]):
                with open(_res["zip"], "rb") as _zf:
                    dl_button("📦 ទាញយកទាំងអស់ (ZIP)", _zf, f"{safe_filename(_res['base'])}_parts.zip",
                              "application/zip", key="cut_zip_dl", use_container_width=True)
            _c1, _c2 = st.columns(2)
            with _c1:
                _lbl_tr = f"✨ បកប្រែ {_n} ផ្នែកនេះ"
                if _n > SPLIT_QUEUE_MAX:
                    _lbl_tr = f"✨ បកប្រែ {SPLIT_QUEUE_MAX} ផ្នែកដំបូង"
                if st.button(_lbl_tr, type="primary", use_container_width=True, disabled=busy,
                             key="cut_translate_btn"):
                    st.session_state["_split_queue"] = [
                        {"name": f"{_res['base']} · ផ្នែក {k}/{_n}", "path": x["path"]}
                        for k, x in enumerate(_res["parts"], start=1)]
                    st.session_state["_run_split"] = True
                    st.session_state["_cut_sent"] = min(_n, SPLIT_QUEUE_MAX)
                    st.rerun()
            with _c2:
                if st.button("🗑 លុបលទ្ធផលកាត់", use_container_width=True, key="cut_clear_btn"):
                    shutil.rmtree(_res["folder"], ignore_errors=True)
                    st.session_state.pop("cut_result", None)
                    st.session_state.pop("_split_queue", None)
                    st.session_state.pop("_cut_sent", None)
                    st.rerun()
    elif _res:
        st.session_state.pop("cut_result", None)

# ============================ ផ្ទាំង ២: បកប្រែ ============================
with tab_trans:
    with st.container(border=True):
        engine_options = [ENGINE_FREE]
        if not effective_groq_key():
            st.warning("សូមដាក់ Groq API Key សម្រាប់សម្គាល់សំឡេង និងកំណត់ API បកប្រែយ៉ាងហោចណាស់មួយក្នុង Secrets ឬបញ្ចូល xKiro Key ផ្ទាល់ខ្លួន។")
        engine_label = st.selectbox("ម៉ាស៊ីនដំណើរការ", engine_options, index=0, disabled=True)
        st.caption("Groq ប្រើសម្រាប់សម្គាល់សំឡេង។ ការបកប្រែសាកល្បង Claude (បើមាន Key) មុនគេ រួច xKiro និង CodeCraft រួចបន្តទៅ Provider ផ្សេងៗដែលម្ចាស់កម្មវិធីបានកំណត់ក្នុង Secrets។")
        with st.expander("🌐 API ដែលអាចភ្ជាប់តាម Secrets"):
            st.markdown("""
            - `ANTHROPIC_API_KEY` (ឬ `ANTHROPIC_API_KEYS = ["key1", "key2"]` / `ANTHROPIC_API_KEY_1`, `_2`), `ANTHROPIC_BASE_URL` (មិនចាំបាច់), `ANTHROPIC_MODEL` (មិនចាំបាច់)
            - `XKIRO_API_KEY`, `XKIRO_BASE_URL`, `XKIRO_MODEL`
            - `CODECRAFT_API_KEY`, `CODECRAFT_BASE_URL`, `CODECRAFT_MODEL`
            - `OPENROUTER_API_KEYS = ["key1", "key2", ...]` ឬ `OPENROUTER_API_KEY_1`, `OPENROUTER_API_KEY_2` និង `OPENROUTER_MODEL` (Base URL លំនាំដើម `https://openrouter.ai/api/v1`)
            - `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_BASE_URL`, `CLOUDFLARE_MODEL` (Base URL ត្រូវមាន Account ID)
            - `MISTRAL_API_KEY`, `MISTRAL_MODEL`
            - `NVIDIA_API_KEY`, `NVIDIA_MODEL`
            - `COHERE_API_KEY`, `COHERE_MODEL`
            - `SAMBANOVA_API_KEY`, `SAMBANOVA_MODEL`

            Provider នឹងត្រូវបានរំលងដោយស្វ័យប្រវត្តិ ប្រសិនបើគ្មាន Key។ សូមកំណត់ឈ្មោះម៉ូដែលដែលមានសិទ្ធិប្រើក្នុងគណនីរបស់អ្នក។ កូតា Free អាចប្រែប្រួល ហើយមិនមែនគ្រប់ API ខាងលើសុទ្ធតែឥតគិតថ្លៃគ្រប់ពេលទេ។ API Key មិនត្រូវបង្ហាញដល់អ្នកប្រើធម្មតាទេ។
            """)
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
    st.markdown("### 🎭 សំឡេងគំរូច្រើនតួអង្គ")
    st.caption("ជម្រើសសំឡេងប្រុស/ស្រី និងសំឡេងដើមស្ថិតនៅលើ Dashboard ខាងមុខ។")
    with st.container(border=True):
        st.markdown("**🎤 សំឡេងគំរូច្រើនតួអង្គ (ឥតគិតថ្លៃ)**")
        clone_on = st.toggle("ប្រើសំឡេងគំរូ ឱ្យសំឡេងអានស្រដៀងសំឡេងគំរូ", value=False, key="clone_toggle")
        clone_files = []
        if clone_on:
            _n_chars = st.slider("ចំនួនតួអង្គ (សំឡេងគំរូ)", 1, 6, 2, key="clone_n")
            for _ci in range(_n_chars):
                _cf = st.file_uploader(
                    f"🎭 សំឡេងគំរូតួអង្គទី {_ci + 1} (mp3 / wav / m4a / mp4)",
                    type=["mp3", "wav", "m4a", "mp4", "ogg", "flac"], key=f"clone_upl_{_ci}")
                if _cf is not None:
                    clone_files.append(_cf)
            st.caption("សំឡេងគំរូនីមួយៗគួរជាអ្នកនិយាយតែម្នាក់ ច្បាស់ ១០ វិនាទីឡើង គ្មានភ្លេង។ "
                       "កម្មវិធីផ្គូផ្គងសំឡេងគំរូទៅតាមអ្នកនិយាយក្នុងវីដេអូ។")
        else:
            clone_files = []


def clone_sample_bytes(upload):
    """បម្លែងសំឡេងគំរូជា wav 16kHz mono (ត្រឹម ៩០ វិនាទី)។ ត្រឡប់ None បើមិនបាន។"""
    if upload is None:
        return None
    raw = upload.getvalue()
    tmp = tempfile.mkdtemp(prefix="kclone_")
    try:
        src = os.path.join(tmp, "in.bin")
        dst = os.path.join(tmp, "out.wav")
        with open(src, "wb") as fh:
            fh.write(raw)
        run_ffmpeg(["-i", src, "-vn", "-ac", "1", "-ar", "16000", "-t", "90", dst])
        with open(dst, "rb") as fh:
            return fh.read()
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================ ផ្ទាំង ៤: អក្សរ ============================
with tab_text:
    st.markdown("### 🔤 ការកំណត់ Subtitle")
    st.caption("ការកំណត់ Font, ពណ៌, ទំហំ, គែមអក្សរ និងទីតាំង ត្រូវបានដាក់នៅជួរទី ៣ លើ Dashboard ដើម្បីមើលឃើញភ្លាមៗពេលបើកកម្មវិធី។")
    bold_, italic_ = STYLE_OPTIONS[style_pick]
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


def render_fx_preview(aspect, logo, lx, ly, lsize, lop, tint, blurs, frame=None):
    """frame = (data_uri, ទទឹង, កម្ពស់) ស៊ុមពិតពីវីដេអូ។ បើមាន ប្រើទំហំពិតរបស់វីដេអូ (អូតូ)។"""
    bg = "linear-gradient(160deg,#3A2C6E 0%,#1B2A5E 60%,#0E1636 100%)"
    if frame and frame[0]:
        fw, fh = max(1, frame[1]), max(1, frame[2])
        ratio = fw / float(fh)
        bg = f"#000 url({frame[0]}) center/cover no-repeat"
        if aspect == "auto":
            if ratio >= 1.0:
                box = f"width:100%;aspect-ratio:{fw}/{fh};margin:6px 0;"
            else:
                box = f"height:460px;max-width:100%;aspect-ratio:{fw}/{fh};margin:6px auto;"
    if not (frame and frame[0] and aspect == "auto"):
        if aspect == "9:16":
            box = "height:260px;aspect-ratio:9/16;margin:6px auto;"
        elif aspect == "1:1":
            box = "height:240px;aspect-ratio:1/1;margin:6px auto;"
        else:
            box = "width:100%;aspect-ratio:16/9;margin:6px 0;"
    html = [f'<div style="position:relative;overflow:hidden;border-radius:14px;border:1px solid rgba(125,145,255,.22);'
            f'background:{bg};{box}">']
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


def fx_frame_for(path, key):
    """ដកស៊ុមមួយពីវីដេអូ (cache តាម key) → (data_uri, w, h) ឬ None។"""
    c = st.session_state.get("_fx_frame")
    if c and c.get("key") == key:
        return c.get("val")
    val = None
    tmp = tempfile.mkdtemp(prefix="kfx_")
    try:
        out = os.path.join(tmp, "f.jpg")
        for ss in ("1", "0"):
            try:
                run_ffmpeg(["-ss", ss, "-i", path, "-frames:v", "1", "-vf", "scale='min(640,iw)':-2", "-q:v", "4", out])
                if os.path.isfile(out) and os.path.getsize(out) > 0:
                    break
            except Exception:
                continue
        if os.path.isfile(out):
            from PIL import Image
            with open(out, "rb") as fh:
                raw = fh.read()
            w_, h_ = Image.open(io.BytesIO(raw)).size
            val = ("data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii"), w_, h_)
    except Exception:
        val = None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    st.session_state["_fx_frame"] = {"key": key, "val": val}
    return val


def fx_current_frame():
    """រកវីដេអូដំបូងដែលបានជ្រើស/រកឃើញ (Upload, Link, ឬផ្នែកដែលកាត់) ហើយត្រឡប់ស៊ុមរបស់វា។"""
    try:
        if uploaded_files:
            f0 = uploaded_files[0]
            if f0.size > MAX_UPLOAD_MB * 1024 * 1024:
                return None
            key = f"up:{f0.name}:{f0.size}"
            c = st.session_state.get("_fx_frame")
            if c and c.get("key") == key:
                return c.get("val")
            tmpd = tempfile.mkdtemp(prefix="kfxu_")
            try:
                pth = os.path.join(tmpd, "v.bin")
                with open(pth, "wb") as fh:
                    fh.write(f0.getbuffer())
                return fx_frame_for(pth, key)
            finally:
                shutil.rmtree(tmpd, ignore_errors=True)
        _cache = st.session_state.get("link_cache", {})
        for u in extract_links(link_text):
            ent = _cache.get(u, {})
            if ent.get("ok") and ent.get("path") and os.path.isfile(ent["path"]):
                return fx_frame_for(ent["path"], f"ln:{ent['path']}")
        _sq0 = st.session_state.get("_split_queue") or []
        for q in _sq0:
            if os.path.isfile(q["path"]):
                return fx_frame_for(q["path"], f"sq:{q['path']}")
    except Exception:
        return None
    return None


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
        _frame = fx_current_frame()
        _asp_opts = ["🔄 អូតូ (តាមវីដេអូ)", "16:9", "9:16", "1:1"]
        _asp = st.radio("ទម្រង់មើលជាមុន", _asp_opts, horizontal=True, key="fx_aspect_v2")
        aspect = "auto" if _asp.startswith("🔄") else _asp
        render_fx_preview(aspect, logo_preview_data(logo_file.getvalue()) if logo_file is not None else None,
                          logo_x, logo_y, logo_size, logo_op / 100.0, logo_tint, blur_list, frame=_frame)
        if _frame is None:
            st.caption("🎞 ជ្រើសវីដេអូ ឬរកតំណឃើញជាមុន នោះនឹងបង្ហាញរូបពិតពីវីដេអូនៅទីនេះ ដើម្បីដាក់ Logo/Blur ឱ្យចំកន្លែង។")
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

# ផ្នែកដែលបានកាត់ពីផ្ទាំង «✂️ កាត់» ហើយបានចុច «បកប្រែ» → ជំនួសបញ្ជីវីដេអូ
_sq = st.session_state.get("_split_queue")
if _sq and st.session_state.get("_run_split"):
    _sq = [q for q in _sq if os.path.isfile(q["path"])]
    items = [{"name": q["name"], "file": None, "url": None, "cached": q["path"], "presplit": True}
             for q in _sq[:SPLIT_QUEUE_MAX]]
    too_many = len(_sq) > SPLIT_QUEUE_MAX

# ============================ ប៊ូតុងចាប់ផ្តើម (ជាប់ខាងក្រោម) ============================
# Place the action slot AFTER all tabs so Streamlit does not reserve a tall empty block above the dashboard.
start_slot = st.container(key="startbar")
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
        st.caption(f"⚠️ ធ្វើបានត្រឹម {link_limit} វីដេអូដំបូង។")

if link_translate and items and not busy:
    run = True
if st.session_state.get("_run_split") and not busy:
    if items:
        run = True
    else:
        st.session_state["_run_split"] = False

if run:
    try:
        fonts_data = load_font_bytes()
    except Exception:
        st.error("ទាញយក Font ខ្មែរមិនបាន។ សូមសាកម្តងទៀត។")
        st.stop()
    prepare_home_font(fonts_data)
    fonts_data = sorted(fonts_data, key=lambda f: 0 if f[2] == font_name else 1)
    clone_samples = [b_ for b_ in (clone_sample_bytes(f_) for f_ in clone_files) if b_] if clone_on else []
    settings = {
        "engine": "free",
        "gemini_key": "", "groq_key": effective_groq_key(), "fx": fx_settings,
        "user_xk_cfg": (
            st.session_state.get("user_oai_key", ""),
            st.session_state.get("user_oai_base", "https://api.xkiro.com/v1"),
            st.session_state.get("user_oai_model", "qwen/qwen3.5-flash"),
        ),
        "language": LANGUAGES[language_label], "quality": QUALITY[quality_label],
        "dub_on": dub_on, "voice": TTS_VOICES[voice_label],
        # Fixed internal defaults; no extra voice-tuning controls in the UI.
        "keep_bg": keep_bg, "bg_vol": (bg_level / 100.0 if keep_bg else 0.0), "dub_offset": 0.0, "tight_sync": False, "auto_gender": auto_gender,
        "voice_match": False, "emotion": emotion_on,
        "timbre": bool(clone_samples), "timbre_samples": clone_samples,
        "font_size": font_size, "outline_size": outline_size,
        "color": COLOR_OPTIONS[color_pick][0],
        "sub_on": sub_on, "srt_on": srt_on,
        "narrate_on": False, "review_on": review_on,
        "style": {"align": POS_MAP[pos_pick], "bold": bold_, "italic": italic_, "box": BOX_OPTIONS[box_pick]},
    }
    st.session_state["_run_split"] = False
    old = st.session_state.get("job")
    if old:
        shutil.rmtree(old.folder, ignore_errors=True)
        st.session_state.pop("job", None)
        old = None
        gc.collect()
    _CLAUDE_PROVIDERS[:] = []
    for _i, _k in enumerate(st.session_state.get("user_claude_keys", []), start=1):
        _CLAUDE_PROVIDERS.append((f"Claude ផ្ទាល់ខ្លួន #{_i}", (
            _k, st.session_state.get("user_claude_base", "https://api.laalaa.me"),
            st.session_state.get("user_claude_model", "claude-sonnet-5-5"))))
    _CLAUDE_PROVIDERS.extend(_CLAUDE_SECRET_PROVIDERS)
    _CLAUDE_COOL.clear()
    job_folder = tempfile.mkdtemp(prefix="kac_")
    job_items = []
    for idx, it in enumerate(items, start=1):
        if it["file"] is not None:
            p = os.path.join(job_folder, f"upload_{idx}.bin")
            with open(p, "wb") as f:
                f.write(it["file"].getbuffer())
            parts = None
            if split_sec:
                with st.spinner(f"កំពុងកាត់វីដេអូទី {idx} ជាផ្នែកខ្លីៗ..."):
                    parts = split_video_parts(p, job_folder, idx, split_sec, split_exact)
            if parts:
                try:
                    os.remove(p)
                except OSError:
                    pass
                for k, pp in enumerate(parts, start=1):
                    item = new_item(f"{it['name']} · ផ្នែក {k}/{len(parts)}")
                    item["path"] = pp
                    job_items.append(item)
            else:
                item = new_item(it["name"], url=it["url"])
                item["path"] = p
                job_items.append(item)
        elif it.get("presplit"):
            item = new_item(it["name"])
            p = os.path.join(job_folder, f"upload_{idx}.bin")
            link_or_copy(it["cached"], p)
            item["path"] = p
            job_items.append(item)
        elif it.get("cached") and os.path.isfile(it["cached"]):
            parts = None
            if split_sec:
                with st.spinner(f"កំពុងរៀបចំវីដេអូទី {idx}..."):
                    parts = split_video_parts(it["cached"], job_folder, idx, split_sec, split_exact)
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


# ---------- Screenshot-specific correction: remove clipping and footer overlay ----------
# The previous final CSS accidentally re-enabled overflow:hidden and a fixed footer.
# Keep every Streamlit widget reachable; the action button is placed in normal flow.
SCREENSHOT_LAYOUT_CORRECTION_CSS = """
<style>
/* Restore the Angkor background and animated neon light beams. */
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMainBlockContainer"] {
  background-color:#05091d !important;
  color:#f7f8ff !important;
}
.stApp::before {
  content:""; position:fixed; inset:0; z-index:0; pointer-events:none;
  background:
    repeating-linear-gradient(112deg,transparent 0 13%,rgba(0,220,255,.10) 13.15%,transparent 13.5% 28%),
    linear-gradient(105deg,transparent 35%,rgba(255,25,170,.16) 48%,transparent 62%);
  background-size:190% 100%,230% 100%;
  animation:kvai-screenshot-lights 7s linear infinite;
}
@keyframes kvai-screenshot-lights {
  from {background-position:190% 0,210% 0}
  to {background-position:-20% 0,-30% 0}
}
[data-testid="stMain"] > div, .block-container {position:relative;z-index:1}

/* Do not lock the document to a short viewport or clip widgets. */
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMainBlockContainer"] {
  height:auto !important; min-height:100% !important;
  max-height:none !important; overflow-x:hidden !important; overflow-y:auto !important;
}
[data-testid="stMain"] {overflow:visible !important}
.block-container {
  height:auto !important; min-height:100dvh !important; max-height:none !important;
  overflow:visible !important; max-width:1800px !important;
  padding:4px 10px 12px !important;
}

/* Remove the large blank band after the header and compact orientation control. */
.kvai-head {height:76px !important;min-height:76px !important;max-height:76px !important;
  margin:0 0 3px !important;padding:5px 12px !important}
.kvai-logo {width:44px !important;height:44px !important;flex-basis:44px !important}
.kvai-title h1 {font-size:clamp(1.05rem,2vw,1.5rem) !important}
.kvai-title p {font-size:.72rem !important;margin:0 !important}
.kvai-badge {font-size:.72rem !important;padding:4px 9px !important}
iframe[title="streamlit.components.v1.html"] {
  display:block !important;height:32px !important;max-height:32px !important;
  margin:0 !important;padding:0 !important;
}
[data-testid="stElementContainer"]:has(iframe[title="streamlit.components.v1.html"]) {
  height:32px !important;min-height:32px !important;margin:0 !important;padding:0 !important;
}
[data-testid="stVerticalBlock"] {gap:.25rem !important}
[data-testid="stElementContainer"] {margin-bottom:0 !important}

/* Tabs and dashboard columns: compact desktop proportions, preserve clickability. */
[data-baseweb="tab-list"] {display:flex !important;gap:4px !important;
  margin:2px 0 4px !important;padding:3px !important}
button[data-baseweb="tab"] {height:36px !important;min-width:0 !important;padding:0 8px !important}
button[data-baseweb="tab"] p {font-size:.78rem !important;white-space:nowrap !important}
[data-baseweb="tab-panel"] {height:auto !important;max-height:none !important;
  overflow:visible !important;padding:2px 0 8px !important}
[data-testid="stHorizontalBlock"] {gap:.4rem !important;flex-wrap:nowrap !important}
[data-testid="stColumn"] {min-width:0 !important}
[data-testid="stWidgetLabel"] p {font-size:.75rem !important;margin-bottom:1px !important}
[data-testid="stFileUploaderDropzone"] {min-height:46px !important;padding:3px 6px !important}
[data-testid="stVideo"] video {max-height:130px !important;object-fit:contain !important}
.kvai-empty-preview {height:130px !important}
.stButton>button,.stDownloadButton>button {min-height:34px !important;font-size:.76rem !important}

/* Critical: never pin the start button over the dashboard. Its container is before tabs,
   so it becomes a compact action strip directly above the tab row. */
.st-key-startbar {
  position:relative !important;inset:auto !important;left:auto !important;bottom:auto !important;
  transform:none !important;width:100% !important;z-index:4 !important;
  margin:2px 0 4px !important;padding:3px 8px !important;
  background:linear-gradient(90deg,rgba(255,20,147,.18),rgba(6,15,48,.94),rgba(0,210,255,.18)) !important;
  border:1px solid rgba(0,220,255,.55) !important;border-radius:12px !important;
  box-shadow:0 0 13px rgba(0,190,255,.15) !important;
}
.st-key-startbar [data-testid="stVerticalBlockBorderWrapper"],
.st-key-startbar [data-testid="stVerticalBlock"] {
  background:transparent !important;border:0 !important;box-shadow:none !important;
}
.st-key-startbar .stButton>button,.st-key-startbar .stButton>button:disabled {
  min-height:38px !important;opacity:1 !important;color:#fff !important;
  border:1px solid #19ddff !important;border-radius:11px !important;
  background:linear-gradient(100deg,#ff1493,#843bff,#00cfff) !important;
  box-shadow:0 0 14px rgba(0,207,255,.25) !important;
}

/* Keep warning compact so it does not push the workspace down. */
[data-testid="stAlert"] {padding:6px 10px !important;margin:3px 0 5px !important}
[data-testid="stAlert"] p {font-size:.78rem !important;line-height:1.25 !important;margin:0 !important}

/* Landscape: fit the desktop-like layout more tightly without clipping the controls.
   If a device has an unusually short viewport, natural scrolling remains available
   rather than making buttons unreachable. */
@media (orientation:landscape) and (min-width:700px) {
  .block-container {padding:3px 8px 8px !important}
  .kvai-head {height:68px !important;min-height:68px !important;max-height:68px !important}
  .kvai-logo {width:39px !important;height:39px !important;flex-basis:39px !important}
  .kvai-title p {font-size:.66rem !important}
  button[data-baseweb="tab"] {height:33px !important}
  [data-testid="stVideo"] video,.kvai-empty-preview {max-height:112px !important;height:112px !important}
  [data-testid="stFileUploaderDropzone"] {min-height:38px !important}
  [data-testid="stWidgetLabel"] p {font-size:.69rem !important}
  .stButton>button,.stDownloadButton>button {min-height:30px !important;font-size:.69rem !important}
  .st-key-startbar .stButton>button {min-height:34px !important}
}
@media (orientation:portrait) {
  .kvai-head {height:auto !important;min-height:68px !important;max-height:none !important}
}
</style>
"""
st.markdown(SCREENSHOT_LAYOUT_CORRECTION_CSS, unsafe_allow_html=True)

# =====================================================================
# FINAL DESKTOP MODE — landscape phone behaves like a compact desktop UI
# Keep the three-column workspace, shrink the whole interface to the viewport,
# collapse optional settings, and reserve a small non-overlapping action bar.
# =====================================================================
DESKTOP_MODE_VIEWPORT_CSS = r"""
<style>
@media screen and (orientation:landscape) and (max-height:700px) and (min-width:600px) {
  html { zoom:.80 !important; }
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    width:100% !important; height:100dvh !important; min-height:100dvh !important;
    max-height:100dvh !important; overflow:hidden !important;
  }
  .block-container {
    width:125vw !important; max-width:none !important; height:125dvh !important;
    min-height:0 !important; max-height:125dvh !important; overflow:hidden !important;
    padding:3px 8px 42px !important; margin:0 !important;
  }
  [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
  [data-testid="stStatusWidget"] {display:none !important;height:0 !important}
  [data-testid="stVerticalBlock"] {gap:.16rem !important}
  [data-testid="stElementContainer"] {margin:0 !important;padding:0 !important}
  .kvai-head {height:52px !important;min-height:52px !important;max-height:52px !important;
    margin:0 0 2px !important;padding:3px 8px !important;gap:6px !important}
  .kvai-logo {width:34px !important;height:34px !important;flex:0 0 34px !important;font-size:18px !important}
  .kvai-title h1 {font-size:1.08rem !important;line-height:1 !important}
  .kvai-title p {display:none !important}
  .kvai-badge {font-size:.62rem !important;padding:3px 7px !important}
  iframe[title="streamlit.components.v1.html"] {height:20px !important;max-height:20px !important}
  [data-testid="stElementContainer"]:has(iframe[title="streamlit.components.v1.html"]) {
    height:20px !important;min-height:20px !important;margin:0 !important;padding:0 !important}
  /* Desktop-style tabs: all seven stay in one row. */
  [data-baseweb="tab-list"] {display:flex !important;flex-wrap:nowrap !important;gap:3px !important;
    padding:2px !important;margin:1px 0 3px !important;overflow:hidden !important}
  button[data-baseweb="tab"] {flex:1 1 0 !important;min-width:0 !important;height:29px !important;
    padding:0 2px !important;border-radius:7px !important}
  button[data-baseweb="tab"] p {font-size:.66rem !important;white-space:nowrap !important;
    overflow:hidden !important;text-overflow:ellipsis !important}
  [data-baseweb="tab-panel"] {height:calc(100dvh - 112px) !important;max-height:calc(100dvh - 112px) !important;
    overflow:hidden !important;padding:0 !important}
  /* Keep the real 3-column desktop dashboard; never stack the columns. */
  [data-testid="stHorizontalBlock"] {display:flex !important;flex-wrap:nowrap !important;gap:.25rem !important}
  [data-testid="stColumn"] {min-width:0 !important;flex:1 1 0 !important}
  .kvai-panel-title {font-size:.70rem !important;padding:2px 5px !important;margin:0 0 1px !important}
  .kvai-step {width:19px !important;height:19px !important;font-size:.64rem !important}
  div[data-testid="stVerticalBlockBorderWrapper"] {padding:2px !important;border-radius:8px !important}
  [data-testid="stWidgetLabel"] p, .stApp label {font-size:.62rem !important;margin:0 !important;line-height:1.02 !important}
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
    font-size:.53rem !important;line-height:1.02 !important;margin:0 !important}
  [data-testid="stFileUploaderDropzone"] {min-height:31px !important;padding:1px 3px !important}
  [data-testid="stFileUploaderDropzoneInstructions"] {padding:0 !important}
  [data-testid="stFileUploaderDropzoneInstructions"] span,
  [data-testid="stFileUploaderDropzoneInstructions"] small {font-size:.53rem !important}
  [data-testid="stVideo"] video, .kvai-empty-preview {height:72px !important;max-height:72px !important}
  .kvai-play {width:29px !important;height:29px !important;font-size:14px !important}
  .kvai-filmstrip {display:none !important}
  [data-baseweb="select"]>div {min-height:25px !important}
  .stTextInput input, .stNumberInput input {min-height:24px !important}
  .stTextArea textarea {height:34px !important;min-height:34px !important}
  .stButton>button, .stDownloadButton>button {min-height:25px !important;padding:1px 4px !important;
    font-size:.60rem !important;border-radius:6px !important}
  [data-testid="stRadio"] [role="radiogroup"] {gap:2px !important;flex-wrap:nowrap !important}
  [data-testid="stRadio"] label {padding:2px 3px !important;font-size:.56rem !important}
  [data-testid="stToggle"], [data-testid="stCheckbox"], [data-testid="stSlider"] {padding:0 !important}
  [data-testid="stExpander"] summary {min-height:22px !important;padding:1px 5px !important}
  [data-testid="stExpander"] summary p {font-size:.60rem !important}
  [data-testid="stAlert"] {padding:2px 5px !important;margin:1px 0 !important}
  [data-testid="stAlert"] p {font-size:.57rem !important;line-height:1.02 !important}
  /* Start button fixed to the screen edge; slot is now at document end, not above the tabs. */
  .st-key-startbar {position:fixed !important;left:0 !important;right:0 !important;bottom:0 !important;
    transform:none !important;width:100% !important;z-index:1000 !important;margin:0 !important;
    padding:2px 6px !important;border-radius:0 !important;
    background:linear-gradient(90deg,rgba(255,20,147,.2),rgba(4,9,30,.97),rgba(0,210,255,.2)) !important;
    border-top:1px solid rgba(0,220,255,.5) !important;backdrop-filter:blur(7px) !important}
  .st-key-startbar [data-testid="stVerticalBlockBorderWrapper"],
  .st-key-startbar [data-testid="stVerticalBlock"] {background:transparent !important;border:0 !important;box-shadow:none !important}
  .st-key-startbar .stButton>button {min-height:28px !important;font-size:.68rem !important;
    padding:1px 5px !important;color:#fff !important;opacity:1 !important}
}
</style>
"""
st.markdown(DESKTOP_MODE_VIEWPORT_CSS, unsafe_allow_html=True)


# =====================================================================
# FINAL MOBILE-FIRST RESTORE — normal phone layout, playable video preview
# Overrides legacy landscape/desktop rules above.
# =====================================================================
MOBILE_NORMAL_NEON_CSS = r"""
<style>
:root { color-scheme: dark; }
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMainBlockContainer"] {
  width:100% !important; min-height:100% !important; height:auto !important;
  max-height:none !important; overflow-x:hidden !important; overflow-y:auto !important;
  background:radial-gradient(ellipse at 5% 8%,rgba(255,20,147,.22),transparent 32%),
    radial-gradient(ellipse at 95% 12%,rgba(0,210,255,.20),transparent 34%),
    linear-gradient(145deg,#03091e 0%,#10133d 52%,#06172e 100%) !important;
  color:#f7f8ff !important;
}
.stApp::before {content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:linear-gradient(115deg,transparent 35%,rgba(0,220,255,.08) 48%,rgba(255,20,147,.07) 52%,transparent 65%);
  background-size:240% 100%;animation:kvai-mobile-light 8s linear infinite}
@keyframes kvai-mobile-light {from{background-position:180% 0}to{background-position:-60% 0}}
.block-container {width:100% !important;max-width:100% !important;height:auto !important;
  min-height:0 !important;max-height:none !important;overflow:visible !important;
  padding:.55rem .65rem 1.2rem !important;margin:0 auto !important;position:relative;z-index:1}
[data-testid="stMain"] {height:auto !important;min-height:0 !important;overflow:visible !important}
[data-testid="stVerticalBlock"] {gap:.65rem !important}
[data-testid="stElementContainer"] {margin:0 !important}
.kvai-head {height:auto !important;min-height:66px !important;max-height:none !important;
  margin:0 0 8px !important;padding:8px 10px !important;gap:9px !important;flex-wrap:nowrap !important}
.kvai-logo {width:42px !important;height:42px !important;flex:0 0 42px !important;font-size:22px !important}
.kvai-title {min-width:0 !important}
.kvai-title h1 {font-size:clamp(1.05rem,5vw,1.45rem) !important;line-height:1.15 !important}
.kvai-title p {display:block !important;font-size:.68rem !important;line-height:1.25 !important}
.kvai-badge {font-size:.66rem !important;padding:4px 7px !important;white-space:nowrap !important}
[data-baseweb="tab-list"] {display:flex !important;flex-wrap:nowrap !important;overflow-x:auto !important;
  overflow-y:hidden !important;gap:4px !important;scrollbar-width:thin !important}
button[data-baseweb="tab"] {flex:0 0 auto !important;min-width:max-content !important;height:40px !important;padding:0 10px !important}
button[data-baseweb="tab"] p {font-size:.78rem !important;white-space:nowrap !important}
[data-baseweb="tab-panel"] {height:auto !important;max-height:none !important;overflow:visible !important;padding:4px 0 !important}
/* Standard mobile: the three desktop columns become a clean vertical flow. */
[data-testid="stHorizontalBlock"] {display:flex !important;flex-wrap:wrap !important;flex-direction:column !important;
  gap:.65rem !important;align-items:stretch !important}
[data-testid="stColumn"] {width:100% !important;min-width:100% !important;max-width:100% !important;flex:1 1 100% !important}
.kvai-panel-title {font-size:1rem !important;margin:2px 0 5px !important}
div[data-testid="stVerticalBlockBorderWrapper"] {padding:7px 6px !important;border-radius:14px !important}
[data-testid="stWidgetLabel"] p,.stApp label {font-size:.88rem !important;line-height:1.3 !important}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p {font-size:.75rem !important;line-height:1.35 !important}
[data-testid="stFileUploaderDropzone"] {min-height:78px !important;padding:12px !important}
[data-testid="stVideo"] {width:100% !important;max-width:100% !important;overflow:visible !important}
[data-testid="stVideo"] video {display:block !important;width:100% !important;max-height:min(52vh,360px) !important;
  height:auto !important;min-height:150px !important;object-fit:contain !important;pointer-events:auto !important;
  background:#000 !important;border-radius:12px !important}
.kvai-empty-preview {height:190px !important;max-height:none !important;min-height:150px !important}
.kvai-play {width:54px !important;height:54px !important;font-size:24px !important}
.kvai-filmstrip {display:flex !important}
[data-baseweb="select"]>div {min-height:42px !important}
.stTextInput input,.stNumberInput input {min-height:42px !important}
.stTextArea textarea {min-height:76px !important}
.stButton>button,.stDownloadButton>button {min-height:42px !important;font-size:.88rem !important}
[data-testid="stExpander"] {margin:5px 0 !important}
[data-testid="stExpander"] details {overflow:visible !important}
/* Start button is in normal flow, never fixed over the video player. */
.st-key-startbar {position:static !important;left:auto !important;right:auto !important;bottom:auto !important;
  transform:none !important;width:100% !important;z-index:1 !important;margin:8px 0 0 !important;
  padding:5px 0 !important;background:transparent !important;border:0 !important;backdrop-filter:none !important}
.st-key-startbar [data-testid="stVerticalBlockBorderWrapper"],
.st-key-startbar [data-testid="stVerticalBlock"] {background:transparent !important;border:0 !important;box-shadow:none !important}
.st-key-startbar .stButton>button {min-height:48px !important;font-size:.95rem !important}
.stApp::before {pointer-events:none !important}
/* Wider screens keep the original desktop columns; phone widths stay mobile-first. */
@media (min-width:760px) {
  .block-container {max-width:1200px !important;padding:1rem 1.2rem 2rem !important}
  [data-testid="stHorizontalBlock"] {flex-direction:row !important;flex-wrap:nowrap !important}
  [data-testid="stColumn"] {min-width:0 !important;max-width:none !important;flex:1 1 0 !important}
}
</style>
"""
st.markdown(MOBILE_NORMAL_NEON_CSS, unsafe_allow_html=True)


# =====================================================================
# FINAL POLISHED MOBILE LAYOUT
# Keep the existing feature locations and horizontal dashboard grouping.
# No orientation lock, no fixed overlays, and no forced vertical stacking.
# =====================================================================
POLISHED_MOBILE_LAYOUT_CSS = r"""
<style>
/* Always let the normal mobile page size itself naturally; do not clip content. */
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stMainBlockContainer"] {
  height:auto !important; min-height:100% !important; max-height:none !important;
  overflow-x:hidden !important; overflow-y:auto !important;
}
[data-testid="stMain"] { overflow:visible !important; }
.block-container { height:auto !important; max-height:none !important; overflow:visible !important; }

/* Tight, consistent page frame */
.block-container {
  width:100% !important; max-width:100% !important;
  padding: .42rem .5rem .8rem !important;
  margin: 0 auto !important;
}
[data-testid="stVerticalBlock"] { gap:.38rem !important; }
[data-testid="stElementContainer"] { margin:0 !important; }

/* Header: slightly larger, aligned in one row */
.kvai-head {
  display:flex !important; flex-direction:row !important; flex-wrap:nowrap !important;
  align-items:center !important; justify-content:flex-start !important;
  width:100% !important; min-height:78px !important; height:78px !important;
  max-height:78px !important; box-sizing:border-box !important;
  gap:10px !important; margin:0 0 5px !important; padding:7px 10px !important;
}
.kvai-logo {
  flex:0 0 46px !important; width:46px !important; height:46px !important;
  font-size:24px !important;
}
.kvai-title { flex:1 1 auto !important; min-width:0 !important; }
.kvai-title h1 {
  font-size:clamp(1.05rem,4.3vw,1.42rem) !important;
  line-height:1.1 !important; white-space:nowrap !important;
}
.kvai-title p {
  display:block !important; font-size:clamp(.58rem,2.3vw,.72rem) !important;
  line-height:1.15 !important; margin:2px 0 0 !important;
  white-space:nowrap !important; overflow:hidden !important; text-overflow:ellipsis !important;
}
.kvai-badge {
  flex:0 0 auto !important; padding:4px 7px !important;
  font-size:clamp(.58rem,2.2vw,.7rem) !important; white-space:nowrap !important;
}

/* Keep all seven feature tabs in their original horizontal navigation row */
[data-baseweb="tab-list"] {
  display:flex !important; flex-direction:row !important; flex-wrap:nowrap !important;
  gap:3px !important; margin:2px 0 4px !important; padding:3px !important;
  overflow-x:auto !important; overflow-y:hidden !important;
  scrollbar-width:thin !important;
}
button[data-baseweb="tab"] {
  flex:0 0 auto !important; min-width:max-content !important;
  height:38px !important; padding:0 9px !important;
}
button[data-baseweb="tab"] p { font-size:.76rem !important; white-space:nowrap !important; }
[data-baseweb="tab-panel"] {
  height:auto !important; max-height:none !important;
  overflow:visible !important; padding:3px 0 5px !important;
}

/* Keep the main upload / preview / AI-control panels side-by-side.
   Other feature controls remain in their original tabs and order. */
[data-testid="stHorizontalBlock"] {
  display:flex !important; flex-direction:row !important; flex-wrap:nowrap !important;
  align-items:stretch !important; gap:.32rem !important; width:100% !important;
}
[data-testid="stColumn"] {
  min-width:0 !important; max-width:none !important;
  flex:1 1 0 !important; width:0 !important;
}
[data-testid="stColumn"] > div { min-width:0 !important; }
.kvai-panel-title {
  display:flex !important; align-items:center !important;
  gap:5px !important; font-size:clamp(.68rem,2.8vw,.9rem) !important;
  line-height:1.15 !important; margin:1px 0 3px !important; padding:5px 6px !important;
}
.kvai-step { width:24px !important; height:24px !important; flex:0 0 24px !important; font-size:.76rem !important; }

/* Compact controls, but preserve usable touch targets */
div[data-testid="stVerticalBlockBorderWrapper"] {
  padding:4px !important; border-radius:11px !important;
}
[data-testid="stWidgetLabel"] p, .stApp label {
  font-size:clamp(.62rem,2.4vw,.78rem) !important;
  line-height:1.15 !important; margin-bottom:2px !important;
}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
  font-size:clamp(.56rem,2.1vw,.68rem) !important;
  line-height:1.2 !important; margin:1px 0 !important;
}
[data-testid="stFileUploaderDropzone"] { min-height:54px !important; padding:5px !important; }
[data-testid="stFileUploaderDropzoneInstructions"] { padding:0 !important; }
[data-testid="stFileUploaderDropzoneInstructions"] span,
[data-testid="stFileUploaderDropzoneInstructions"] small { font-size:.62rem !important; }
[data-testid="stVideo"] { width:100% !important; max-width:100% !important; }
[data-testid="stVideo"] video {
  width:100% !important; height:auto !important; min-height:90px !important;
  max-height:clamp(105px,30vh,190px) !important; object-fit:contain !important;
  pointer-events:auto !important; background:#000 !important;
}
.kvai-empty-preview { height:clamp(105px,30vh,170px) !important; min-height:100px !important; }
.kvai-play { width:42px !important; height:42px !important; font-size:19px !important; }
.kvai-filmstrip { margin:3px 0 !important; padding:3px !important; font-size:.7rem !important; }
[data-baseweb="select"] > div { min-height:34px !important; }
.stTextInput input, .stNumberInput input { min-height:34px !important; }
.stTextArea textarea { min-height:48px !important; }
.stButton > button, .stDownloadButton > button {
  min-height:36px !important; padding:4px 6px !important;
  font-size:clamp(.65rem,2.5vw,.8rem) !important; white-space:normal !important;
}
[data-testid="stExpander"] { margin:2px 0 !important; }
[data-testid="stExpander"] summary { min-height:34px !important; padding:4px 7px !important; }
[data-testid="stExpander"] details { overflow:visible !important; }

/* Keep start action in normal page flow; never cover other controls */
.st-key-startbar {
  position:static !important; inset:auto !important; transform:none !important;
  width:100% !important; margin:3px 0 5px !important; padding:3px 5px !important;
  z-index:2 !important; border:1px solid rgba(0,220,255,.55) !important;
  border-radius:12px !important;
  background:linear-gradient(100deg,rgba(255,20,147,.20),rgba(8,18,53,.96),rgba(0,210,255,.20)) !important;
  box-shadow:0 0 14px rgba(0,210,255,.16) !important;
}
.st-key-startbar [data-testid="stVerticalBlockBorderWrapper"],
.st-key-startbar [data-testid="stVerticalBlock"] {
  background:transparent !important; border:0 !important; box-shadow:none !important;
}
.st-key-startbar .stButton > button { min-height:42px !important; font-size:.86rem !important; }

/* Very narrow phones: retain row layout and reduce only visual scale */
@media (max-width:420px) {
  .block-container { padding:.3rem .32rem .65rem !important; }
  .kvai-head { min-height:72px !important; height:72px !important; max-height:72px !important;
    gap:6px !important; padding:5px 6px !important; }
  .kvai-logo { flex-basis:38px !important; width:38px !important; height:38px !important; font-size:20px !important; }
  .kvai-title h1 { font-size:1rem !important; }
  .kvai-title p { font-size:.55rem !important; }
  .kvai-badge { font-size:.55rem !important; padding:3px 5px !important; }
  [data-testid="stHorizontalBlock"] { gap:.22rem !important; }
  .kvai-panel-title { font-size:.65rem !important; padding:4px !important; }
  .kvai-step { width:20px !important; height:20px !important; flex-basis:20px !important; font-size:.65rem !important; }
  div[data-testid="stVerticalBlockBorderWrapper"] { padding:3px !important; }
  [data-testid="stWidgetLabel"] p, .stApp label { font-size:.59rem !important; }
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { font-size:.53rem !important; }
  [data-testid="stFileUploaderDropzone"] { min-height:46px !important; padding:3px !important; }
  [data-testid="stVideo"] video, .kvai-empty-preview { max-height:112px !important; min-height:88px !important; }
  .stButton > button, .stDownloadButton > button { min-height:33px !important; font-size:.61rem !important; }
}
/* On tablets and desktop keep the same feature positions with comfortable sizing */
@media (min-width:760px) {
  .block-container { max-width:1500px !important; padding:.7rem 1rem 1.2rem !important; }
  [data-testid="stHorizontalBlock"] { gap:.55rem !important; }
  .kvai-head { min-height:84px !important; height:84px !important; max-height:84px !important; }
}
</style>
"""
st.markdown(POLISHED_MOBILE_LAYOUT_CSS, unsafe_allow_html=True)


# =====================================================================
# FINAL MOBILE READABILITY PATCH
# Keep the three main workflow panels side-by-side and swipe horizontally
# on phones instead of squeezing all controls into unreadably narrow columns.
# Also improve contrast for labels, captions, inputs, and progress indicators.
# =====================================================================
MOBILE_READABILITY_PATCH_CSS = r"""
<style>
@media (max-width: 759px) {
  /* Only the main Upload / Preview / AI panels: horizontal swipe, not stacking. */
  [data-testid="stHorizontalBlock"]:has(.kvai-panel-title) {
    display:flex !important;
    flex-direction:row !important;
    flex-wrap:nowrap !important;
    align-items:stretch !important;
    gap:10px !important;
    width:100% !important;
    max-width:100% !important;
    overflow-x:auto !important;
    overflow-y:visible !important;
    padding:2px 2px 10px !important;
    scroll-snap-type:x proximity !important;
    -webkit-overflow-scrolling:touch !important;
    scrollbar-width:thin !important;
  }
  [data-testid="stHorizontalBlock"]:has(.kvai-panel-title) > [data-testid="stColumn"] {
    flex:0 0 76vw !important;
    width:76vw !important;
    min-width:76vw !important;
    max-width:76vw !important;
    scroll-snap-align:start !important;
  }
  [data-testid="stHorizontalBlock"]:has(.kvai-panel-title) > [data-testid="stColumn"] > div {
    min-width:0 !important;
  }

  /* Readable type inside the three workflow panels. */
  [data-testid="stHorizontalBlock"]:has(.kvai-panel-title) .kvai-panel-title {
    font-size:clamp(.9rem,3.8vw,1.05rem) !important;
    line-height:1.3 !important;
  }
  [data-testid="stHorizontalBlock"]:has(.kvai-panel-title) [data-testid="stWidgetLabel"] p,
  [data-testid="stHorizontalBlock"]:has(.kvai-panel-title) label {
    color:#FFE7A3 !important;
    font-size:.88rem !important;
    line-height:1.35 !important;
  }
  [data-testid="stHorizontalBlock"]:has(.kvai-panel-title) [data-testid="stCaptionContainer"],
  [data-testid="stHorizontalBlock"]:has(.kvai-panel-title) [data-testid="stCaptionContainer"] p {
    color:#C8DFFF !important;
    font-size:.78rem !important;
    line-height:1.4 !important;
  }
}

/* Strong readable contrast: avoid white text disappearing on pale controls. */
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stText"],
.stApp .stMarkdown p,
.stApp li {
  color:#EAF3FF !important;
}
.stApp [data-testid="stWidgetLabel"] p,
.stApp label {
  color:#FFE7A3 !important;
}
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stCaptionContainer"] p {
  color:#C5D9F7 !important;
}
.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea {
  color:#FFFFFF !important;
  caret-color:#42E6FF !important;
  background:#0B173B !important;
}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
  color:#AFC4E8 !important;
  opacity:1 !important;
}
/* Progress track and progress text must not be pale-on-white. */
[data-testid="stProgress"] > div > div {
  background:#26365F !important;
}
[data-testid="stProgress"] [data-testid="stMarkdownContainer"],
[data-testid="stProgress"] p {
  color:#FFE7A3 !important;
}
/* Native metric values remain bright; their labels use a warm readable tone. */
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {
  color:#FFFFFF !important;
}
[data-testid="stMetricLabel"] p {
  color:#FFE7A3 !important;
}
</style>
"""
st.markdown(MOBILE_READABILITY_PATCH_CSS, unsafe_allow_html=True)
