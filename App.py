import os
import io
import re
import json
import time
import uuid
import shutil
import asyncio
import datetime
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
    page_title="áž”áž€áž”áŸ’ážšáŸ‚ážšáž¿áž„áž˜áž€áž“áž·áž™áž¶áž™áž—áž¶ážŸáž¶ážáŸ’áž˜áŸ‚ážš",
    page_icon="ðŸŽ¬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =====================================================================
#  THEME (ážŸáŸ’áž”áŸ‚áž€ážáŸ’áž˜áž¸ v2)
# =====================================================================
for _k, _v in {
    "theme.base": "dark",
    "theme.primaryColor": "#2F6BFF",
    "theme.backgroundColor": "#0A0F2C",
    "theme.secondaryBackgroundColor": "#121842",
    "theme.textColor": "#EEF2FF",
}.items():
    try:
        st._config.set_option(_k, _v)
    except Exception:
        pass

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Kantumruy+Pro:wght@400;500;600;700;800&display=swap');

:root {
  --bg: #0A0F2C;
  --bg2: #0D1336;
  --panel: #121842;
  --panel2: #1A2158;
  --line: #2A3270;
  --text: #EEF2FF;
  --muted: #9AA6D8;
  --blue: #2F6BFF;
  --blue2: #1F54E0;
  --green: #2ED47A;
  --red: #FF5470;
  --gold: #F5A524;
  --r-lg: 18px;
  --r-md: 14px;
  --r-sm: 10px;
}

#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
.stDeployButton, [data-testid="stStatusWidget"], [class*="viewerBadge"],
[data-testid="manage-app-button"] { display: none !important; }

html, body, .stApp, [data-testid="stAppViewContainer"] {
  background: radial-gradient(1200px 600px at 70% -10%, #17205a 0%, var(--bg) 60%) !important;
  color: var(--text);
  font-family: 'Kantumruy Pro', 'Battambang', system-ui, sans-serif !important;
  color-scheme: dark;
}
.stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp li, .stApp small,
.stApp textarea, .stApp input, .stApp button p, .stApp a, .stApp span,
.stApp [data-baseweb="select"] div, .stApp [data-testid="stMarkdownContainer"] {
  font-family: 'Kantumruy Pro', 'Battambang', system-ui, sans-serif;
}
[data-testid="stIconMaterial"], [class*="material-symbols"], .material-icons {
  font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}
[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {
  display: flex !important; color: #fff !important;
}
[data-testid="stSidebarCollapsedControl"] *, [data-testid="collapsedControl"] * { color: #fff !important; }
.block-container { max-width: 100% !important; padding: .4rem 1.2rem 3rem !important; }

.stMarkdown, .stMarkdown p, [data-testid="stText"], h1, h2, h3,
label, [data-testid="stWidgetLabel"] p, [data-testid="stCheckbox"] p {
  color: var(--text) !important;
}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--muted) !important; }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0E1540 0%, #090E2B 100%) !important;
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] > div { padding-top: .6rem; }
.kac-brand { text-align: center; padding: 6px 4px 12px; }
.kac-brand .logo {
  width: 74px; height: 74px; margin: 0 auto 8px; border-radius: 20px;
  display: flex; align-items: center; justify-content: center; font-size: 2.2rem;
  background: linear-gradient(145deg, #2F6BFF, #7C3AED);
  box-shadow: 0 8px 22px rgba(47,107,255,.45);
}
.kac-brand b { display: block; font-size: 1.2rem; font-weight: 800; color: #fff !important; }
.kac-brand .tag {
  display: inline-block; margin-top: 6px; padding: 3px 14px; border-radius: 999px;
  background: linear-gradient(90deg, #6D4CFF, #2F6BFF); font-size: .78rem; font-weight: 700; color: #fff !important;
}
.kac-brand small { display: block; margin-top: 6px; color: var(--muted) !important; }

[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] {
  flex-direction: column !important; flex-wrap: nowrap !important; gap: 6px; width: 100%;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
  flex: none !important; width: 100%; justify-content: flex-start !important;
  background: rgba(255,255,255,.04); border: 1px solid transparent; border-radius: 14px;
  padding: 12px 14px !important; margin: 0 !important; cursor: pointer;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background: rgba(255,255,255,.09); }
[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child { display: none !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
  background: linear-gradient(90deg, #2F6BFF, #1F54E0); border-color: #5B8DFF;
  box-shadow: 0 6px 16px rgba(47,107,255,.35);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label p { font-weight: 600; font-size: .95rem; }

/* ---------- Token bar ---------- */
.kac-token {
  display: flex; flex-direction: column; gap: 8px; margin: 12px 0 4px;
  background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 12px 14px;
}
.kac-token .bal { display: flex; align-items: center; gap: 8px; font-weight: 800; font-size: 1.05rem; color: var(--text) !important; }
.kac-token .coin {
  width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  font-size: .85rem; background: radial-gradient(circle at 35% 35%, #FFD27A, #F5A524 75%);
}
.kac-token .lbl { font-weight: 500; font-size: .78rem; color: var(--muted) !important; }
.kac-token .cost {
  background: rgba(245,165,36,.15); color: #FFD27A !important; border-radius: 999px;
  padding: 4px 12px; font-size: .78rem; font-weight: 700; text-align: center;
}

/* ---------- Hero ---------- */
.kac-hero {
  display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-wrap: wrap;
  background: linear-gradient(120deg, #141B52 0%, #0F1544 100%);
  border: 1px solid var(--line); border-radius: 22px; padding: 16px 22px; margin-bottom: 16px;
}
.kac-hero h1 { margin: 0 !important; padding: 0 !important; font-size: clamp(1.4rem, 3.4vw, 2.3rem) !important; font-weight: 800 !important; color: #fff !important; }
.kac-hero h1 span { color: #4D86FF !important; }
.kac-hero p { margin: 6px 0 0; color: var(--muted) !important; font-size: .95rem; }
.kac-hero .pill {
  display: inline-block; padding: 3px 12px; border-radius: 8px; margin-right: 8px;
  background: linear-gradient(90deg, #6D4CFF, #2F6BFF); color: #fff !important; font-size: .82rem;
}
.kac-feats { display: flex; gap: 14px; flex-wrap: wrap; }
.kac-feats div { text-align: center; min-width: 78px; }
.kac-feats i {
  display: flex; width: 44px; height: 44px; margin: 0 auto 4px; border-radius: 12px; font-style: normal;
  align-items: center; justify-content: center; font-size: 1.3rem; background: linear-gradient(145deg, #2F6BFF, #7C3AED);
}
.kac-feats b { display: block; font-size: .72rem; color: #fff !important; }
.kac-feats small { display: block; font-size: .66rem; color: var(--muted) !important; }

.kac-rotate {
  display: none; align-items: center; gap: 10px; margin-bottom: 12px; padding: 10px 14px;
  background: rgba(245,165,36,.14); border: 1px solid rgba(245,165,36,.4); border-radius: 12px;
  color: #FFD27A !important; font-size: .9rem; font-weight: 600;
}
.kac-rotate * { color: #FFD27A !important; }
@media (orientation: portrait) and (max-width: 700px) { .kac-rotate { display: flex; } }

/* ---------- Section headings ---------- */
.kac-sec { display: flex; align-items: center; gap: 10px; margin: 18px 0 8px; font-weight: 700; font-size: 1.08rem; color: #fff !important; }
.kac-sec::before { content: ""; width: 5px; height: 22px; border-radius: 4px; background: var(--blue); }
.kac-sec b { color: var(--muted) !important; font-weight: 600; }
.kac-card-title { font-weight: 700; font-size: 1.02rem; margin: 2px 0 8px; color: #fff !important; }

/* ---------- Cards ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--panel) !important; border: 1px solid var(--line) !important;
  border-radius: var(--r-lg) !important; box-shadow: 0 4px 18px rgba(0,0,0,.25); padding: 8px 6px;
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--panel2) !important; box-shadow: none;
}

/* ---------- Select ---------- */
[data-baseweb="select"] > div, [data-testid="stSelectbox"] [data-baseweb="select"] > div {
  background-color: var(--panel2) !important; border: 1.5px solid var(--line) !important;
  border-radius: var(--r-sm) !important; color: var(--text) !important; min-height: 46px;
}
[data-baseweb="select"] > div:focus-within, [data-baseweb="select"] > div:hover {
  border-color: var(--blue) !important; box-shadow: 0 0 0 3px rgba(47,107,255,.25) !important;
}
[data-baseweb="select"] * { color: var(--text) !important; }
[data-baseweb="select"] svg { fill: var(--text) !important; }
[data-baseweb="popover"], [data-baseweb="popover"] > div { background: transparent !important; }
[data-baseweb="popover"] ul, [data-baseweb="popover"] li, [data-baseweb="menu"] {
  background: #161D4D !important; color: var(--text) !important;
}
[data-baseweb="popover"] li:hover { background: rgba(47,107,255,.35) !important; }

/* ---------- Inputs ---------- */
.stTextArea textarea, .stTextInput input, [data-baseweb="textarea"], [data-baseweb="textarea"] > div,
[data-baseweb="input"], [data-baseweb="input"] > div {
  background: var(--panel2) !important; border: 1.5px solid var(--line) !important;
  border-radius: var(--r-sm) !important; color: var(--text) !important;
}
.stTextArea textarea:focus, .stTextInput input:focus { border-color: var(--blue) !important; box-shadow: 0 0 0 3px rgba(47,107,255,.25) !important; }
::placeholder { color: #6E79B8 !important; }

/* ---------- Radio => pills (main) ---------- */
[data-testid="stMain"] [data-testid="stRadio"] [role="radiogroup"], .main [data-testid="stRadio"] [role="radiogroup"] {
  gap: 8px; flex-wrap: wrap; width: 100%;
}
[data-testid="stMain"] [data-testid="stRadio"] label, .main [data-testid="stRadio"] label {
  flex: 1 1 auto; justify-content: center; background: var(--panel2); border: 1.5px solid var(--line);
  border-radius: 12px; padding: 9px 14px !important; margin: 0 !important; cursor: pointer;
}
[data-testid="stMain"] [data-testid="stRadio"] label > div:first-child, .main [data-testid="stRadio"] label > div:first-child { display: none !important; }
[data-testid="stMain"] [data-testid="stRadio"] label:has(input:checked), .main [data-testid="stRadio"] label:has(input:checked) {
  background: linear-gradient(180deg, #2F6BFF, #1F54E0); border-color: #5B8DFF;
}
[data-testid="stMain"] [data-testid="stRadio"] label:has(input:checked) *, .main [data-testid="stRadio"] label:has(input:checked) * { color: #fff !important; }

[data-testid="stMain"] [data-testid="stRadio"] [role="radiogroup"] label { min-height: 46px; align-items: center; }

/* ---------- Checkbox ---------- */
[data-testid="stCheckbox"] label > span:first-child, [data-baseweb="checkbox"] > span:first-child {
  border-radius: 7px !important; border: 1.5px solid #5F6BB5 !important; background-color: transparent !important;
}
[data-testid="stCheckbox"] label:has(input:checked) > span:first-child, [data-baseweb="checkbox"]:has(input:checked) > span:first-child {
  background-color: var(--blue) !important; border-color: var(--blue) !important;
}

/* ---------- Slider ---------- */
[data-testid="stSlider"] [role="slider"] { background: var(--blue) !important; border-color: var(--blue) !important; }
[data-testid="stSlider"] [data-testid="stThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] { color: var(--text) !important; }

/* ---------- Uploader ---------- */
[data-testid="stFileUploaderDropzone"] {
  background: rgba(47,107,255,.07); border: 2px dashed #4D6BD6; border-radius: var(--r-lg); padding: 24px 16px;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: #7FA2FF; background: rgba(47,107,255,.14); }
[data-testid="stFileUploaderDropzone"] * { color: var(--text) !important; }
[data-testid="stFileUploaderDropzone"] button {
  background: linear-gradient(180deg, #2F6BFF, #1F54E0) !important; color: #fff !important;
  border-radius: 12px !important; border: none !important; min-height: 44px; font-weight: 700;
}
[data-testid="stFileUploaderDropzone"] button * { color: #fff !important; }
[data-testid="stFileUploaderFile"] * { color: var(--text) !important; }

/* ---------- Buttons ---------- */
.stButton > button, .stDownloadButton > button {
  border-radius: 12px; border: 1.5px solid var(--line); background: var(--panel2); color: var(--text);
  font-weight: 700; min-height: 46px; transition: transform .12s ease, box-shadow .12s ease;
}
.stButton > button *, .stDownloadButton > button * { color: inherit !important; }
.stButton > button:hover, .stDownloadButton > button:hover { transform: translateY(-1px); border-color: #5B8DFF; }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(180deg, #2F6BFF, #1F54E0) !important; border: none !important; color: #fff !important;
  box-shadow: 0 8px 20px rgba(47,107,255,.4);
}
.stButton > button[kind="primary"] *, .stDownloadButton > button[kind="primary"] * { color: #fff !important; }
.kac-start .stButton > button[kind="primary"] { min-height: 62px; font-size: 1.1rem; border-radius: 16px; }
.stButton > button:focus-visible { outline: 3px solid var(--gold); outline-offset: 2px; }
.stButton > button:disabled { background: #1B2250 !important; color: #6E79B8 !important; box-shadow: none; transform: none; border-color: var(--line) !important; }

/* ---------- Progress ---------- */
[data-testid="stProgress"] > div > div { background: #232B66 !important; border-radius: 999px; }
[data-testid="stProgress"] > div > div > div { background: var(--blue) !important; border-radius: 999px; }

/* ---------- Metrics / alerts / expander ---------- */
[data-testid="stMetric"] { background: var(--panel2); border: 1px solid var(--line); border-radius: var(--r-md); padding: 12px 14px; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * { font-weight: 800; color: var(--text) !important; }
[data-testid="stMetricLabel"] p { color: var(--muted) !important; }
[data-testid="stAlert"] { border-radius: var(--r-md); border: none; }
[data-testid="stExpander"] { background: var(--panel2); border: 1.5px solid var(--line) !important; border-radius: var(--r-md); }
[data-testid="stExpander"] * { color: var(--text) !important; }
[data-testid="stVideo"] video { border-radius: var(--r-md); background: #000; }
hr { border-color: var(--line) !important; margin: 1.2rem 0 !important; }
[data-testid="stTable"] table, [data-testid="stTable"] th, [data-testid="stTable"] td { color: var(--text) !important; border-color: var(--line) !important; }

/* ---------- Processing rows ---------- */
.kac-row {
  display: flex; align-items: center; gap: 14px; background: var(--panel2);
  border: 1px solid var(--line); border-radius: 14px; padding: 10px 14px;
}
.kac-row .ring {
  --p: 0; flex: none; width: 50px; height: 50px; border-radius: 50%; display: grid; place-items: center; position: relative;
  background: conic-gradient(var(--blue) calc(var(--p) * 1%), #2A3270 0);
}
.kac-row .ring::before { content: ""; position: absolute; inset: 5px; background: var(--panel2); border-radius: 50%; }
.kac-row .ring span { position: relative; font-size: .72rem; font-weight: 800; color: #fff !important; }
.kac-row .meta { flex: 1; min-width: 0; }
.kac-row .meta b { display: block; font-size: .95rem; color: #fff !important; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kac-row .meta .track { height: 7px; border-radius: 999px; background: #2A3270; margin: 6px 0 4px; overflow: hidden; }
.kac-row .meta .track i { display: block; height: 100%; background: linear-gradient(90deg, #2F6BFF, #7FA2FF); border-radius: 999px; }
.kac-row .meta small { color: var(--muted) !important; font-size: .78rem; }
.kac-row .secs { flex: none; color: var(--muted) !important; font-size: .78rem; }

.kac-vname b { display: block; color: #fff !important; font-size: .95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kac-vname small { color: var(--muted) !important; font-size: .78rem; }

/* ---------- Caption preview ---------- */
.kac-stage {
  position: relative; height: 150px; border-radius: 14px; overflow: hidden; margin-top: 8px;
  background: linear-gradient(180deg, #2A3A86 0%, #1A2358 62%, #101638 100%); display: flex; padding: 10px 12px;
}
.kac-stage::before {
  content: ""; position: absolute; left: 50%; top: 22px; width: 54px; height: 54px; transform: translateX(-50%);
  border-radius: 50%; background: radial-gradient(circle at 35% 35%, #FFD27A, #F5A524 70%); box-shadow: 0 0 36px 8px rgba(245,165,36,.3);
}
.kac-stage .cap { position: relative; z-index: 2; width: 100%; text-align: center; font-weight: 800; line-height: 1.3; }

/* ---------- áž‘áž¼ážšážŸáž–áŸ’áž‘áŸ– ážšáž€áŸ’ážŸáž¶ layout ážŠáž¼áž… PC ---------- */
@media (max-width: 1100px) {
  [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
  [data-testid="stColumn"], [data-testid="column"] { min-width: 0 !important; }
  .block-container { padding: .3rem .8rem 3rem !important; }
  .kac-hero { padding: 8px 14px !important; margin-bottom: 8px !important; }
  .kac-hero h1 { font-size: 1.5rem !important; }
  .kac-hero p { font-size: .8rem !important; margin-top: 2px !important; }
  .kac-feats { display: none !important; }
  .kac-rotate { display: none !important; }
}

/* ---------- áž€áŸ‚áž”áž‰áŸ’áž áž¶áž˜áž¶ážáž·áž€áž¶áž˜áž·áž“áž–áŸáž‰áž¢áŸáž€áŸ’ážšáž„áŸ‹ ---------- */
[data-testid="stAppViewContainer"], [data-testid="stMain"] {
  overflow-y: auto !important;
}
html, body { min-height: 100%; background: var(--bg) !important; }

/* ---------- áž•áŸ’áž‘áŸƒážáž¶áž„áž€áŸ’ážšáŸ„áž™áž‘áž¹áž€ážŸáž˜áž»áž‘áŸ’ážš ---------- */
html, body, .stApp, [data-testid="stAppViewContainer"] {
  background: linear-gradient(180deg,#0E6BA0 0%,#0A4F82 30%,#073862 65%,#031D3A 100%) !important;
}
[data-testid="stMain"] { background: transparent !important; }
.block-container { position: relative; z-index: 1; }

.kac-sea { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
.kac-sea .light {
  position: absolute; top: -10%; left: 0; right: 0; height: 60%;
  background: radial-gradient(ellipse at 30% 0%, rgba(130,225,255,.28), transparent 65%);
  animation: sway 9s ease-in-out infinite alternate;
}
@keyframes sway { from { transform: translateX(-4%); } to { transform: translateX(4%); } }

.kac-sea .swim { position: absolute; left: 105vw; animation: swim linear infinite; }
.kac-sea .swim span { display: block; animation: bob ease-in-out infinite alternate; opacity: .9; }
@keyframes swim { to { transform: translateX(-130vw); } }
@keyframes bob { from { transform: translateY(-10px); } to { transform: translateY(10px); } }

.kac-sea .bub {
  position: absolute; bottom: -30px; border-radius: 50%;
  border: 1.5px solid rgba(190,240,255,.55); background: rgba(190,240,255,.12);
  animation: rise linear infinite;
}
@keyframes rise { to { transform: translateY(-110vh) translateX(18px); opacity: 0; } }

/* áž”áŸ’ážšáž¢áž”áŸ‹ážáŸ’áž›áž¶áž”áž“áŸ’ážáž·áž… áž²áŸ’áž™ážƒáž¾áž‰áž‘áž¹áž€áž–áž¸áž€áŸ’ážšáŸ„áž™ áž áž¾áž™áž¢áž¶áž“áž¢áž€áŸ’ážŸážšáž”áž¶áž“áž…áŸ’áž”áž¶ážŸáŸ‹ */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: rgba(8,28,64,.80) !important; backdrop-filter: blur(6px);
}
.kac-hero { background: rgba(10,34,76,.78) !important; backdrop-filter: blur(6px); }
</style>
"""


def apply_theme():
    st.markdown(THEME_CSS, unsafe_allow_html=True)


DAILY_TOKENS = 10000
TOKEN_COST = 10
TOKEN_TZ = datetime.timezone(datetime.timedelta(hours=7))  # áž˜áŸ‰áŸ„áž„áž€áž˜áŸ’áž–áž»áž‡áž¶
TOKEN_FILE = os.path.join(tempfile.gettempdir(), "kac_tokens.json")
_token_lock = threading.Lock()


def _today():
    return datetime.datetime.now(TOKEN_TZ).strftime("%Y-%m-%d")


def get_user_id():
    uid = st.query_params.get("u", "")
    if not re.fullmatch(r"[A-Za-z0-9]{8,32}", str(uid or "")):
        uid = uuid.uuid4().hex[:16]
        st.query_params["u"] = uid
    return str(uid)


def sync_browser_id(uid):
    """áž…áž„áž…áž¶áŸ†áž›áŸážáž€áž¼ážŠáž¢áŸ’áž“áž€áž”áŸ’ážšáž¾áž€áŸ’áž“áž»áž„ browser (localStorage) ážŠáž¾áž˜áŸ’áž”áž¸áž€áž»áŸ†áž±áŸ’áž™áž¢áž¼ážŸáž€áž˜áŸ’áž˜ážœáž·áž’áž¸áž…áŸ„áž›ážšáž½áž… Token ážáŸ’ážšáž¡áž”áŸ‹áž˜áž€ážœáž·áž‰"""
    js = """
    <script>
    (function () {
      try {
        var uid = "__UID__";
        var w = window.parent;
        var key = "kac_uid";
        var saved = w.localStorage.getItem(key);
        if (saved && /^[A-Za-z0-9]{8,32}$/.test(saved)) {
          if (saved !== uid) {
            var url = new URL(w.location.href);
            url.searchParams.set("u", saved);
            w.location.replace(url.toString());
          }
        } else {
          w.localStorage.setItem(key, uid);
        }
      } catch (e) {}
    })();
    </script>
    """
    components.html(js.replace("__UID__", uid), height=0)


def _load_tokens():
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_tokens(data):
    tmp = TOKEN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, TOKEN_FILE)


def token_balance(uid):
    with _token_lock:
        rec = _load_tokens().get(uid)
    if not rec or rec.get("day") != _today():
        return DAILY_TOKENS
    return max(0, DAILY_TOKENS - int(rec.get("used", 0)))


def spend_tokens(uid, amount):
    today = _today()
    with _token_lock:
        data = {k: v for k, v in _load_tokens().items() if isinstance(v, dict) and v.get("day") == today}
        rec = data.get(uid) or {"day": today, "used": 0}
        if DAILY_TOKENS - int(rec.get("used", 0)) < amount:
            return False
        rec["used"] = int(rec.get("used", 0)) + amount
        data[uid] = rec
        try:
            _save_tokens(data)
        except Exception:
            pass
    return True


STATS_FILE = os.path.join(tempfile.gettempdir(), "kac_stats.json")
_stats_lock = threading.Lock()


def _load_stats():
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_stats(data):
    keep = sorted(data.keys())[-30:]
    data = {k: data[k] for k in keep}
    tmp = STATS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, STATS_FILE)


def _day_rec(data, day):
    return data.setdefault(day, {"videos": 0, "done": 0, "failed": 0, "users": []})


def record_start(uid, count):
    with _stats_lock:
        data = _load_stats()
        rec = _day_rec(data, _today())
        rec["videos"] += count
        if uid not in rec["users"]:
            rec["users"].append(uid)
        try:
            _save_stats(data)
        except Exception:
            pass


def record_result(ok):
    with _stats_lock:
        data = _load_stats()
        rec = _day_rec(data, _today())
        rec["done" if ok else "failed"] += 1
        try:
            _save_stats(data)
        except Exception:
            pass


def today_stats():
    with _stats_lock:
        rec = _load_stats().get(_today())
    return rec or {"videos": 0, "done": 0, "failed": 0, "users": []}


def is_admin():
    key = str(st.secrets.get("ADMIN_KEY", "") or "")
    return bool(key) and str(st.query_params.get("admin", "")) == key


def render_token_bar(uid):
    balance = token_balance(uid)
    st.markdown(
        f"""
        <div class="kac-token">
          <div class="bal">
            <span class="coin">ðŸª™</span>
            <span>{balance:,}</span>
            <span class="lbl">/ {DAILY_TOKENS:,} Token</span>
          </div>
          <div class="cost">áŸ¡ ážœáž¸ážŠáŸáž¢áž¼ = {TOKEN_COST} Token</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Token ážáŸ’áž„áŸƒáž“áŸáŸ‡áŸ” ážŸáŸ’áž¢áŸ‚áž€ážœáž¶áž“áž¹áž„ážáŸ’ážšáž¡áž”áŸ‹áž˜áž€ {DAILY_TOKENS:,} ážœáž·áž‰ážŠáŸ„áž™ážŸáŸ’ážœáŸáž™áž”áŸ’ážšážœážáŸ’ážáž·áŸ”")
    if is_admin():
        st.caption(f"ðŸ” (áž˜áŸ’áž…áž¶ážŸáŸ‹áž”áŸ‰áž»ážŽáŸ’ážŽáŸ„áŸ‡) ðŸŽ¬ ážáŸ’áž„áŸƒáž“áŸáŸ‡áž˜áž¶áž“áž‚áŸáž”áž„áŸ’áž€áž¾ážážœáž¸ážŠáŸáž¢áž¼ážŸážšáž»áž” {today_stats()['videos']:,}")


def render_hero(max_videos=5):
    st.markdown(
        f"""
        <div class="kac-hero">
          <h1>áž”áž€áž”áŸ’ážšáŸ‚ážšáž¿áž„áž˜áž€áž“áž·áž™áž¶áž™áž—áž¶ážŸáž¶ážáŸ’áž˜áŸ‚ážš</h1>
          <p>ážŠáž¶áž€áŸ‹ážœáž¸ážŠáŸáž¢áž¼áž—áž¶ážŸáž¶áž¢áŸ’ážœáž¸áž€áŸáž”áž¶áž“ áž‘áž‘áž½áž›áž”áž¶áž“áž¢áž€áŸ’ážŸážšážšážáŸ‹áž‡áž¶áž—áž¶ážŸáž¶ážáŸ’áž˜áŸ‚ážšážŠáŸ„áž™ážŸáŸ’ážœáŸáž™áž”áŸ’ážšážœážáŸ’ážáž·
             (ážšáž áž¼ážážŠáž›áŸ‹ {max_videos} ážœáž¸ážŠáŸáž¢áž¼ážŸáŸ’áž˜áž¾áž‚áŸ’áž“áž¶)</p>
          <div class="kac-pills">
            <span>ðŸŽ™ ážŸáŸ’ážáž¶áž”áŸ‹ áž“áž·áž„áž”áž€áž”áŸ’ážšáŸ‚</span>
            <span>ðŸ—£ ážŸáŸ†áž¡áŸáž„áž¢áž¶áž“ážáŸ’áž˜áŸ‚ážš</span>
            <span>ðŸŽ­ áž¢áž¶ážšáž˜áŸ’áž˜ážŽáŸáž€áŸ’áž“áž»áž„ážŸáŸ†áž¡áŸáž„</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


apply_theme()

# ---------------------------------------------------------------------
#  áž•áŸ’áž‘áŸƒážáž¶áž„áž€áŸ’ážšáŸ„áž™áž‘áž¹áž€ážŸáž˜áž»áž‘áŸ’ážš + ážŸážáŸ’ážœážŸáž˜áž»áž‘áŸ’ážšáž áŸ‚áž›
# ---------------------------------------------------------------------
import random as _rnd


def render_sea():
    creatures = ["ðŸŸ", "ðŸ ", "ðŸ¡", "ðŸ™", "ðŸ¢", "ðŸ¬", "ðŸ¦‘", "ðŸ¦€", "ðŸŸ", "ðŸ "]
    parts = ['<div class="kac-sea"><div class="light"></div>']
    for i, c in enumerate(creatures):
        top = _rnd.randint(12, 88)
        size = _rnd.choice([1.6, 2.0, 2.4, 3.0])
        dur = _rnd.randint(22, 45)
        delay = -_rnd.randint(0, dur)  # áž…áž¶áž”áŸ‹áž•áŸ’ážŠáž¾áž˜áž–áž¶ážŸáž–áŸáž‰áž¢áŸáž€áŸ’ážšáž„áŸ‹ážáž¶áŸ†áž„áž–áž¸ážŠáŸ†áž”áž¼áž„
        bob = _rnd.randint(3, 6)
        parts.append(
            f'<div class="swim" style="top:{top}%;animation-duration:{dur}s;'
            f'animation-delay:{delay}s"><span style="font-size:{size}rem;'
            f'animation-duration:{bob}s">{c}</span></div>'
        )
    for i in range(16):
        left = _rnd.randint(2, 98)
        size = _rnd.randint(6, 18)
        dur = _rnd.randint(9, 20)
        delay = -_rnd.randint(0, dur)
        parts.append(
            f'<div class="bub" style="left:{left}%;width:{size}px;height:{size}px;'
            f'animation-duration:{dur}s;animation-delay:{delay}s"></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


render_sea()

DEBUG = bool(st.secrets.get("DEBUG", False))

REQUEST_TIMEOUT_MS = 120000
MAX_CAPTION_CHARS = 26
MAX_DOWNLOAD_MB = 300
MAX_VIDEOS = 5
MAX_ZIP_MB = 250
REFRESH_SECONDS = 2
MAX_RENDER_AT_ONCE = 3
MAX_DURATION_MIN = 15

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

# áž–áž»áž˜áŸ’áž–áž¢áž€áŸ’ážŸážšážáŸ’áž˜áŸ‚ážšážŠáŸ‚áž›áž¢áž¶áž…áž‡áŸ’ážšáž¾ážŸáž”áž¶áž“áŸ– ážˆáŸ’áž˜áŸ„áŸ‡áž”áž„áŸ’áž áž¶áž‰ -> (ážˆáŸ’áž˜áŸ„áŸ‡áž¯áž€ážŸáž¶ážš, [áž•áŸ’áž›áž¼ážœáž‘áž¶áž‰áž™áž€...], ážˆáŸ’áž˜áŸ„áŸ‡ Font)
FONT_CHOICES = {
    "Battambang (ážŸáŸ’ážáž„áŸ‹ážŠáž¶ážš)": ("Battambang.ttf", ["battambang/Battambang-Regular.ttf"], "Battambang"),
    "Content": ("Content.ttf", ["content/Content-Regular.ttf"], "Content"),
    "Siemreap": ("Siemreap.ttf", ["siemreap/Siemreap-Regular.ttf"], "Siemreap"),
    "Bokor": ("Bokor.ttf", ["bokor/Bokor-Regular.ttf"], "Bokor"),
    "Hanuman": ("Hanuman.ttf", ["hanuman/Hanuman-Regular.ttf", "hanuman/Hanuman%5Bwght%5D.ttf"], "Hanuman"),
    "Nokora": ("Nokora.ttf", ["nokora/Nokora-Regular.ttf"], "Nokora"),
    "Koulen (áž€áŸ’ážšáž¶ážŸáŸ‹)": ("Koulen.ttf", ["koulen/Koulen-Regular.ttf"], "Koulen"),
    "Moul (áž…áž˜áŸ’áž›áž¶áž€áŸ‹)": ("Moul.ttf", ["moul/Moul-Regular.ttf"], "Moul"),
    "Moulpali": ("Moulpali.ttf", ["moulpali/Moulpali-Regular.ttf"], "Moulpali"),
    "Dangrek": ("Dangrek.ttf", ["dangrek/Dangrek-Regular.ttf"], "Dangrek"),
    "Suwannaphum": ("Suwannaphum.ttf", ["suwannaphum/Suwannaphum-Regular.ttf"], "Suwannaphum"),
    "Chenla": ("Chenla.ttf", ["chenla/Chenla-Regular.ttf"], "Chenla"),
    "Taprom": ("Taprom.ttf", ["taprom/Taprom-Regular.ttf"], "Taprom"),
    "Bayon": ("Bayon.ttf", ["bayon/Bayon-Regular.ttf"], "Bayon"),
    "Angkor": ("Angkor.ttf", ["angkor/Angkor-Regular.ttf"], "Angkor"),
    "Metal": ("Metal.ttf", ["metal/Metal-Regular.ttf"], "Metal"),
    "Freehand (ážŠáŸƒážŸážšážŸáŸážš)": ("Freehand.ttf", ["freehand/Freehand-Regular.ttf"], "Freehand"),
    "Fasthand (ážŠáŸƒážŸážšážŸáŸážš)": ("Fasthand.ttf", ["fasthand/Fasthand-Regular.ttf"], "Fasthand"),
    "Odor Mean Chey": ("OdorMeanChey.ttf", ["odormeanchey/OdorMeanChey-Regular.ttf"], "Odor Mean Chey"),
    "Preahvihear": ("Preahvihear.ttf", ["preahvihear/Preahvihear-Regular.ttf"], "Preahvihear"),
}
DEFAULT_FONT = "Battambang (ážŸáŸ’ážáž„áŸ‹ážŠáž¶ážš)"
FONT_BACKUP = [DEFAULT_FONT, "Content", "Siemreap"]

QUALITY = {
    "âš¡ áž›áž¿áž“": (480, 28, "ultrafast"),
    "âœ¨ áž›áŸ’áž¢ (ážŽáŸ‚áž“áž¶áŸ†)": (720, 24, "veryfast"),
    "ðŸ’Ž áž‚áž»ážŽáž—áž¶áž–ážáŸ’áž–ážŸáŸ‹": (0, 20, "veryfast"),
}

LANGUAGES = {
    "ðŸŒ ážŸáŸ’ážœáŸáž™áž”áŸ’ážšážœážáŸ’ážáž· (áž—áž¶ážŸáž¶áž¢áŸ’ážœáž¸áž€áŸáž”áž¶áž“)": None,
    "ážáŸ’áž˜áŸ‚ážš": "Khmer", "áž¢áž„áŸ‹áž‚áŸ’áž›áŸážŸ": "English", "ážáŸƒ": "Thai",
    "ážœáŸ€ážážŽáž¶áž˜": "Vietnamese", "áž…áž·áž“": "Chinese", "áž‡áž”áŸ‰áž»áž“": "Japanese",
    "áž€áž¼ážšáŸ‰áŸ": "Korean", "áž”áž¶ážšáž¶áŸ†áž„": "French",
}

TTS_VOICES = {
    "ážŸáŸ’ážšáž¸ (Sreymom)": "km-KH-SreymomNeural",
    "áž”áŸ’ážšáž»ážŸ (Piseth)": "km-KH-PisethNeural",
}


class UserError(RuntimeError):
    pass


def friendly_message(error):
    if isinstance(error, UserError):
        return str(error)
    low = str(error).lower()
    if "429" in low or "resource_exhausted" in low or "quota" in low:
        return "áž˜áž¶áž“áž¢áŸ’áž“áž€áž”áŸ’ážšáž¾áž…áŸ’ážšáž¾áž“áž–áŸáž€áŸ” ážŸáž¼áž˜ážšáž„áŸ‹áž…áž¶áŸ†áž˜áž½áž™áž—áŸ’áž›áŸ‚ážáŸ”"
    if any(x in low for x in ("503", "unavailable", "high demand", "overloaded", "timeout", "timed out")):
        return "áž”áŸ’ážšáž–áŸáž“áŸ’áž’ AI áž€áŸ†áž–áž»áž„ážšážœáž›áŸ‹áŸ” ážŸáž¼áž˜ážŸáž¶áž€áž˜áŸ’ážáž„áž‘áŸ€ážáŸ”"
    if "api key" in low or "api_key" in low or "permission" in low:
        return "ážŸáŸážœáž¶ AI áž˜áž¶áž“áž”áž‰áŸ’áž áž¶áŸ” ážŸáž¼áž˜áž‘áž¶áž€áŸ‹áž‘áž„áž˜áŸ’áž…áž¶ážŸáŸ‹áž€áž˜áŸ’áž˜ážœáž·áž’áž¸áŸ”"
    return "áž€áž¶ážšáž”áž„áŸ’áž€áž¾ážážœáž¸ážŠáŸáž¢áž¼áž˜áž·áž“áž”áž¶áž“ážŸáž˜áŸ’ážšáŸáž…áŸ” ážŸáž¼áž˜ážŸáž¶áž€áž˜áŸ’ážáž„áž‘áŸ€ážáŸ”"


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


SITE_PREFIX_RE = re.compile(
    r"^(ssstik[._\-\s]*io|snaptik|tikmate|savetik|musicaldown|tikwm|ttdown|tiktok)[._\-\s]*",
    re.I,
)


def clean_name(name):
    out = str(name or "")
    for _ in range(3):
        new = SITE_PREFIX_RE.sub("", out)
        if new == out:
            break
        out = new
    return out.strip() or "Video"


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
        raise RuntimeError("FFmpeg áž”ážšáž¶áž‡áŸáž™:\n" + err)
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
        raise UserError("áž˜áž·áž“áž¢áž¶áž…áž¢áž¶áž“áž¯áž€ážŸáž¶ážšáž“áŸáŸ‡áž”áž¶áž“áž‘áŸáŸ”")
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
def load_font_bytes(choice=DEFAULT_FONT):
    """áž‘áž¶áž‰ Font ážŠáŸ‚áž›áž”áž¶áž“áž‡áŸ’ážšáž¾ážŸáž˜áž€áž˜áž»áž“ ážšáž½áž…áž‘áž¶áž‰ Font áž”áž˜áŸ’ážšáž»áž„ (áž”áŸ’ážšáž¾áž–áŸáž› Font ážŠáŸ‚áž›áž‡áŸ’ážšáž¾ážŸáž˜áž·áž“ážŠáŸ†ážŽáž¾ážšáž€áž¶ážš)"""
    if choice not in FONT_CHOICES:
        choice = DEFAULT_FONT
    order = [choice] + [k for k in FONT_BACKUP if k != choice]
    out = []
    for key in order:
        filename, paths, default_name = FONT_CHOICES[key]
        data = None
        for path in paths:
            try:
                request = urllib.request.Request(GF + path, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=25) as response:
                    got = response.read()
                if len(got) >= 1000:
                    data = got
                    break
            except Exception:
                continue
        if data:
            out.append((filename, data, default_name))
        if len(out) >= 3:
            break
    if not out:
        raise RuntimeError("áž‘áž¶áž‰áž™áž€ Font ážáŸ’áž˜áŸ‚ážšáž˜áž·áž“áž”áž¶áž“áŸ”")
    return out


def prepare_home_font(fonts_data):
    try:
        home_fonts = os.path.expanduser("~/.fonts")
        os.makedirs(home_fonts, exist_ok=True)
        for filename, data, _name in fonts_data:
            dst = os.path.join(home_fonts, filename)
            if not os.path.exists(dst):
                with open(dst, "wb") as f:
                    f.write(data)
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
    # Rebuild cache for fonts copied into this job's temporary folder.
    try:
        subprocess.run(["fc-cache", "-f", folder], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=15, check=False)
    except Exception:
        pass
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


def is_tiktok_url(url):
    try:
        return "tiktok.com" in urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return False


def download_tiktok(url, path, progress):
    try:
        import yt_dlp
    except Exception:
        raise UserError("áž˜áž·áž“áž‘áž¶áž“áŸ‹áž”áž¶áž“ážŠáŸ†áž¡áž¾áž„ yt-dlp áž‘áŸáŸ” ážŸáž¼áž˜áž”áž“áŸ’ážáŸ‚áž˜ yt-dlp áž€áŸ’áž“áž»áž„ requirements.txtáŸ”")
    limit = MAX_DOWNLOAD_MB * 1024 * 1024
    folder = os.path.dirname(path)
    out_tpl = os.path.join(folder, "tt_download.%(ext)s")

    def hook(d):
        try:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                if total:
                    progress.progress(min(1.0, d.get("downloaded_bytes", 0) / total))
        except Exception:
            pass

    opts = {
        "outtmpl": out_tpl,
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": limit,
        "socket_timeout": 30,
        "progress_hooks": [hook],
    }
    got = None
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            got = ydl.prepare_filename(info)
    except Exception:
        raise UserError("áž‘áž¶áž‰áž™áž€ážœáž¸ážŠáŸáž¢áž¼ TikTok áž˜áž·áž“áž”áž¶áž“áž‘áŸáŸ” ážŸáž¼áž˜áž–áž·áž“áž·ážáŸ’áž™ážáŸ†ážŽ áž¬ážŸáž¶áž€áž˜áŸ’ážáž„áž‘áŸ€ážáŸ”")
    if not got or not os.path.exists(got):
        import glob
        found = glob.glob(os.path.join(folder, "tt_download.*"))
        got = found[0] if found else None
    if not got or os.path.getsize(got) < 1000:
        raise UserError("áž‘áž¶áž‰áž™áž€ážœáž¸ážŠáŸáž¢áž¼ TikTok áž˜áž·áž“áž”áž¶áž“áž‘áŸáŸ”")
    shutil.move(got, path)
    progress.progress(1.0)


def download_video(url, path, progress):
    url = normalize_link(url)
    if is_tiktok_url(url):
        return download_tiktok(url, path, progress)
    limit = MAX_DOWNLOAD_MB * 1024 * 1024
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            ctype = (response.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype:
                raise UserError("ážáŸ†ážŽáž“áŸáŸ‡áž˜áž·áž“áž˜áŸ‚áž“áž‡áž¶ážœáž¸ážŠáŸáž¢áž¼áž•áŸ’áž‘áž¶áž›áŸ‹áž‘áŸáŸ”")
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
                        raise UserError(f"ážœáž¸ážŠáŸáž¢áž¼áž’áŸ†áž‡áž¶áž„ {MAX_DOWNLOAD_MB}MBáŸ”")
                    if total:
                        progress.progress(min(1.0, done / total))
    except UserError:
        raise
    except Exception:
        raise UserError("áž‘áž¶áž‰áž™áž€ážœáž¸ážŠáŸáž¢áž¼áž–áž¸ážáŸ†ážŽáž˜áž·áž“áž”áž¶áž“áž‘áŸáŸ”")
    if os.path.getsize(path) < 1000:
        raise UserError("áž‘áž¶áž‰áž™áž€ážœáž¸ážŠáŸáž¢áž¼áž˜áž·áž“áž”áž¶áž“áŸ”")
    progress.progress(1.0)


def extract_audio(video_path, audio_path, master_path):
    try:
        run_ffmpeg([
            "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", audio_path,
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac", master_path,
        ])
    except RuntimeError:
        raise UserError("áž˜áž·áž“áž¢áž¶áž…ážŠáž€ážŸáŸ†áž¡áŸáž„áž–áž¸ážœáž¸ážŠáŸáž¢áž¼áž“áŸáŸ‡áž”áž¶áž“áž‘áŸáŸ”")


def get_available_models(client):
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
    sentences = [fix_khmer(p) for p in re.split(r"(?<=[áŸ”.!?])\s+|\n+", text) if fix_khmer(p)]
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
    return items, "ážáž¶áž˜áž˜áŸ‰áŸ„áž„áž–áž¸ AI (áž€áŸ‚ážáž˜áŸ’ážšáž¹áž˜ážáž¶áž˜ážŸáŸ†áž¡áŸáž„)"


def write_ass(path, captions, font_family, font_size, outline_size, primary_color, width, height, alignment=2):
    # libass/fontconfig sometimes fails with family names containing spaces or
    # metadata aliases. Keep the selected font family explicit and text NFC.
    font_family = str(font_family or "Battambang").replace(",", " ").strip()
    if not font_family:
        font_family = "Battambang"
    play_res_y = 288
    play_res_x = max(100, int(round(play_res_y * width / max(1, height))))
    header = [
        "[Script Info]", "ScriptType: v4.00+",
        f"PlayResX: {play_res_x}", f"PlayResY: {play_res_y}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_family},{font_size},{primary_color},"
        f"&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,"
        f"{outline_size},1,{alignment},20,20,35,1", "",
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
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(header + events) + "\n")


class Reporter:
    def __init__(self, item):
        self.item = item
    def _check(self):
        if self.item.get("cancel"):
            raise UserError("áž”áž¶áž“áž”áŸ„áŸ‡áž”áž„áŸ‹ážŠáŸ„áž™áž¢áŸ’áž“áž€áž”áŸ’ážšáž¾áŸ”")
    def write(self, message):
        self._check()
        self.item["stage"] = message
        self.item["log"].append(message)
    def progress(self, value):
        self._check()
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
                status.write("áž”áŸ’ážšáž–áŸáž“áŸ’áž’ážšážœáž›áŸ‹áž”áž“áŸ’ážáž·áž… áž€áŸ†áž–áž»áž„ážŸáž¶áž€áž˜áŸ’ážáž„áž‘áŸ€áž...")
                dbg(status, f"[{model}] busy, wait {wait}s")
                time.sleep(wait)
                continue
            if quota and attempt < 1:
                status.write("áž”áŸ’ážšáž–áŸáž“áŸ’áž’ážšážœáž›áŸ‹áž”áž“áŸ’ážáž·áž… áž€áŸ†áž–áž»áž„ážŸáž¶áž€áž˜áŸ’ážáž„áž‘áŸ€áž...")
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
            "and calmly within its own time range: at most about 9 Khmer "
            "characters per second of that segment. Prefer concise, "
            "everyday spoken wording. "
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
            dbg(status, f"áž€áŸ†áž–áž»áž„ážŸáž¶áž€áž˜áŸ‰áž¼ážŠáŸ‚áž› {model}...")
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
                errors.append(f"{model}: áž˜áž·áž“áž˜áŸ‚áž“áž¢áž€áŸ’ážŸážšážáŸ’áž˜áŸ‚ážš")
                break
            if is_empty_json(raw):
                return [], model, []
            plain = fix_khmer(re.sub(r"[\[\]{}\"]", " ", raw))
            if plain and has_khmer(plain):
                return plain_to_segments(plain, clip_duration), model, errors
            errors.append(f"{model}: áž˜áž·áž“áž˜áž¶áž“áž¢ážáŸ’ážáž”áž‘")
            break
    if weak:
        return weak[0], weak[1], errors
    return [], None, errors


def transcribe(api_key, audio_path, duration, source_language, status, concise=False, speech=None):
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
    models = get_available_models(client)
    if not models:
        raise RuntimeError("API Key áž˜áž¾áž›áž˜áž·áž“ážƒáž¾áž‰áž˜áŸ‰áž¼ážŠáŸ‚áž›ážŽáž¶áž˜áž½áž™áž‘áŸáŸ” api key")
    dbg(status, "áž˜áŸ‰áž¼ážŠáŸ‚áž›ážŠáŸ‚áž›ážšáž€ážƒáž¾áž‰: " + ", ".join(models))
    chunks = plan_chunks(duration, speech or [])
    total = len(chunks)
    folder = os.path.dirname(audio_path)
    base = os.path.basename(audio_path)
    done_counter = {"n": 0}
    dbg(status, f"áž”áŸ‚áž„áž…áŸ‚áž€áž‡áž¶ {total} áž•áŸ’áž“áŸ‚áž€")
    def work(i, start, end):
        out_name = f"chunk_{i}.flac"
        run_ffmpeg(["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", base, "-c:a", "flac", out_name], cwd=folder)
        with open(os.path.join(folder, out_name), "rb") as f:
            data = f.read()
        if len(data) > 15 * 1024 * 1024:
            raise UserError("ážŸáŸ†áž¡áŸáž„áž’áŸ†áž–áŸáž€áŸ”")

        # Retry a failed/empty chunk before declaring part of the video lost.
        segs, model, errors = [], None, []
        last_error = None
        for attempt in range(3):
            try:
                segs, model, errors = transcribe_clip(
                    client, models, data, "audio/flac", end - start,
                    source_language, concise, status
                )
                if segs:
                    break
                # Empty result with explicit model errors may be a temporary
                # provider/model failure; retry. A clean empty result means silence.
                if not errors:
                    break
                last_error = " | ".join(errors[:2])
            except Exception as e:
                last_error = str(e)
            if attempt < 2:
                wait = 2 * (attempt + 1)
                status.write(f"áž•áŸ’áž“áŸ‚áž€ {i + 1} áž”áž€áž˜áž·áž“áž”áž¶áž“ áž€áŸ†áž–áž»áž„ážŸáž¶áž€áž˜áŸ’ážŠáž„áž‘áŸ€áž ({attempt + 2}/3)...")
                time.sleep(wait)
        if not segs and last_error:
            errors = list(errors or []) + [f"chunk {i + 1}: {last_error}"]
        done_counter["n"] += 1
        if total > 1:
            status.write(f"áŸ£/áŸ¤ áž€áŸ†áž–áž»áž„ážŸáŸ’ážáž¶áž”áŸ‹ áž“áž·áž„áž”áž€áž”áŸ’ážšáŸ‚... ({done_counter['n']}/{total})")
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
            elif errors and any(k in err.lower() for err in errors for k in fatal_keys):
                failed += 1
                fatal_errors.extend(errors)
            elif errors:
                # Chunk produced no captions after its retries: count it as a
                # failed part so the UI warning accurately reflects omissions.
                failed += 1
                fatal_errors.extend(errors)
    if not all_segments:
        if fatal_errors:
            raise RuntimeError("áž˜áŸ‰áž¼ážŠáŸ‚áž›áž‘áž¶áŸ†áž„áž¢ážŸáŸ‹áž”ážšáž¶áž‡áŸáž™áŸ”\n\n" + "\n\n".join(fatal_errors))
        raise UserError("ážšáž€áž˜áž·áž“ážƒáž¾áž‰ážŸáŸ†áž¡áŸáž„áž“áž·áž™áž¶áž™áž€áŸ’áž“áž»áž„ážœáž¸ážŠáŸáž¢áž¼áž“áŸáŸ‡áž‘áŸáŸ”")
    all_segments.sort(key=lambda x: x[0])
    main_model = Counter(used_models).most_common(1)[0][0]
    return all_segments, main_model, failed


def groq_request(api_key, audio_path, model, language):
    boundary = "----kac" + uuid.uuid4().hex
    fields = [
        ("model", model), ("response_format", "verbose_json"),
        ("temperature", "0"), ("timestamp_granularities[]", "segment"),
        ("timestamp_granularities[]", "word"),
    ]
    if language:
        fields.append(("language", language))
        # Whisper prompt helps keep names and language-specific writing stable.
        asr_hint = (
            "Transcribe the audio in its original language exactly as spoken. "
            "Do not translate it. Preserve names, short words, negations, and complete phrases. "
            "Use punctuation naturally. If speech is unclear, do not invent words."
        )
        fields.append(("prompt", asr_hint))
    else:
        fields.append(("prompt",
            "First identify the spoken language, then transcribe exactly in that language. "
            "Do not translate or paraphrase. Preserve names, negations, and complete phrases."))
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
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:500]
        raise RuntimeError(f"Groq HTTP {e.code}: {detail}")


def groq_transcribe(api_key, audio_path, language, status):
    last = None
    for model in GROQ_MODELS:
        for attempt in range(2):
            try:
                return groq_request(api_key, audio_path, model, language), model
            except RuntimeError as e:
                last = e
                text = str(e)
                if ("429" in text or "503" in text) and attempt == 0:
                    status.write("áž”áŸ’ážšáž–áŸáž“áŸ’áž’ážšážœáž›áŸ‹áž”áž“áŸ’ážáž·áž… áž€áŸ†áž–áž»áž„ážŸáž¶áž€áž˜áŸ’ážáž„áž‘áŸ€áž...")
                    time.sleep(12)
                    continue
                break
            except Exception as e:
                last = e
                break
    raise last or RuntimeError("Groq áž”ážšáž¶áž‡áŸáž™: áž˜áž·áž“ážŠáž¹áž„áž˜áž¼áž›áž áŸážáž»")


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
                time.sleep(3 * (attempt + 1))
                continue
            raise


def clean_translation(out):
    """Normalize Khmer translation; do not erase foreign words to fake a Khmer result."""
    out = str(out or "")
    out = CJK_RE.sub("", out)
    out = fix_khmer(out)
    out = re.sub(r"\s+([áŸ”.!?,áŸ–])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    # Reject English/source-language output so it can be retried instead of
    # silently deleting words and leaving an incomplete subtitle.
    if not out or not has_khmer(out) or re.search(r"[A-Za-z]", out):
        return None
    return out


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
        request = urllib.request.Request(GROQ_MODELS_URL, headers={"Authorization": f"Bearer {api_key}", "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        for m in data.get("data") or []:
            mid = str(m.get("id", ""))
            low = mid.lower()
            if not mid or m.get("active") is False:
                continue
            if any(x in low for x in ("whisper", "tts", "guard", "prompt", "orpheus")):
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


def groq_translate_chunk(api_key, texts):
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    models = groq_chat_models(api_key)
    good = _groq_chat_cache["good"]
    if good in models:
        models = [good] + [m for m in models if m != good]
    last = "áž˜áž·áž“áž˜áž¶áž“áž˜áŸ‰áž¼ážŠáŸ‚áž›"
    for model in models[:6]:
        body = json.dumps({
            "model": model, "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": (
                    "You are translating consecutive subtitle dialogue from a Chinese/English drama into "
                    "natural spoken Cambodian Khmer. The numbered source lines are in chronological order; "
                    "read them together as a short conversation so pronouns, threats, insults, and replies make "
                    "sense. Translate the intended meaning and emotional tone, NOT the source-language grammar "
                    "or word order. Avoid stiff calques and textbook Khmer. Convert idioms and figurative threats "
                    "into expressions a Cambodian viewer immediately understands. Example: 'Today I will grind "
                    "your bones to dust' should sound like a natural Khmer threat, e.g. 'ážáŸ’áž„áŸƒáž“áŸáŸ‡ ážáŸ’áž‰áž»áŸ†áž“áž¹áž„áž€áž˜áŸ’áž‘áŸáž… "
                    "áž†áŸ’áž¢áž¹áž„áž¢áŸ’áž“áž€áž²áŸ’áž™áž˜áŸ‰ážŠáŸ’áž‹'â€”not a word-by-word rendering. Keep lines brief and speakable for dubbing, "
                    "but do not remove plot information, negation, names, relationships, or key details. "
                    "Write the ENTIRE output in Khmer script only: never leave English, Chinese, or other "
                    "source-language words in the translation. Transliterate character names and places into "
                    "Khmer when needed; do not keep Latin spellings in parentheses. Keep only numerals if "
                    "they are necessary. Do not add meaning, summarize, or combine lines. If a source line is "
                    "fragmentary, translate it as a fragment and use neighboring lines to infer its sense. "
                    "Return only valid JSON with key 'translations', exactly one Khmer-script string per "
                    "numbered input line, same order."
                )},
                {"role": "user", "content": numbered},
            ],
        }).encode("utf-8")
        for attempt in range(2):
            request = urllib.request.Request(GROQ_CHAT_URL, data=body, method="POST", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(request, timeout=60) as r:
                    data = json.loads(r.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
                items = json.loads(content).get("translations") or []
                if len(items) == len(texts):
                    _groq_chat_cache["good"] = model
                    return [clean_translation(x) for x in items]
                last = f"{model}: áž…áŸ†áž“áž½áž“áž”áž“áŸ’áž‘áž¶ážáŸ‹áž˜áž·áž“ážáŸ’ážšáž¼ážœáž‚áŸ’áž“áž¶"
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


def translate_texts(texts, groq_key=None):
    """
    Translate in small contextual batches with the AI translator first.
    Google Translate is a fallback, not the primary quality path.
    Each source subtitle remains one output subtitle in the same order.
    """
    errors = []
    outs = [None] * len(texts)

    # AI-first: short batches preserve nearby context while limiting malformed responses.
    if groq_key:
        for k in range(0, len(texts), 5):
            idxs = list(range(k, min(k + 5, len(texts))))
            try:
                res = groq_translate_chunk(
                    groq_key, [str(texts[i]).strip() for i in idxs]
                )
                if len(res) == len(idxs):
                    for i, translated in zip(idxs, res):
                        cleaned = clean_translation(translated)
                        if cleaned:
                            outs[i] = cleaned
            except Exception as e:
                errors.append(f"groq-batch: {e}"[:200])
            time.sleep(0.4)

        # Isolate failed AI batches, one subtitle at a time.
        missing = [i for i, value in enumerate(outs) if not value]
        for i in missing:
            try:
                res = groq_translate_chunk(groq_key, [str(texts[i]).strip()])
                if res and res[0]:
                    cleaned = clean_translation(res[0])
                    if cleaned:
                        outs[i] = cleaned
            except Exception as e:
                errors.append(f"groq-single: {e}"[:200])
            time.sleep(0.3)

    # Google fallback only for lines the AI could not translate.
    missing = [i for i, value in enumerate(outs) if not value]
    for i in missing:
        try:
            translated = google_translate_request(str(texts[i]).replace("\\n", " ").strip(), retries=3)
            cleaned = clean_translation(translated)
            if cleaned:
                outs[i] = cleaned
        except Exception as e:
            errors.append(f"google-single: {e}"[:200])
        time.sleep(0.2)

    # Final AI retry for lines Google returned in the wrong language or failed.
    missing = [i for i, value in enumerate(outs) if not value]
    for i in missing:
        if not groq_key:
            break
        try:
            res = groq_translate_chunk(groq_key, [str(texts[i]).strip()])
            cleaned = clean_translation(res[0]) if res else None
            if cleaned:
                outs[i] = cleaned
        except Exception as e:
            errors.append(f"groq-final-retry: {e}"[:200])
        time.sleep(0.25)

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
        status.write(f"áŸ£/áŸ¤ áž€áŸ†áž–áž»áž„ážŸáŸ’ážáž¶áž”áŸ‹áž—áž¶ážŸáž¶ážáŸ’áž˜áŸ‚ážš... ({i + 1}/{len(chunks)})")
        wait = 3.2 - (time.time() - t0)
        if wait > 0:
            time.sleep(wait)
    out.sort(key=lambda x: x[0])
    return out


GSPEECH_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"


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
            status.write(f"áŸ£/áŸ¤ áž€áŸ†áž–áž»áž„ážŸáŸ’ážáž¶áž”áŸ‹áž—áž¶ážŸáž¶ážáŸ’áž˜áŸ‚ážš... ({counter['n']}/{len(todo)})")

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
            raise RuntimeError("Google Speech áž”ážšáž¶áž‡áŸáž™")
        return []
    out.sort(key=lambda x: x[0])
    return out


def transcribe_free(groq_key, audio_path, duration, source_language, status, speech=None, khmer_ok=True):
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
    words = []
    for w in data.get("words") or []:
        try:
            words.append((float(w.get("start", 0)), float(w.get("end", 0))))
        except Exception:
            continue

    def refine(s0, e0):
        ws = [(a, b) for a, b in words if s0 - 0.05 <= (a + b) / 2 <= e0 + 0.05]
        if not ws:
            return s0, e0
        return max(0.0, min(a for a, _ in ws)), max(b for _, b in ws)

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
        s, e = refine(s, e)
        s = min(max(0.0, s), duration)
        e = min(max(e, s + 0.4), duration + 0.5)
        keep.append((s, e, text))
    if not keep:
        raise UserError("ážšáž€áž˜áž·áž“ážƒáž¾áž‰ážŸáŸ†áž¡áŸáž„áž“áž·áž™áž¶áž™áž€áŸ’áž“áž»áž„ážœáž¸ážŠáŸáž¢áž¼áž“áŸáŸ‡áž‘áŸáŸ”")
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
        status.write("áŸ£/áŸ¤ áž€áŸ†áž–áž»áž„áž”áž€áž”áŸ’ážšáŸ‚áž‡áž¶áž—áž¶ážŸáž¶ážáŸ’áž˜áŸ‚ážš...")
        outs, errs = translate_texts([t for _, _, t in keep], groq_key)
        segs = []
        for (s, e, _), out in zip(keep, outs):
            if out:
                segs.append((s, e, out))
            else:
                failed += 1
        if not segs or failed > len(keep) * 0.5:
            reason = " | ".join(errs[:2]) or "áž˜áž·áž“ážŸáŸ’áž‚áž¶áž›áŸ‹áž˜áž¼áž›áž áŸážáž»"
            raise RuntimeError("áž€áž¶ážšáž”áž€áž”áŸ’ážšáŸ‚áž”ážšáž¶áž‡áŸáž™áŸ” " f"(ážŸáŸ’ážáž¶áž”áŸ‹áž”áž¶áž“ {len(keep)} ážƒáŸ’áž›áž¶ áž”áž€áž”áž¶áž“ {len(segs)}) " f"áž˜áž¼áž›áž áŸážáž»: {reason}")
    if not segs:
        raise UserError("ážšáž€áž˜áž·áž“ážƒáž¾áž‰áž¢ážáŸ’ážáž”áž‘ážáŸ’áž˜áŸ‚ážšáž€áŸ’áž“áž»áž„ážŸáŸ†áž¡áŸáž„áž“áŸáŸ‡áž‘áŸáŸ”")
    segs.sort(key=lambda x: x[0])
    return segs, f"Groq {model} + Translate", failed


def tts_segment(text, voice, path, prosody=None):
    async def _go(p):
        kw = {}
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
    limit = max(6, int(max_seconds * 9))
    try:
        response = client.models.generate_content(
            model=model,
            contents=(
                f"Shorten this Khmer sentence to at most {limit} "
                "characters. Keep the meaning. Use natural everyday "
                "spoken Khmer. Khmer script only. "
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
        info["summary"] = "ážœáž¶ážŸáŸ‹áž€áž˜áŸ’ážšáž·ážážŸáŸ†áž¡áŸáž„áž˜áž·áž“áž”áž¶áž“ áž”áŸ’ážšáž¾ážŸáŸ†áž¡áŸáž„ážŠáŸ‚áž›áž”áž¶áž“áž‡áŸ’ážšáž¾ážŸ"
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
            info["summary"] = f"áž€áž˜áŸ’ážšáž·ážážŸáŸ†áž¡áŸáž„ ~{int(med)}Hz áž˜áž·áž“áž…áŸ’áž”áž¶ážŸáŸ‹ áž”áŸ’ážšáž¾ážŸáŸ†áž¡áŸáž„ážŠáŸ‚áž›áž”áž¶áž“áž‡áŸ’ážšáž¾ážŸ"
    names = {"M": "áž”áŸ’ážšáž»ážŸ", "F": "ážŸáŸ’ážšáž¸"}
    if not two:
        med = float(np.median(hz))
        if not info["summary"]:
            info["summary"] = f"ážŸáŸ’áž‚áž¶áž›áŸ‹ážƒáž¾áž‰áž¢áŸ’áž“áž€áž“áž·áž™áž¶áž™ áŸ¡ áž“áž¶áž€áŸ‹áŸ– {names[single]} (~{int(med)}Hz)"
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
        "ážŸáŸ’áž‚áž¶áž›áŸ‹ážƒáž¾áž‰áž¢áŸ’áž“áž€áž“áž·áž™áž¶áž™ áŸ¢ áž“áž¶áž€áŸ‹áŸ– "
        f"áž”áŸ’ážšáž»ážŸ (~{int(hz_m)}Hz) áž“áž·áž„ážŸáŸ’ážšáž¸ (~{int(hz_f)}Hz) "
        f"áž”áŸ’ážáž¼ážšáž¢áŸ’áž“áž€áž“áž·áž™áž¶áž™ {len(runs) - 1} ážŠáž„"
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
        mark = "â™‚" if v == VOICE_MALE else "â™€"
        lines.append(f"{mark} {int(hz) if hz else '?'}Hz  {t}")
    return dub, lines, info, runs


# ---- áž€áŸ‚ážáž˜áŸ’ážšáž¹áž˜ážŸáŸ†áž¡áŸáž„áž±áŸ’áž™áž‡áž·ážážŸáŸ†áž¡áŸáž„ážŠáž¾áž˜ ážáŸ‚ážáž·áž…ážáž½áž…áž”áŸ‰áž»ážŽáŸ’ážŽáŸ„áŸ‡ ážŠáž¾áž˜áŸ’áž”áž¸áž€áž»áŸ†áž±áŸ’áž™ážŸáŸ’ážáž¶áž”áŸ‹áž˜áž·áž“áž’áž˜áŸ’áž˜ážáž¶ ----
MATCH_MIN = 0.92
MATCH_MAX = 1.10


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

# áž¢áž¶ážšáž˜áŸ’áž˜ážŽáŸážŸáŸ’ážšáž¶áž›áŸ— ážŠáž¾áž˜áŸ’áž”áž¸áž±áŸ’áž™ážŸáŸ†áž¡áŸáž„ AI áž“áŸ…ážáŸ‚ážŸáŸ’ážáž¶áž”áŸ‹áž‘áŸ…áž’áž˜áŸ’áž˜ážáž¶ (rate %, pitch Hz, volume %)
EMO_PRESETS = {
    "neutral": (0, 0, 0), "happy": (3, 4, 2), "excited": (6, 6, 5),
    "angry": (4, 2, 8), "sad": (-5, -4, -6), "fear": (4, 6, -2),
    "whisper": (-3, -2, -15),
}

EMO_NAMES = {
    "neutral": "ðŸ˜ áž’áž˜áŸ’áž˜ážáž¶", "happy": "ðŸ˜Š ážŸáž”áŸ’áž”áž¶áž™", "excited": "ðŸ¤© ážšáŸ†áž—áž¾áž”",
    "angry": "ðŸ˜  ážáž¹áž„", "sad": "ðŸ˜¢ áž€áŸ’ážšáŸ€áž˜áž€áŸ’ážšáŸ†", "fear": "ðŸ˜¨ áž—áŸáž™",
    "whisper": "ðŸ¤« ážáŸ’ážŸáž¹áž”",
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
    last = "áž˜áž·áž“áž˜áž¶áž“áž˜áŸ‰áž¼ážŠáŸ‚áž›"
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
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as r:
                    data = json.loads(r.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
                items = json.loads(content).get("emotions") or []
                if len(items) == len(texts):
                    _groq_chat_cache["good"] = model
                    return [norm_emotion(x) for x in items]
                last = f"{model}: áž…áŸ†áž“áž½áž“áž˜áž·áž“ážáŸ’ážšáž¼ážœáž‚áŸ’áž“áž¶"
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
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
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
        return text_label, max(0.3, min(1.0, 0.6 + 0.3 * arousal))
    if text_label in EMO_LOW:
        return text_label, max(0.3, min(1.0, 0.6 - 0.3 * arousal))
    if arousal > 0.5:
        return "excited", min(0.8, 0.4 + (arousal - 0.5) * 0.6)
    if arousal < -0.5:
        return "sad", min(0.8, 0.4 + (-arousal - 0.5) * 0.6)
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
    source = ("ážáž¶áž˜áž¢ážáŸ’ážáž”áž‘ + ážŸáŸ†áž¡áŸáž„ážŠáž¾áž˜" if labels and have_audio else "ážáž¶áž˜áž¢ážáŸ’ážáž”áž‘ážáŸ‚áž”áŸ‰áž»ážŽáŸ’ážŽáŸ„áŸ‡" if labels else "ážáž¶áž˜ážŸáŸ†áž¡áŸáž„ážŠáž¾áž˜ážáŸ‚áž”áŸ‰áž»ážŽáŸ’ážŽáŸ„áŸ‡" if have_audio else "áž˜áž·áž“áž˜áž¶áž“áž‘áž·áž“áŸ’áž“áž“áŸáž™")
    summary = (f"ðŸŽ­ áž¢áž¶ážšáž˜áŸ’áž˜ážŽáŸ ({source})áŸ– " + " Â· ".join(f"{EMO_NAMES[k]} {counts[k]}" for k in EMO_LABELS if counts.get(k)))
    lines = [summary]
    shown = 0
    for (lab, inten), text in zip(result, texts):
        if lab == "neutral":
            continue
        lines.append(f"{EMO_NAMES[lab]} Ã—{inten:.1f}  {text}")
        shown += 1
        if shown >= 40:
            break
    return result, lines


def emotion_prosody(label, intensity, use_pitch=True):
    rate, pitch, vol = EMO_PRESETS.get(label, (0, 0, 0))
    k = max(0.0, float(intensity))
    rate = int(max(-10, min(10, rate * k)))
    pitch = int(max(-8, min(8, pitch * k))) if use_pitch else 0
    vol = int(max(-20, min(15, vol * k)))
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
                raise RuntimeError("ElevenLabs áž†áŸ’áž›áž¾áž™ážáž”áž‘áž‘áŸ")
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
    """ážœáž¶ážŸáŸ‹ 'áž–ážŽáŸŒážŸáŸ†áž¡áŸáž„' áž‡áž¶áž€áž˜áŸ’ážšáž·áž dB áž€áŸ’áž“áž»áž„áž…áž“áŸ’áž›áŸ„áŸ‡áž”áŸ’ážšáŸáž€áž„áŸ‹ áŸ© (áž¥ážáž‚áž·ážážáŸ’áž›áŸƒ áž‚áŸ’áž˜áž¶áž“ API)"""
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


def eq_filters(ref, tts, limit=4.0):
    if not ref or not tts:
        return ""
    import numpy as np
    r = np.array(ref, dtype=np.float64)
    t = np.array(tts, dtype=np.float64)
    d = np.clip((r - r.mean()) - (t - t.mean()), -limit, limit)
    parts = [f"equalizer=f={c}:t=q:w=1.0:g={g:.1f}" for c, g in zip(EQ_CENTERS, d) if abs(g) >= 0.8]
    return ",".join(parts)


def merge_for_dub(segments, max_chars=80, max_gap=0.6, max_len=8.0):
    """áž”áž‰áŸ’áž…áž¼áž›ážƒáŸ’áž›áž¶ážáŸ’áž›áž¸áŸ—áž‡áž¶áž”áŸ‹áž‚áŸ’áž“áž¶áž‡áž¶áž”áŸ’ážšáž™áŸ„áž‚ážœáŸ‚áž„ ážŠáž¾áž˜áŸ’áž”áž¸áž±áŸ’áž™ážŸáŸ†áž¡áŸáž„áž¢áž¶áž“ážšáž›áž¼áž“ážŠáž¼áž…áž˜áž“áž»ážŸáŸ’ážŸáž“áž·áž™áž¶áž™ áž˜áž·áž“áž€áž¶ážáŸ‹áŸ—"""
    out = []
    for s, e, t in segments:
        if out:
            ps, pe, pt = out[-1]
            if s - pe <= max_gap and len(pt) + len(t) + 1 <= max_chars and e - ps <= max_len:
                out[-1] = (ps, max(pe, e), fix_khmer(pt + " " + t))
                continue
        out.append((s, e, t))
    return out


def tts_retry(text, voice, path, prosody=None, tries=3):
    last = None
    for k in range(tries):
        try:
            tts_segment(text, voice, path, prosody)
            if os.path.exists(path) and os.path.getsize(path) > 200:
                return True
        except Exception as e:
            last = e
        time.sleep(0.8 * (k + 1))
    return False


def shorten_groq(api_key, text, max_seconds):
    limit = max(6, int(max_seconds * 9))
    try:
        models = groq_chat_models(api_key)[:3]
    except Exception:
        return text
    for model in models:
        try:
            body = json.dumps({
                "model": model, "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": f"Shorten the Khmer sentence to at most {limit} characters. Keep the meaning. Use natural everyday spoken Khmer. Khmer script only. Return only the sentence."},
                    {"role": "user", "content": text},
                ],
            }).encode("utf-8")
            request = urllib.request.Request(
                GROQ_CHAT_URL, data=body, method="POST",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(request, timeout=40) as r:
                data = json.loads(r.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
            out = clean_translation(content)
            if out and has_khmer(out) and len(out) < len(text):
                return out
        except Exception:
            continue
    return text


BG_VOLUME = 0.04

# áž›áŸ’áž”áž¿áž“áž¢áž¶áž“áž’áž˜áŸ’áž˜ážáž¶áŸ– áž˜áž·áž“áž±áŸ’áž™áž›áž¿áž“áž–áŸáž€ áž¬áž™ážºážáž–áŸáž€
SPEED_MIN = 0.95
SPEED_MAX = 1.4


def make_dub(folder, segments, voice, duration, keep_bg, client, model,
             seg_voices=None, targets=None, notes=None, emotions=None, groq_key=None,
             clone_voice=None, eleven_key=None, ref_bands=None, base_rate=0):
    inputs, filters = [], []
    n = 0
    if keep_bg:
        inputs += ["-i", "audio.mp3"]
        filters.append(f"[0:a]volume={BG_VOLUME}[bg]")
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
    if base_rate:
        for i in range(n_seg):
            p = dict(pros[i] or {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"})
            r = int(p["rate"].replace("%", "")) + int(base_rate)
            p["rate"] = f"{max(-50, min(50, r)):+d}%"
            pros[i] = p

    clone_stats = {"ok": 0, "fail": 0, "err": ""}

    def gen(i):
        s_, e_, t_ = segments[i]
        next_s_ = segments[i + 1][0] if i + 1 < n_seg else duration
        # áž‘áž»áž€áž–áŸáž›áž±áŸ’áž™áž¢áž¶áž“áž”áž¶áž“áž™áž¼ážšáž‡áž¶áž„áž˜áž»áž“ ážŠáž¾áž˜áŸ’áž”áž¸áž€áž»áŸ†áž…áž¶áŸ†áž”áž¶áž…áŸ‹áž”áž„áŸ’áž€áž¾áž“áž›áŸ’áž”áž¿áž“
        slot0 = max(0.8, min(next_s_ - 0.05, e_ + 0.8) - s_)
        path_ = os.path.join(folder, f"tts_{i}.mp3")
        try:
            if not tts_retry(t_, voices_[i], path_, pros[i]):
                return None
            d_, _, _ = probe_media(path_)
            # Preserve the complete Khmer sentence. Timing is fitted later with
            # FFmpeg atempo (maximum SPEED_MAX=1.4), rather than rewriting/omitting words.
            # If the speech is much longer than its slot, keep it intact and let
            # the placement planner use the bounded playback speed.
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
            notes.append("ðŸŽš áž•áŸ’áž‚áž¼áž•áŸ’áž‚áž„áž–ážŽáŸŒážŸáŸ†áž¡áŸáž„ážŸáŸ’ážšážŠáŸ€áž„ážŸáŸ†áž¡áŸáž„áž‚áŸ†ážšáž¼")
    if notes is not None and clone_voice:
        notes.append(f"ðŸ§‘â€ðŸŽ¤ áž€áŸ’áž›áž¼áž“ážŸáŸ†áž¡áŸáž„áž”áž¶áž“ {clone_stats['ok']}/{n_seg} ážƒáŸ’áž›áž¶"
                     + (f" (áž”ážšáž¶áž‡áŸáž™: {clone_stats['err']})" if clone_stats["fail"] else ""))
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
        start = max(s, cursor)
        if start >= duration - 0.3:
            break
        slot = max(0.8, min(next_s - 0.05, e + 0.5) - start)
        # áž›áŸ’áž”áž¿áž“áž‡áž·ážáž’áž˜áŸ’áž˜ážáž¶ (áŸ¡.áŸ ) áž”áž¾ážœáŸ‚áž„áž–áŸáž€áž‘áž¾áž”áž”áž„áŸ’áž€áž¾áž“áž”áž“áŸ’ážáž·áž… áž˜áž·áž“áž›áž¾ážŸáž€áŸ†ážŽážáŸ‹
        speed = min(SPEED_MAX, max(SPEED_MIN, d / slot))
        cursor = start + d / speed + 0.12
        target = targets[i] if (targets is not None and i < len(targets) and targets[i]) else None
        plan.append({"name": f"tts_{i}.mp3", "start": start, "speed": speed,
                     "voice": voices_[i], "f0": f0 if target else None, "target": target,
                     "eq": voice_eq.get(voices_[i], "")})
    if notes is not None and skipped:
        notes.append(f"âš ï¸ áž˜áž·áž“áž¢áž¶áž…áž”áž„áŸ’áž€áž¾ážážŸáŸ†áž¡áŸáž„ {skipped} ážƒáŸ’áž›áž¶")
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
            if abs(ratio - 1.0) < 0.04:
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
        chain = "silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB," + chain
        if p.get("eq"):
            chain += "," + p["eq"]
        filters.append(f"[{n}:a]{chain},adelay={delay}:all=1[a{n}]")
        n += 1
    if notes is not None:
        for v, (ratios, tgts) in stats.items():
            who = "áž”áŸ’ážšáž»ážŸ" if v == VOICE_MALE else "ážŸáŸ’ážšáž¸"
            notes.append(f"ðŸ§¬ ážŸáŸ†áž¡áŸáž„ AI {who}áŸ– ~{int(base[v])}Hz â†’ " f"ážŸáŸ†áž¡áŸáž„ážŠáž¾áž˜ ~{int(statistics.median(tgts))}Hz " f"(áž€áŸ‚ Ã—{statistics.mean(ratios):.2f})")
    labels = "[bg]" if keep_bg else ""
    labels += "".join(f"[a{k}]" for k in range(first_voice, n))
    limiter = ",alimiter=limit=0.95" if emotions is not None else ""
    fc = (";".join(filters) + f";{labels}amix=inputs={n}:dropout_transition=0," f"volume={n}{limiter}[out]")
    run_ffmpeg(inputs + ["-filter_complex", fc, "-map", "[out]", "-t", f"{duration:.2f}", "dub.wav"], cwd=folder)
    return os.path.exists(os.path.join(folder, "dub.wav"))


def build_video_filter(max_side, subs=True):
    ass = "ass=filename=captions.ass:fontsdir=."
    if max_side and max_side > 0:
        scale = (f"scale=w='if(gt(iw,ih),-2,min({max_side},iw))':" f"h='if(gt(iw,ih),min({max_side},ih),-2)'")
        return f"{scale},{ass},format=yuv420p" if subs else f"{scale},format=yuv420p"
    return f"{ass},format=yuv420p" if subs else "format=yuv420p"


def render_with_fonts(folder, fonts, captions, font_size, outline_size,
                      color, vid_w, vid_h, quality, status, dub=False, alignment=2, subs=True):
    ass_path = os.path.join(folder, "captions.ass")
    output_path = os.path.join(folder, "output.mp4")
    max_side, crf, preset = quality
    conf_env = make_fontconfig_env(folder)
    plan = [(0, False), (0, True)]
    plan += [(i, True) for i in range(1, len(fonts))]
    if not subs:
        plan = [(0, False)]
    attempts = []
    have_output = False
    best = None
    for font_index, use_conf in plan:
        font_path, default_name = fonts[font_index]
        family = get_font_family(font_path, default_name)
        keys = [family.lower(), default_name.lower()]
        if subs:
            write_ass(ass_path, captions, family, font_size, outline_size, color, vid_w, vid_h, alignment)
        args = ["-i", "input.mp4"]
        if dub:
            args += ["-i", "dub.wav"]
        args += ["-vf", build_video_filter(max_side, subs)]
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
        ok = font_was_used(log, keys) if subs else True
        attempts.append(f"{family} conf={use_conf}: ok={ok}")
        have_output = True
        best = (family, log)
        if ok:
            break
        dbg(status, f"Font {family} áž˜áž·áž“ážáŸ’ážšáž¼ážœáž”áž¶áž“áž”áŸ’ážšáž¾ áž€áŸ†áž–áž»áž„ážŸáž¶áž€ážœáž·áž’áž¸áž•áŸ’ážŸáŸáž„...")
    if not have_output:
        raise RuntimeError("Render áž˜áž·áž“áž”áž¶áž“áŸ”\n" + "\n".join(attempts))
    with open(output_path, "rb") as f:
        data = f.read()
    return data, best[0], best[1], attempts


def new_item(name, path=None, url=None):
    return {
        "name": name, "path": path, "url": url, "state": "queued",
        "stage": "áž€áŸ’áž“áž»áž„áž‡áž½ážšážšáž„áŸ‹áž…áž¶áŸ†...", "pct": 0.0, "warn": [], "log": [],
        "video": None, "captions": [], "voice_lines": [], "error": None,
        "raw_error": "", "debug": {}, "t0": None, "elapsed": None,
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
    return "áž¥ážáž‚áž·ážážáŸ’áž›áŸƒ (Groq)" if engine == "free" else "Gemini"


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
                rep.write("áž€áŸ†áž–áž»áž„áž‘áž¶áž‰áž™áž€ážœáž¸ážŠáŸáž¢áž¼...")
                download_video(item["url"], source, rep)
            item["pct"] = 0.12
            rep.write("áŸ¡/áŸ¤ áž€áŸ†áž–áž»áž„ážšáŸ€áž”áž…áŸ†...")
            fonts = install_fonts(folder, fonts_data)
            _want = settings.get("font_choice", DEFAULT_FONT)
            if settings.get("subs_on", True) and _want in FONT_CHOICES and fonts_data[0][2] != FONT_CHOICES[_want][2]:
                item["warn"].append(f"áž‘áž¶áž‰áž™áž€ Font Â«{_want}Â» áž˜áž·áž“áž”áž¶áž“ áž”áŸ’ážšáž¾ Font ážŸáŸ’ážáž„áŸ‹ážŠáž¶ážšáž‡áŸ†áž“áž½ážŸáŸ”")
            item["pct"] = 0.18
            rep.write("áŸ¢/áŸ¤ áž€áŸ†áž–áž»áž„ážŠáž€ážŸáŸ†áž¡áŸáž„...")
            extract_audio(source, audio_path, master_path)
            duration, vid_w, vid_h = probe_media(source)
            if duration > MAX_DURATION_MIN * 60:
                raise UserError(f"ážœáž¸ážŠáŸáž¢áž¼ážœáŸ‚áž„áž–áŸáž€áŸ” ážŸáž¼áž˜áž”áŸ’ážšáž¾ážœáž¸ážŠáŸáž¢áž¼ážáŸ’áž›áž¸áž‡áž¶áž„ {MAX_DURATION_MIN} áž“áž¶áž‘áž¸áŸ”")
            speech = detect_speech(master_path, duration)
            item["pct"] = 0.25
            rep.write("áŸ£/áŸ¤ áž€áŸ†áž–áž»áž„ážŸáŸ’ážáž¶áž”áŸ‹ áž“áž·áž„áž”áž€áž”áŸ’ážšáŸ‚áž‡áž¶áž—áž¶ážŸáž¶ážáŸ’áž˜áŸ‚ážš...")
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
                        segments, used_model, failed_chunks = transcribe_free(settings["groq_key"], audio_path, duration, settings["language"], rep, speech=speech)
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
                        item["warn"].append("áž˜áŸ‰áž¶ážŸáŸŠáž¸áž“áž‘áž¸áž˜áž½áž™áž˜áž¶áž“áž”áž‰áŸ’áž áž¶ áž€áž˜áŸ’áž˜ážœáž·áž’áž¸áž”áž¶áž“áž”áŸ’ážáž¼ážšáž‘áŸ…áž˜áŸ‰áž¶ážŸáŸŠáž¸áž“áž”áž˜áŸ’ážšáž»áž„ážŠáŸ„áž™ážŸáŸ’ážœáŸáž™áž”áŸ’ážšážœážáŸ’ážáž·áŸ”" f"\n\náž˜áž¼áž›áž áŸážáž» â†’ {reason}")
                        rep.write("áž€áŸ†áž–áž»áž„áž”áŸ’ážáž¼ážšáž‘áŸ…áž˜áŸ‰áž¶ážŸáŸŠáž¸áž“áž”áž˜áŸ’ážšáž»áž„...")
            if segments is None:
                raise UserError("áž˜áŸ‰áž¶ážŸáŸŠáž¸áž“áž”áž€áž”áŸ’ážšáŸ‚áž‘áž¶áŸ†áž„áž¢ážŸáŸ‹áž”ážšáž¶áž‡áŸáž™áŸ”\n\n" + "\n\n".join(engine_errors))
            # Suppress the misleading warning when the video produced usable
            # captions. Empty/silent chunks may be counted by the transcription
            # backend even though the completed result is valid.
            item["pct"] = 0.55
            segments = snap_segments(segments, speech, duration)
            captions, sync_mode = build_captions(segments, duration)
            if not captions:
                raise UserError("ážšáž€áž˜áž·áž“ážƒáž¾áž‰ážŸáŸ†áž¡áŸáž„áž“áž·áž™áž¶áž™áž€áŸ’áž“áž»áž„ážœáž¸ážŠáŸáž¢áž¼áž“áŸáŸ‡áž‘áŸáŸ”")
            dub_ok = False
            if settings["dub_on"]:
                item["pct"] = 0.6
                rep.write("ðŸŽ™ áž€áŸ†áž–áž»áž„áž”áž„áŸ’áž€áž¾ážážŸáŸ†áž¡áŸáž„ážáŸ’áž˜áŸ‚ážš...")
                try:
                    client = (genai.Client(api_key=settings["gemini_key"]) if used_engine == "gemini" else None)
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
                            rep.write("ðŸ” áž€áŸ†áž–áž»áž„ážœáž·áž—áž¶áž‚ážŸáŸ†áž¡áŸáž„áž¢áŸ’áž“áž€áž“áž·áž™áž¶áž™ážŠáž¾áž˜...")
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
                            item["warn"].append("ážœáž·áž—áž¶áž‚ážŸáŸ†áž¡áŸáž„áž¢áŸ’áž“áž€áž“áž·áž™áž¶áž™áž˜áž·áž“áž”áž¶áž“ áž”áŸ’ážšáž¾ážŸáŸ†áž¡áŸáž„ážáŸ‚áž˜áž½áž™ážáž¶áž˜ážŠáŸ‚áž›áž”áž¶áž“áž‡áŸ’ážšáž¾ážŸáŸ”")
                    if settings["emotion"]:
                        try:
                            rep.write("ðŸŽ­ áž€áŸ†áž–áž»áž„ážœáž·áž—áž¶áž‚áž¢áž¶ážšáž˜áŸ’áž˜ážŽáŸ...")
                            emotions, emo_lines = plan_emotions(dub_segments, seg_voices, pitch_inf, runs_, settings["groq_key"], settings["gemini_key"])
                            voice_notes = voice_notes + emo_lines
                        except Exception:
                            emotions = None
                            item["warn"].append("ážœáž·áž—áž¶áž‚áž¢áž¶ážšáž˜áŸ’áž˜ážŽáŸáž˜áž·áž“áž”áž¶áž“ áž”áŸ’ážšáž¾ážŸáŸ†áž¡áŸáž„áž’áž˜áŸ’áž˜ážáž¶áŸ”")
                    clone_voice = None
                    if settings.get("clone_sample") and settings.get("eleven_key"):
                        try:
                            rep.write("ðŸ§‘â€ðŸŽ¤ áž€áŸ†áž–áž»áž„áž€áŸ’áž›áž¼áž“ážŸáŸ†áž¡áŸáž„áž‚áŸ†ážšáž¼...")
                            clone_voice = eleven_add_voice(settings["eleven_key"], settings["clone_sample"])
                            targets = None
                        except Exception as ce:
                            item["warn"].append("áž€áŸ’áž›áž¼áž“ážŸáŸ†áž¡áŸáž„áž˜áž·áž“áž”áž¶áž“ áž”áŸ’ážšáž¾ážŸáŸ†áž¡áŸáž„ AI áž’áž˜áŸ’áž˜ážáž¶áŸ” áž˜áž¼áž›áž áŸážáž»: " + str(ce)[:200])
                    rep.write("ðŸŽ™ áž€áŸ†áž–áž»áž„áž”áž„áŸ’áž€áž¾ážážŸáŸ†áž¡áŸáž„ážáŸ’áž˜áŸ‚ážš...")
                    match_notes = []
                    try:
                        dub_ok = make_dub(folder, dub_segments, settings["voice"], duration, settings["keep_bg"], client, used_model, seg_voices=seg_voices, targets=targets, notes=match_notes, emotions=emotions, groq_key=settings["groq_key"], clone_voice=clone_voice, eleven_key=settings.get("eleven_key"), ref_bands=ref_bands, base_rate=settings.get("tts_rate", 0))
                    finally:
                        if clone_voice:
                            eleven_delete_voice(settings["eleven_key"], clone_voice)
                    item["voice_lines"] = match_notes + voice_notes
                except Exception:
                    dub_ok = False
                if not dub_ok:
                    item["warn"].append("áž”áž„áŸ’áž€áž¾ážážŸáŸ†áž¡áŸáž„áž¢áž¶áž“áž˜áž·áž“áž”áž¶áž“áž‘áŸáŸ” ážœáž¸ážŠáŸáž¢áž¼áž˜áž¶áž“ážáŸ‚áž¢áž€áŸ’ážŸážšáŸ”")
            item["pct"] = 0.75
            rep.write("áŸ¤/áŸ¤ áž€áŸ†áž–áž»áž„ážšáž„áŸ‹áž…áž¶áŸ†ážŠáž¶áž€áŸ‹áž¢áž€áŸ’ážŸážšáž…áž¼áž›ážœáž¸ážŠáŸáž¢áž¼...")
            with job.render_slots:
                item["pct"] = 0.82
                rep.write("áŸ¤/áŸ¤ áž€áŸ†áž–áž»áž„ážŠáž¶áž€áŸ‹áž¢áž€áŸ’ážŸážšáž…áž¼áž›ážœáž¸ážŠáŸáž¢áž¼...")
                video, used_font, ffmpeg_log, attempts = render_with_fonts(folder, fonts, captions, settings["font_size"], settings["outline_size"], settings["color"], vid_w, vid_h, settings["quality"], rep, dub=dub_ok, alignment=settings.get("position", 2), subs=settings.get("subs_on", True))
            item["video"] = video
            item["captions"] = [t for _, _, t in captions]
            item["debug"] = {
                "áž˜áŸ‰áž¶ážŸáŸŠáž¸áž“": used_engine, "áž˜áŸ‰áž¼ážŠáŸ‚áž›": used_model,
                "áž€áž¶ážšážáž˜áŸ’ážšáž¹áž˜": sync_mode, "áž•áŸ’áž“áŸ‚áž€áž”ážšáž¶áž‡áŸáž™": failed_chunks,
                "Font ážŠáŸ‚áž›áž”áŸ’ážšáž¾": used_font, "Dubbing": dub_ok,
                "áž¢áŸ’áž“áž€áž“áž·áž™áž¶áž™": (item["voice_lines"][0] if item["voice_lines"] else ""),
                "áž‘áŸ†áž áŸ†áž›áž‘áŸ’áž’áž•áž›": f"{len(video) / (1024 * 1024):.1f}MB",
                "áž€áž¶ážšážŸáž¶áž€ Font": "\n".join(attempts),
                "fontselect": "\n".join(line for line in ffmpeg_log.splitlines() if "fontselect" in line.lower())[:1500],
                "áž˜áŸ‰áŸ„áž„áž¢áž€áŸ’ážŸážš": "\n".join(f"[{s:.1f}-{e:.1f}] {t}" for s, e, t in captions),
            }
            item["pct"] = 1.0
            item["stage"] = "ážšáž½áž…ážšáž¶áž›áŸ‹"
            item["elapsed"] = time.time() - item["t0"]
            item["state"] = "done"
    except Exception as error:
        item["error"] = friendly_message(error)
        item["raw_error"] = str(error)
        item["elapsed"] = time.time() - (item["t0"] or time.time())
        item["state"] = "error"
    finally:
        if item["state"] == "running":
            item["error"] = "áž€áž¶ážšáž”áž„áŸ’áž€áž¾ážážœáž¸ážŠáŸáž¢áž¼áž˜áž·áž“áž”áž¶áž“ážŸáž˜áŸ’ážšáŸáž…áŸ” ážŸáž¼áž˜ážŸáž¶áž€áž˜áŸ’ážáž„áž‘áŸ€ážáŸ”"
            item["state"] = "error"
        try:
            record_result(item["state"] == "done")
        except Exception:
            pass
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
            z.writestr(f"{i:02d}_{safe_filename(it['name'])}_khmer.mp4", it["video"])
    return buf.getvalue()


def dl_button(label, data, file_name, mime, key, **kwargs):
    if ST_VER >= (1, 43):
        return st.download_button(label, data=data, file_name=file_name, mime=mime, key=key, on_click="ignore", **kwargs)
    return st.download_button(label, data=data, file_name=file_name, mime=mime, key=key, **kwargs)


def work_area(job, was_running):
    items = job.items
    total = len(items)
    done = sum(1 for it in items if it["state"] == "done")
    failed = sum(1 for it in items if it["state"] == "error")
    working = total - done - failed
    c1, c2, c3 = st.columns(3)
    c1.metric("â³ áž€áŸ†áž–áž»áž„áž’áŸ’ážœáž¾", working)
    c2.metric("âœ… ážšáž½áž…ážšáž¶áž›áŸ‹", done)
    c3.metric("âŒ áž”ážšáž¶áž‡áŸáž™", failed)
    st.progress((done + failed) / total, text=f"ážŸážšáž»áž” {done + failed} / {total}")
    for i, it in enumerate(items, start=1):
        with st.container(border=True):
            left, right = st.columns([4, 1])
            left.markdown(f"**{i}. {it['name']}**")
            if it["t0"]:
                if it["elapsed"] is not None:
                    secs = it["elapsed"]
                else:
                    secs = time.time() - it["t0"]
                right.caption(f"â± {int(secs)} ážœáž·áž“áž¶áž‘áž¸")
            if it["state"] == "done":
                st.success("âœ… ážšáž½áž…ážšáž¶áž›áŸ‹ â€” áž‘áž¶áž‰áž™áž€áž”áž¶áž“áž“áŸ…áž•áŸ’áž“áŸ‚áž€ážáž¶áž„áž€áŸ’ážšáŸ„áž˜ â¬‡ï¸")
            elif it["state"] == "error":
                st.error(it["error"] or "áž˜áž·áž“áž”áž¶áž“ážŸáž˜áŸ’ážšáŸáž…áŸ”")
                if DEBUG and it["raw_error"]:
                    st.text(it["raw_error"])
            else:
                st.progress(max(0.0, min(1.0, it["pct"])), text=it["stage"])
            for w in it["warn"]:
                st.warning(w)
    if was_running and not job.running():
        st.rerun()


def download_area(job):
    done = [(i, it) for i, it in enumerate(job.items, start=1) if it["state"] == "done"]
    if job.zip:
        dl_button("ðŸ“¦ áž‘áž¶áž‰áž™áž€áž‘áž¶áŸ†áž„áž¢ážŸáŸ‹ (ZIP)", job.zip, "khmer_videos.zip", "application/zip", key=f"zip_{job.id}", use_container_width=True)
    if not done:
        st.info("ážœáž¸ážŠáŸáž¢áž¼ážŽáž¶ážŠáŸ‚áž›ážšáž½áž…ážšáž¶áž›áŸ‹ áž“áž¹áž„áž›áŸáž…áž¡áž¾áž„áž“áŸ…áž‘áž¸áž“áŸáŸ‡áž—áŸ’áž›áž¶áž˜áŸ— áž áž¾áž™áž¢áž¶áž…áž‘áž¶áž‰áž™áž€áž”áž¶áž“ážáŸ‚áž˜áŸ’ážáž„áŸ”")
        return
    for i, it in done:
        with st.container(border=True):
            st.markdown(f"**{i}. {it['name']}**")
            st.video(it["video"])
            dl_button("â¬‡ï¸ áž‘áž¶áž‰áž™áž€ážœáž¸ážŠáŸáž¢áž¼áž“áŸáŸ‡", it["video"], f"{safe_filename(it['name'])}_khmer.mp4", "video/mp4", key=f"dl_{job.id}_{i}", type="primary", use_container_width=True)
            with st.expander("ðŸ“ áž˜áž¾áž›áž¢ážáŸ’ážáž”áž‘ážáŸ’áž˜áŸ‚ážš"):
                for text in it["captions"]:
                    st.write(text)
            if it.get("voice_lines"):
                with st.expander("ðŸ‘« áž–áŸážáŸŒáž˜áž¶áž“ážŸáŸ†áž¡áŸáž„áž¢áž¶áž“"):
                    for line in it["voice_lines"]:
                        st.write(line)
            if DEBUG:
                with st.expander("ðŸ›  DEBUG"):
                    for key, value in it["debug"].items():
                        st.text(f"{key}: {value}")
                    st.text("\n".join(it["log"][-30:]))


# ážŠáž¶áž€áŸ‹ážáŸ†ážŽážœáž¸ážŠáŸáž¢áž¼ TikTok ážŠáŸ‚áž›áž¢áŸ’áž“áž€áž…áž„áŸ‹áž±áŸ’áž™áž¢áŸ’áž“áž€áž”áŸ’ážšáž¾áž˜áž¾áž›áž–áŸáž›ážšáž„áŸ‹áž…áž¶áŸ† áž“áŸ…áž‘áž¸áž“áŸáŸ‡ (áž˜áž½áž™ážáŸ†ážŽáž€áŸ’áž“áž»áž„áž˜áž½áž™áž”áž“áŸ’áž‘áž¶ážáŸ‹)
TIKTOK_VIDEOS = [
    # "https://www.tiktok.com/@username/video/1234567890123456789",
    # "https://vm.tiktok.com/xxxxxxx/",
]

TT_ID_RE = re.compile(r"/video/(\d{8,25})")


@st.cache_data(show_spinner=False, ttl=86400)
def tiktok_video_id(url):
    url = str(url or "").strip()
    if re.fullmatch(r"\d{8,25}", url):
        return url
    m = TT_ID_RE.search(url)
    if m:
        return m.group(1)
    if "tiktok.com" in url:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                m = TT_ID_RE.search(r.geturl())
                if m:
                    return m.group(1)
        except Exception:
            pass
    return None


def tiktok_playlist():
    links = list(TIKTOK_VIDEOS)
    extra = st.secrets.get("TIKTOK_LINKS", [])
    if isinstance(extra, str):
        extra = [extra]
    links += [str(x) for x in list(extra)]
    ids = []
    for ln in links:
        if not str(ln).strip():
            continue
        vid = tiktok_video_id(ln)
        if vid and vid not in ids:
            ids.append(vid)
    return ids


def render_tiktok_box():
    import random
    ids = tiktok_playlist()
    if not ids:
        if is_admin():
            st.info("ðŸ” (áž˜áŸ’áž…áž¶ážŸáŸ‹áž”áŸ‰áž»ážŽáŸ’ážŽáŸ„áŸ‡) áž˜áž·áž“áž‘áž¶áž“áŸ‹áž˜áž¶áž“ážœáž¸ážŠáŸáž¢áž¼ TikTok áž‘áŸáŸ” ážŸáž¼áž˜ážŠáž¶áž€áŸ‹ážáŸ†ážŽáž€áŸ’áž“áž»áž„ TIKTOK_VIDEOS (áž€áŸ’áž“áž»áž„áž€áž¼ážŠ) áž¬ TIKTOK_LINKS (áž€áŸ’áž“áž»áž„ Secrets)áŸ”")
        return
    order = st.session_state.get("tt_order")
    if not order or set(order) != set(ids):
        order = random.sample(ids, len(ids))
        st.session_state["tt_order"] = order
        st.session_state["tt_idx"] = 0
    idx = st.session_state.get("tt_idx", 0) % len(order)
    with st.expander("ðŸŽµ áž˜áž¾áž› TikTok áž–áŸáž›ážšáž„áŸ‹áž…áž¶áŸ†", expanded=True):
        c1, c2, c3 = st.columns([1, 2, 1])
        if c1.button("â®", key="tt_prev", use_container_width=True):
            idx = (idx - 1) % len(order)
        if c3.button("â­ áž”áž“áŸ’áž‘áž¶áž”áŸ‹", key="tt_next", type="primary", use_container_width=True):
            idx = (idx + 1) % len(order)
        st.session_state["tt_idx"] = idx
        c2.caption(f"ážœáž¸ážŠáŸáž¢áž¼ {idx + 1} / {len(order)}")
        components.html(
            f"""
            <div style="display:flex;justify-content:center;">
              <iframe src="https://www.tiktok.com/embed/v2/{order[idx]}"
                      width="325" height="740"
                      style="border:0;border-radius:14px;max-width:100%;"
                      allow="autoplay; fullscreen; encrypted-media"
                      allowfullscreen></iframe>
            </div>
            """,
            height=760,
        )


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


import html as _html

GEMINI_KEY = ""  # Gemini ážáŸ’ážšáž¼ážœáž”áž¶áž“áž”áž·áž‘ áž˜áž·áž“ážŠáŸ†ážŽáž¾ážšáž€áž¶ážšáž‘áŸ
GROQ_KEY = st.secrets.get("GROQ_API_KEY", "")
ELEVEN_KEY = st.secrets.get("ELEVENLABS_API_KEY", "")

USER_ID = get_user_id()
sync_browser_id(USER_ID)

# áž”áž„áŸ’áž áž¶áž‰áž‡áž¶áž‘áŸ†áž–áŸážš PC áž›áž¾áž‘áž¼ážšážŸáž–áŸ’áž‘áŸ– áž”áž„áŸ’ážšáž½áž˜áž‘áž¶áŸ†áž„áž˜áž¼áž›ážáž¶áž˜áž‘áž‘áž¹áž„áž¢áŸáž€áŸ’ážšáž„áŸ‹ (ážŠáŸáž€ áž“áž·áž„ážˆážš)
# áž€áŸ‚áŸ– áž–áŸáž›áž”áž„áŸ’ážšáž½áž˜ (zoom) ážáŸ’ážšáž¼ážœáž”áž„áŸ’áž€áž¾áž“áž€áž˜áŸ’áž–ážŸáŸ‹áž±áŸ’áž™ážŸáŸ’áž˜áž¾ innerHeight / zoom ážŠáž¾áž˜áŸ’áž”áž¸áž±áŸ’áž™áž˜áž¶ážáž·áž€áž¶áž–áŸáž‰áž¢áŸáž€áŸ’ážšáž„áŸ‹
components.html(
    """
    <script>
    (function () {
      var TARGET = 1100;
      function fit() {
        try {
          var p = window.parent;
          var d = p.document;
          var w = p.innerWidth || 1200;
          var z = w >= TARGET ? 1 : Math.max(0.4, w / TARGET);
          var h = Math.round((p.innerHeight || 800) / z) + "px";
          if (p.__kacZ === z && p.__kacH === h) { return; }
          p.__kacZ = z; p.__kacH = h;
          d.documentElement.style.zoom = z;
          var sels = [
            '[data-testid="stApp"]',
            '[data-testid="stAppViewContainer"]',
            '[data-testid="stMain"]',
            'section.main'
          ];
          sels.forEach(function (sel) {
            var el = d.querySelector(sel);
            if (el) {
              el.style.height = h;
              el.style.minHeight = h;
            }
          });
        } catch (e) {}
      }
      fit();
      setTimeout(fit, 300);
      try { window.parent.addEventListener("resize", fit); } catch (e) {}
      try { window.parent.addEventListener("orientationchange", function () { setTimeout(fit, 250); }); } catch (e) {}
    })();
    </script>
    """,
    height=0,
)

if not GROQ_KEY:
    st.error("áž€áž˜áŸ’áž˜ážœáž·áž’áž¸áž˜áž·áž“áž‘áž¶áž“áŸ‹ážšáž½áž…ážšáž¶áž›áŸ‹áž‘áŸáŸ” ážŸáž¼áž˜áž‘áž¶áž€áŸ‹áž‘áž„áž˜áŸ’áž…áž¶ážŸáŸ‹áž€áž˜áŸ’áž˜ážœáž·áž’áž¸áŸ”")
    st.stop()

# ---------------------------------------------------------------------
#  áž‡áž˜áŸ’ážšáž¾ážŸáž•áŸ’ážŸáŸáž„áŸ—
# ---------------------------------------------------------------------
PAGE_LABELS = {
    "home": "ðŸ  áž‘áŸ†áž–áŸážšážŠáž¾áž˜",
    "sub": "ðŸ’¬ áž¢áž€áŸ’ážŸážšážáŸ’áž˜áŸ‚ážš",
    "dub": "ðŸŽ™ ážŸáŸ†áž¡áŸáž„ AI",
    "batch": "ðŸ“š áž…áŸ’ážšáž¾áž“ážœáž¸ážŠáŸáž¢áž¼",
    "videos": "ðŸŽž ážœáž¸ážŠáŸáž¢áž¼ážáŸ’áž‰áž»áŸ†",
    "help": "â“ áž‡áŸ†áž“áž½áž™",
}
PAGE_IDS = list(PAGE_LABELS.keys())

COLOR_OPTIONS = {
    "âšª ážŸ": ("&H00FFFFFF", "#FFFFFF"),
    "ðŸŸ¡ áž›áž¿áž„": ("&H0000FFFF", "#FFE600"),
    "ðŸŸ¢ áž”áŸƒážáž„": ("&H0000FF00", "#3DDC64"),
    "ðŸ”µ ážáŸ€ážœ": ("&H00FF0000", "#3D7BFF"),
    "ðŸ”´ áž€áŸ’ážšáž áž˜": ("&H000000FF", "#FF4D5E"),
}
POSITION_OPTIONS = {"â¬‡ áž€áŸ’ážšáŸ„áž˜": 2, "âº áž€ážŽáŸ’ážŠáž¶áž›": 5, "â¬† áž›áž¾": 8}
MODES = ["ðŸ“ Upload Â· áž•áŸ’áž‘áž»áž€ážœáž¸ážŠáŸáž¢áž¼", "ðŸ”— Link Â· ážáŸ†ážŽ", "ðŸ“š Batch Â· áž…áŸ’ážšáž¾áž“ážœáž¸ážŠáŸáž¢áž¼"]
VIDEO_TYPES = ["mp4", "mov", "mkv", "avi", "webm"]

ENGINE_FREE = "ðŸ†“ áž¥ážáž‚áž·ážážáŸ’áž›áŸƒ (Groq + Google Translate)"
ENGINE_GEMINI = "âœ¨ Gemini (áž’áž˜áŸ’áž˜áž‡áž¶ážáž·áž‡áž¶áž„ ážáŸ‚áž˜áž¶áž“áž€áž¼ážáž¶)"

# ážšáž€áŸ’ážŸáž¶ážáž˜áŸ’áž›áŸƒáž€áž¶ážšáž€áŸ†ážŽážáŸ‹ áž–áŸáž›áž”áŸ’ážáž¼ážšáž‘áŸ†áž–áŸážš
SETTING_KEYS = ["fs", "ol", "fc", "pos", "voice", "spd", "qual", "eng", "lang",
                "keep_bg", "subs_on", "font_choice"]
for _k in SETTING_KEYS:
    if _k in st.session_state:
        st.session_state[_k] = st.session_state[_k]

st.session_state.setdefault("library", [])


def esc(x):
    return _html.escape(str(x or ""))


def fmt_mb(n):
    return f"{n / (1024 * 1024):.1f}MB"


# ---------------------------------------------------------------------
#  Sidebar (áž˜áŸ‰ážºáž“áž»áž™)
# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
#  Header
# ---------------------------------------------------------------------
st.markdown(
    '<div class="kac-hero"><div>'
    '<h1>áž”áž€áž”áŸ’ážšáŸ‚ážšáž¿áž„áž˜áž€<span>áž“áž·áž™áž¶áž™áž—áž¶ážŸáž¶ážáŸ’áž˜áŸ‚ážš</span></h1>'
    '<p>áž”áž„áŸ’áž€áž¾ážážœáž¸ážŠáŸáž¢áž¼áž˜áž¶áž“áž¢áž€áŸ’ážŸážšážáŸ’áž˜áŸ‚ážš áž“áž·áž„ážŸáŸ†áž¡áŸáž„áž¢áž¶áž“ AI Â· áž”áŸ’ážšáž¾áž”áž¶áž“áž‚áŸ’áž˜áž¶áž“ážŠáŸ‚áž“áž€áŸ†ážŽážáŸ‹</p></div>'
    '<div class="kac-feats">'
    '<div><i>ðŸ’¬</i><b>Auto Subtitle</b><small>áž”áž„áŸ’áž€áž¾ážáž¢áž€áŸ’ážŸážšážáŸ’áž˜áŸ‚ážš</small></div>'
    '<div><i>ðŸŽ™</i><b>AI Dubbing</b><small>áž”áž‰áŸ’áž…áž¼áž›ážŸáŸ†áž¡áŸáž„ AI</small></div>'
    '<div><i>ðŸ…°</i><b>Custom Style</b><small>áž€áŸ†ážŽážáŸ‹áž…áŸážŸáŸ’ážšážŸáŸ‹</small></div>'
    '<div><i>HD</i><b>High Quality</b><small>áž‚áž»ážŽáž—áž¶áž–ážáŸ’áž–ážŸáŸ‹</small></div>'
    '</div></div>'
    '<div class="kac-rotate">ðŸ“± ážŸáž¼áž˜áž”áž„áŸ’ážœáž·áž›áž‘áž¼ážšážŸáž–áŸ’áž‘ážŠáŸáž€ (áž•áŸ’ážŠáŸáž€) ážŠáž¾áž˜áŸ’áž”áž¸áž”áŸ’ážšáž¾áž”áž¶áž“ážŸáŸ’ážšáž½áž›áž‡áž¶áž„áž“áŸáŸ‡</div>',
    unsafe_allow_html=True,
)

nav_col, fs_col = st.columns([6, 1])
with nav_col:
    page_id = st.radio("áž˜áŸ‰ážºáž“áž»áž™", PAGE_IDS, format_func=lambda k: PAGE_LABELS[k],
                       horizontal=True, label_visibility="collapsed", key="page")
with fs_col:
    components.html(
        """
        <style>
          html, body { margin: 0; background: transparent; }
          button {
            width: 100%; height: 46px; border-radius: 12px; border: 1.5px solid #2A3270;
            background: #1A2158; color: #EEF2FF; font-weight: 700; font-size: 15px;
            font-family: system-ui, sans-serif; cursor: pointer;
          }
          button:active { background: #2F6BFF; }
        </style>
        <button id="fs">â›¶ áž–áŸáž‰áž¢áŸáž€áŸ’ážšáž„áŸ‹</button>
        <script>
          document.getElementById("fs").onclick = function () {
            try {
              var d = window.parent.document;
              var el = d.documentElement;
              if (d.fullscreenElement || d.webkitFullscreenElement) {
                (d.exitFullscreen || d.webkitExitFullscreen).call(d);
              } else {
                (el.requestFullscreen || el.webkitRequestFullscreen).call(el);
              }
            } catch (e) {}
          };
        </script>
        """,
        height=50,
    )


def section(title, extra=""):
    st.markdown(f'<div class="kac-sec">{title} <b>{extra}</b></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------
#  áž”áž“áŸ’áž‘áž¶ážáŸ‹ážœáž¸ážŠáŸáž¢áž¼ (Completed / My Videos)
# ---------------------------------------------------------------------
def video_rows(entries, prefix):
    if not entries:
        st.info("áž˜áž·áž“áž‘áž¶áž“áŸ‹áž˜áž¶áž“ážœáž¸ážŠáŸáž¢áž¼ážšáž½áž…ážšáž¶áž›áŸ‹áž‘áŸáŸ” ážœáž¸ážŠáŸáž¢áž¼ážŽáž¶ážŠáŸ‚áž›ážšáž½áž…ážšáž¶áž›áŸ‹ áž“áž¹áž„áž›áŸáž…áž¡áž¾áž„áž“áŸ…áž‘áž¸áž“áŸáŸ‡áž—áŸ’áž›áž¶áž˜áŸ—áŸ”")
        return
    for item, owner in entries:
        k = f"{prefix}_{id(item)}"
        with st.container(border=True):
            c_name, c_play, c_dl, c_del = st.columns([3.2, 1.1, 1.5, 0.8])
            secs = int(item.get("elapsed") or 0)
            c_name.markdown(
                f'<div class="kac-vname">âœ… <b>{esc(item["name"])}</b>'
                f'<small>â± {secs} ážœáž·áž“áž¶áž‘áž¸ Â· {fmt_mb(len(item["video"]))}</small></div>',
                unsafe_allow_html=True,
            )
            playing = st.session_state.get(f"play_{k}", False)
            if c_play.button("â¹ áž”áž·áž‘" if playing else "â–¶ áž˜áž¾áž›", key=f"pb_{k}", use_container_width=True):
                playing = not playing
                st.session_state[f"play_{k}"] = playing
            with c_dl:
                dl_button("â¬‡ áž‘áž¶áž‰áž™áž€", item["video"], f"{safe_filename(item['name'])}_khmer.mp4",
                          "video/mp4", key=f"dl_{k}", type="primary", use_container_width=True)
            if c_del.button("ðŸ—‘", key=f"del_{k}", use_container_width=True, help="áž›áž»áž”ážœáž¸ážŠáŸáž¢áž¼áž“áŸáŸ‡"):
                try:
                    owner.remove(item)
                except ValueError:
                    pass
                st.session_state.pop(f"play_{k}", None)
                st.rerun()
            if playing:
                st.video(item["video"])
            with st.expander("ðŸ“ áž˜áž¾áž›áž¢ážáŸ’ážáž”áž‘ážáŸ’áž˜áŸ‚ážš"):
                for text in item["captions"]:
                    st.write(text)
            if item.get("voice_lines"):
                with st.expander("ðŸ‘« áž–áŸážáŸŒáž˜áž¶áž“ážŸáŸ†áž¡áŸáž„áž¢áž¶áž“"):
                    for line in item["voice_lines"]:
                        st.write(line)
            if DEBUG:
                with st.expander("ðŸ›  DEBUG"):
                    for key, value in item["debug"].items():
                        st.text(f"{key}: {value}")
                    st.text("\n".join(item["log"][-30:]))


def processing_panel(job, was_running):
    items = job.items
    active = [(i, it) for i, it in enumerate(items, start=1) if it["state"] in ("queued", "running")]
    failed = [(i, it) for i, it in enumerate(items, start=1) if it["state"] == "error"]
    done = sum(1 for it in items if it["state"] == "done")
    head, btn = st.columns([3, 1.3])
    head.markdown(
        f'<div class="kac-sec">áž€áŸ†áž–áž»áž„ážŠáŸ†ážŽáž¾ážšáž€áž¶ážš <b>({len(active)}) Â· âœ… {done} Â· âŒ {len(failed)}</b></div>',
        unsafe_allow_html=True,
    )
    if active and btn.button("â›” áž”áŸ„áŸ‡áž”áž„áŸ‹áž‘áž¶áŸ†áž„áž¢ážŸáŸ‹", key=f"cancel_all_{job.id}", use_container_width=True):
        for _, it in active:
            it["cancel"] = True
    if not active:
        st.caption("áž˜áž·áž“áž˜áž¶áž“áž€áž¶ážšáž„áž¶ážšáž€áŸ†áž–áž»áž„ážŠáŸ†ážŽáž¾ážšáž€áž¶ážšáž‘áŸáŸ”")
    for i, it in active:
        c1, c2 = st.columns([4, 1.1])
        pct = int(max(0.0, min(1.0, it["pct"])) * 100)
        secs = int(time.time() - it["t0"]) if it["t0"] else 0
        c1.markdown(
            f'<div class="kac-row"><div class="ring" style="--p:{pct}"><span>{pct}%</span></div>'
            f'<div class="meta"><b>{i}. {esc(it["name"])}</b>'
            f'<div class="track"><i style="width:{pct}%"></i></div>'
            f'<small>{esc(it["stage"])}</small></div>'
            f'<div class="secs">â± {secs}s</div></div>',
            unsafe_allow_html=True,
        )
        if c2.button("áž”áŸ„áŸ‡áž”áž„áŸ‹", key=f"cancel_{job.id}_{i}", use_container_width=True):
            it["cancel"] = True
            it["stage"] = "áž€áŸ†áž–áž»áž„áž”áŸ„áŸ‡áž”áž„áŸ‹..."
    for i, it in failed:
        st.error(f"âŒ {i}. {it['name']} â€” {it['error'] or 'áž˜áž·áž“áž”áž¶áž“ážŸáž˜áŸ’ážšáŸáž…áŸ”'}")
        if DEBUG and it["raw_error"]:
            st.text(it["raw_error"])
    for i, it in enumerate(items, start=1):
        for w in it["warn"]:
            st.warning(f"{i}. {w}")
    if was_running and not job.running():
        st.rerun()


def completed_panel(job, query):
    entries = [(it, job.items) for it in job.items if it["state"] == "done"]
    q = (query or "").strip().lower()
    if q:
        entries = [(it, ow) for it, ow in entries if q in it["name"].lower()]
    if job.zip:
        dl_button("ðŸ“¦ áž‘áž¶áž‰áž™áž€áž‘áž¶áŸ†áž„áž¢ážŸáŸ‹ (ZIP)", job.zip, "khmer_videos.zip", "application/zip",
                  key=f"zip_{job.id}", use_container_width=True)
    video_rows(entries, "c")


def start_job(items, settings):
    try:
        fonts_data = load_font_bytes(settings.get("font_choice", DEFAULT_FONT))
    except Exception:
        st.error("áž‘áž¶áž‰áž™áž€ Font ážáŸ’áž˜áŸ‚ážšáž˜áž·áž“áž”áž¶áž“áŸ” ážŸáž¼áž˜ážŸáž¶áž€áž˜áŸ’ážáž„áž‘áŸ€ážáŸ”")
        st.stop()
    prepare_home_font(fonts_data)
    record_start(USER_ID, len(items))
    old = st.session_state.get("job")
    if old:
        lib = st.session_state["library"]
        for it in old.items:
            if it["state"] == "done" and it["video"]:
                lib.append(it)
        del lib[:-8]
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


# ---------------------------------------------------------------------
#  áž‘áŸ†áž–áŸážšáž’áŸ’ážœáž¾áž€áž¶ážš (Home / Subtitle / Dubbing / Batch)
# ---------------------------------------------------------------------
def workspace(page_id):
    current_job = st.session_state.get("job")
    busy = bool(current_job and current_job.running())
    left, right = st.columns([1.55, 1], gap="medium")

    # ----- áž†áŸ’ážœáŸáž„áŸ– áž”áž‰áŸ’áž…áž¼áž›ážœáž¸ážŠáŸáž¢áž¼ -----
    with left:
        section("áž•áŸ’áž‘áž»áž€ážœáž¸ážŠáŸáž¢áž¼", "Upload")
        with st.container(border=True):
            mode = st.radio("ážœáž·áž’áž¸áž”áž‰áŸ’áž…áž¼áž›", MODES, index=2 if page_id == "batch" else 0,
                            horizontal=True, label_visibility="collapsed", key=f"mode_{page_id}")
            uploaded_files = []
            link_text = ""
            if mode.startswith("ðŸ“"):
                one = st.file_uploader("áž‘áž¶áž‰ážœáž¸ážŠáŸáž¢áž¼áž˜áž€áž‘áž¸áž“áŸáŸ‡ áž¬áž…áž»áž…áž‡áŸ’ážšáž¾ážŸážšáž¾ážŸ", type=VIDEO_TYPES, key=f"up1_{page_id}")
                uploaded_files = [one] if one else []
            elif mode.startswith("ðŸ”—"):
                link_text = st.text_area(
                    "ážáŸ†ážŽážœáž¸ážŠáŸáž¢áž¼ (TikTok, .mp4 áž•áŸ’áž‘áž¶áž›áŸ‹ áž¬ Google Drive ážŸáž¶áž’áž¶ážšážŽáŸˆ) â€” áž˜áž½áž™áž”áž“áŸ’áž‘áž¶ážáŸ‹ áŸ¡ ážáŸ†ážŽ",
                    placeholder="https://...\nhttps://...", height=120, key=f"link_{page_id}")
            else:
                uploaded_files = st.file_uploader(
                    f"áž‡áŸ’ážšáž¾ážŸáž”áž¶áž“ážŠáž›áŸ‹ {MAX_VIDEOS} ážœáž¸ážŠáŸáž¢áž¼ áž€áŸ’áž“áž»áž„áž–áŸáž›ážáŸ‚áž˜áž½áž™", type=VIDEO_TYPES,
                    accept_multiple_files=True, key=f"upn_{page_id}") or []
            st.caption(f"MP4, MOV, MKV, AVI, WEBM Â· ážœáŸ‚áž„áž”áŸ†áž•áž»áž {MAX_DURATION_MIN} áž“áž¶áž‘áž¸")

    items = []
    too_many = False
    if uploaded_files:
        too_many = len(uploaded_files) > MAX_VIDEOS
        for f in uploaded_files[:MAX_VIDEOS]:
            items.append({"name": clean_name(f.name), "file": f, "url": None})
    else:
        lines = [ln.strip() for ln in link_text.splitlines()
                 if ln.strip().lower().startswith(("http://", "https://"))]
        too_many = len(lines) > MAX_VIDEOS
        for i, url in enumerate(lines[:MAX_VIDEOS], start=1):
            items.append({"name": f"Video {i}", "file": None, "url": url})

    # ----- ážŸáŸ’ážáž¶áŸ†áŸ– áž˜áž¾áž›áž‡áž¶áž˜áž»áž“ + áž€áž¶ážšáž€áŸ†ážŽážáŸ‹ -----
    with right:
        preview_ph = st.container()

        with st.container(border=True):
            st.markdown('<div class="kac-card-title">ðŸ…° áž€áŸ†ážŽážáŸ‹áž¢áž€áŸ’ážŸážš Â· Subtitle</div>', unsafe_allow_html=True)
            if page_id == "sub":
                subs_on = True
            else:
                subs_on = st.checkbox("ážŠáž¶áž€áŸ‹áž¢áž€áŸ’ážŸážšážáŸ’áž˜áŸ‚ážšáž›áž¾ážœáž¸ážŠáŸáž¢áž¼ (Subtitle)", value=True, key="subs_on")
            font_choice = DEFAULT_FONT
            font_size, outline_size = 22, 2
            color_label = list(COLOR_OPTIONS.keys())[0]
            pos_label = list(POSITION_OPTIONS.keys())[0]
            if subs_on:
                font_choice = st.selectbox("áž–áž»áž˜áŸ’áž–áž¢áž€áŸ’ážŸážšážáŸ’áž˜áŸ‚ážš", list(FONT_CHOICES.keys()), key="font_choice")
                font_size = st.slider("áž‘áŸ†áž áŸ†áž¢áž€áŸ’ážŸážš", 16, 36, 22, key="fs")
                outline_size = st.slider("áž€áž˜áŸ’ážšáž¶ážŸáŸ‹áž‚áŸ‚áž˜áž¢áž€áŸ’ážŸážš", 1, 5, 2, key="ol")
                color_label = st.radio("áž–ážŽáŸŒáž¢áž€áŸ’ážŸážš", list(COLOR_OPTIONS.keys()), horizontal=True, key="fc")
                pos_label = st.radio("áž‘áž¸ážáž¶áŸ†áž„áž¢áž€áŸ’ážŸážš", list(POSITION_OPTIONS.keys()), horizontal=True, key="pos")
            else:
                st.caption("ážœáž¸ážŠáŸáž¢áž¼áž“áž¹áž„áž‚áŸ’áž˜áž¶áž“áž¢áž€áŸ’ážŸážšáž›áž¾ážœáž¸ážŠáŸáž¢áž¼áž‘áŸáŸ”")

        voice_label = list(TTS_VOICES.keys())[0]
        speed = 1.0
        keep_bg = False
        if page_id == "sub":
            dub_on = False
        else:
            with st.container(border=True):
                st.markdown('<div class="kac-card-title">ðŸŽ™ ážŸáŸ†áž¡áŸáž„ AI Â· Dubbing</div>', unsafe_allow_html=True)
                if page_id == "dub":
                    dub_on = True
                else:
                    dub_on = st.checkbox("áž”áž“áŸ’ážáŸ‚áž˜ážŸáŸ†áž¡áŸáž„áž¢áž¶áž“áž‡áž¶áž—áž¶ážŸáž¶ážáŸ’áž˜áŸ‚ážš (Dubbing)", key=f"dub_{page_id}")
                if dub_on:
                    voice_label = st.selectbox("ážŸáŸ†áž¡áŸáž„", list(TTS_VOICES.keys()), key="voice")
                    speed = st.slider("áž›áŸ’áž”áž¿áž“áž¢áž¶áž“", 0.8, 1.4, 1.0, 0.05, key="spd", format="%.2fx")
                    keep_bg = st.checkbox(
                        "ðŸ”ˆ ážšáž€áŸ’ážŸáž¶ážŸáŸ†áž¡áŸáž„ážŠáž¾áž˜ážáž·áž…áŸ— (áž”áž“áŸ’ážáž™ážŸáŸ†áž¡áŸáž„ážŠáž¾áž˜)",
                        value=True, key="keep_bg")

        # ----- áž˜áž¾áž›áž‡áž¶áž˜áž»áž“ (áž”áŸ†áž–áŸáž‰áž€áŸ’áž“áž»áž„ container ážáž¶áž„áž›áž¾) -----
        css_color = COLOR_OPTIONS[color_label][1]
        align = POSITION_OPTIONS[pos_label]
        valign = {2: "flex-end", 5: "center", 8: "flex-start"}[align]
        with preview_ph:
            with st.container(border=True):
                st.markdown('<div class="kac-card-title">ðŸŽ¬ áž˜áž¾áž›áž‡áž¶áž˜áž»áž“ Â· Preview</div>', unsafe_allow_html=True)
                if uploaded_files and st.checkbox("â–¶ áž˜áž¾áž›ážœáž¸ážŠáŸáž¢áž¼ážŠáŸ‚áž›áž”áž¶áž“áž‡áŸ’ážšáž¾ážŸ", key="prev_vid"):
                    try:
                        st.video(uploaded_files[0])
                    except Exception:
                        pass
                if subs_on:
                    px = max(12, int(font_size * 0.85))
                    o = outline_size
                    shadow = ",".join(f"{dx}px {dy}px 0 #000" for dx, dy in
                                      [(-o, 0), (o, 0), (0, -o), (0, o), (-o, -o), (o, -o), (-o, o), (o, o)])
                    fam = FONT_CHOICES[font_choice][2]
                    st.markdown(
                        f"<style>@import url('https://fonts.googleapis.com/css2?family={fam.replace(' ', '+')}&display=swap');</style>"
                        f'<div class="kac-stage" style="align-items:{valign}">'
                        f'<div class="cap" style="color:{css_color};font-size:{px}px;text-shadow:{shadow};'
                        f"font-family:'{fam}','Kantumruy Pro',sans-serif\">"
                        'ážŸáž½ážŸáŸ’ážáž¸! áž“áŸáŸ‡áž‡áž¶áž¢áž€áŸ’ážŸážšáž‚áŸ†ážšáž¼</div></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div class="kac-stage"></div>', unsafe_allow_html=True)
                    st.caption("áž˜áž·áž“ážŠáž¶áž€áŸ‹áž¢áž€áŸ’ážŸážšáž›áž¾ážœáž¸ážŠáŸáž¢áž¼")

    # ----- áž†áŸ’ážœáŸáž„áŸ– áž›áž‘áŸ’áž’áž•áž› + áž”áŸŠáž¼ážáž»áž„áž…áž¶áž”áŸ‹áž•áŸ’ážáž¾áž˜ (áž“áŸ…áž€áŸ’ážšáŸ„áž˜áž€áž¶ážšáž”áž‰áŸ’áž…áž¼áž›ážœáž¸ážŠáŸáž¢áž¼) -----
    with left:
        with st.container(border=True):
            st.markdown('<div class="kac-card-title">âš™ áž›áž‘áŸ’áž’áž•áž› Â· Output</div>', unsafe_allow_html=True)
            quality_label = st.selectbox("áž‚áž»ážŽáž—áž¶áž–ážœáž¸ážŠáŸáž¢áž¼", list(QUALITY.keys()), index=1, key="qual")
            language_label = st.selectbox("áž—áž¶ážŸáž¶áž€áŸ’áž“áž»áž„ážœáž¸ážŠáŸáž¢áž¼", list(LANGUAGES.keys()), index=0, key="lang")
            engine_label = ENGINE_FREE

        # ----- áž”áŸŠáž¼ážáž»áž„áž…áž¶áž”áŸ‹áž•áŸ’ážáž¾áž˜ -----
        run = False
        if too_many:
            st.warning(f"áž¢áž¶áž…áž’áŸ’ážœáž¾áž”áž¶áž“ážáŸ’ážšáž¹áž˜ {MAX_VIDEOS} ážœáž¸ážŠáŸáž¢áž¼áž˜áŸ’ážáž„áŸ” áž“áž¹áž„áž’áŸ’ážœáž¾ážáŸ‚ {MAX_VIDEOS} ážŠáŸ†áž”áž¼áž„áŸ”")
        st.markdown('<div class="kac-start">', unsafe_allow_html=True)
        if busy:
            st.button("â³ áž€áŸ†áž–áž»áž„áž’áŸ’ážœáž¾áž€áž¶ážš... ážŸáž¼áž˜ážšáž„áŸ‹áž…áž¶áŸ†", disabled=True, use_container_width=True, key="start_busy")
        elif not items:
            st.button("âœ¨ áž…áž¶áž”áŸ‹áž•áŸ’ážáž¾áž˜ážŠáŸ†ážŽáž¾ážšáž€áž¶ážš", disabled=True, use_container_width=True, key="start_none")
            st.caption("ážŸáž¼áž˜áž‡áŸ’ážšáž¾ážŸážšáž¾ážŸážœáž¸ážŠáŸáž¢áž¼ áž¬áž”áž·áž‘áž—áŸ’áž‡áž¶áž”áŸ‹ážáŸ†ážŽáž‡áž¶áž˜áž»áž“ážŸáž·áž“áŸ”")
        elif not subs_on and not dub_on:
            st.button("âœ¨ áž…áž¶áž”áŸ‹áž•áŸ’ážáž¾áž˜ážŠáŸ†ážŽáž¾ážšáž€áž¶ážš", disabled=True, use_container_width=True, key="start_nothing")
            st.caption("ážŸáž¼áž˜áž”áž¾áž€áž™áŸ‰áž¶áž„áž áŸ„áž…ážŽáž¶ážŸáŸ‹áž˜áž½áž™áŸ– áž¢áž€áŸ’ážŸážšážáŸ’áž˜áŸ‚ážš áž¬ážŸáŸ†áž¡áŸáž„áž¢áž¶áž“ AIáŸ”")
        else:
            label = "âœ¨ áž…áž¶áž”áŸ‹áž•áŸ’ážáž¾áž˜ážŠáŸ†ážŽáž¾ážšáž€áž¶ážš"
            if len(items) > 1:
                label += f" ({len(items)} ážœáž¸ážŠáŸáž¢áž¼)"
            run = st.button(label, type="primary", use_container_width=True, key="start_go")
        st.markdown('</div>', unsafe_allow_html=True)


    if run:
        settings = {
            "engine": "free",
            "gemini_key": GEMINI_KEY, "groq_key": GROQ_KEY,
            "language": LANGUAGES[language_label], "quality": QUALITY[quality_label],
            "dub_on": dub_on, "voice": TTS_VOICES[voice_label],
            "tts_rate": int(round((speed - 1.0) * 100)),
            "keep_bg": keep_bg, "auto_gender": False,
            "voice_match": False, "emotion": False,
            "clone_sample": None, "eleven_key": None,
            "timbre": False, "timbre_sample": None,
            "font_size": font_size, "outline_size": outline_size,
            "subs_on": subs_on, "font_choice": font_choice,
            "color": COLOR_OPTIONS[color_label][0], "position": align,
        }
        start_job(items, settings)

    # ----- áž†áŸ’ážœáŸáž„áŸ– áž€áŸ†áž–áž»áž„ážŠáŸ†ážŽáž¾ážšáž€áž¶ážš + ážšáž½áž…ážšáž¶áž›áŸ‹ -----
    with left:
        job = st.session_state.get("job")
        if not job:
            section("áž€áŸ†áž–áž»áž„ážŠáŸ†ážŽáž¾ážšáž€áž¶ážš", "Processing")
            st.caption("áž“áŸ…áž‘áŸ†áž“áŸážšáŸ” áž‡áŸ’ážšáž¾ážŸážœáž¸ážŠáŸáž¢áž¼ ážšáž½áž…áž…áž»áž… Â«áž…áž¶áž”áŸ‹áž•áŸ’ážáž¾áž˜ážŠáŸ†ážŽáž¾ážšáž€áž¶ážšÂ»áŸ”")
            return
        running = job.running()
        if not running and not job.zip_done:
            job.zip = build_zip(job.items)
            job.zip_done = True
        refresh = REFRESH_SECONDS if running else None
        st.fragment(run_every=refresh)(processing_panel)(job, running)
        if running:
            render_tiktok_box()
        st.markdown('<div id="download-area"></div>', unsafe_allow_html=True)
        head, search = st.columns([2, 2])
        head.markdown('<div class="kac-sec">ážšáž½áž…ážšáž¶áž›áŸ‹ <b>Completed</b></div>', unsafe_allow_html=True)
        query = search.text_input("ážŸáŸ’ážœáŸ‚áž„ážšáž€", placeholder="ðŸ” ážŸáŸ’ážœáŸ‚áž„ážšáž€ážœáž¸ážŠáŸáž¢áž¼...",
                                  label_visibility="collapsed", key="q_home")
        st.fragment(run_every=refresh)(completed_panel)(job, query)
        if not running:
            if st.button("ðŸ—‘ áž›áž»áž”áž›áž‘áŸ’áž’áž•áž›áž‘áž¶áŸ†áž„áž¢ážŸáŸ‹", key="clear_job"):
                shutil.rmtree(job.folder, ignore_errors=True)
                st.session_state.pop("job", None)
                st.rerun()
            if not job.scrolled:
                job.scrolled = True
                if any(it["state"] == "done" for it in job.items):
                    scroll_to_downloads()


def videos_page():
    section("ážœáž¸ážŠáŸáž¢áž¼ážšáž”ážŸáŸ‹ážáŸ’áž‰áž»áŸ†", "My Videos")
    job = st.session_state.get("job")
    entries = []
    if job:
        entries += [(it, job.items) for it in job.items if it["state"] == "done"]
    lib = st.session_state["library"]
    entries += [(it, lib) for it in reversed(lib)]
    q = st.text_input("ážŸáŸ’ážœáŸ‚áž„ážšáž€", placeholder="ðŸ” ážŸáŸ’ážœáŸ‚áž„ážšáž€ážœáž¸ážŠáŸáž¢áž¼...", label_visibility="collapsed", key="q_videos")
    if q.strip():
        entries = [(it, ow) for it, ow in entries if q.strip().lower() in it["name"].lower()]
    if job and job.zip:
        dl_button("ðŸ“¦ áž‘áž¶áž‰áž™áž€áž‘áž¶áŸ†áž„áž¢ážŸáŸ‹ (ZIP)", job.zip, "khmer_videos.zip", "application/zip",
                  key=f"zipv_{job.id}", use_container_width=True)
    video_rows(entries, "v")
    st.caption("ážœáž¸ážŠáŸáž¢áž¼ážáŸ’ážšáž¼ážœáž”áž¶áž“ážšáž€áŸ’ážŸáž¶áž‘áž»áž€áž”ážŽáŸ’ážáŸ„áŸ‡áž¢áž¶ážŸáž“áŸ’áž“áž€áŸ’áž“áž»áž„áž€áž˜áŸ’áž˜ážœáž·áž’áž¸áŸ” ážŸáž¼áž˜áž‘áž¶áž‰áž™áž€áž‘áž»áž€áž—áŸ’áž›áž¶áž˜áŸ—áŸ”")
    if entries and st.button("ðŸ—‘ áž›áž»áž”ážœáž¸ážŠáŸáž¢áž¼áž‘áž¶áŸ†áž„áž¢ážŸáŸ‹", key="clear_all_videos"):
        if job:
            shutil.rmtree(job.folder, ignore_errors=True)
            st.session_state.pop("job", None)
        st.session_state["library"] = []
        st.rerun()


def help_page():
    section("áž‡áŸ†áž“áž½áž™", "Help")
    with st.container(border=True):
        st.markdown(
            "**ážšáž”áŸ€áž”áž”áŸ’ážšáž¾ (áŸ£áž‡áŸ†áž áž¶áž“)**\n\n"
            "1. ðŸ“ áž‡áŸ’ážšáž¾ážŸážœáž¸ážŠáŸáž¢áž¼ (Upload / Link / Batch)\n"
            "2. âš™ áž€áŸ†ážŽážáŸ‹áž¢áž€áŸ’ážŸážš áž“áž·áž„ážŸáŸ†áž¡áŸáž„ (áž¬áž‘áž»áž€ážŠáž¼áž…ážŠáž¾áž˜)\n"
            "3. âœ¨ áž…áž»áž… Â«áž…áž¶áž”áŸ‹áž•áŸ’ážáž¾áž˜ážŠáŸ†ážŽáž¾ážšáž€áž¶ážšÂ» ážšáž½áž…ážšáž„áŸ‹áž…áž¶áŸ† áž áž¾áž™áž‘áž¶áž‰áž™áž€\n"
        )
    with st.container(border=True):
        st.markdown(
            "**áž˜áŸ‰ážºáž“áž»áž™**\n\n"
            "- ðŸ  áž‘áŸ†áž–áŸážšážŠáž¾áž˜áŸ– áž’áŸ’ážœáž¾áž”áž¶áž“áž‘áž¶áŸ†áž„áž¢áž€áŸ’ážŸážš áž“áž·áž„ážŸáŸ†áž¡áŸáž„\n"
            "- ðŸ’¬ ážŠáž¶áž€áŸ‹áž¢áž€áŸ’ážŸážšážáŸ’áž˜áŸ‚ážšáŸ– ážáŸ‚áž¢áž€áŸ’ážŸážšážšážáŸ‹áž”áŸ‰áž»ážŽáŸ’ážŽáŸ„áŸ‡\n"
            "- ðŸŽ™ ážŸáŸ†áž¡áŸáž„ AIáŸ– áž¢áž€áŸ’ážŸážš + ážŸáŸ†áž¡áŸáž„áž¢áž¶áž“ážáŸ’áž˜áŸ‚ážš\n"
            "- ðŸ“š áž…áŸ’ážšáž¾áž“ážœáž¸ážŠáŸáž¢áž¼áŸ– áž’áŸ’ážœáž¾áž…áŸ’ážšáž¾áž“ážœáž¸ážŠáŸáž¢áž¼ážŸáŸ’áž˜áž¾áž‚áŸ’áž“áž¶\n"
            "- ðŸŽž ážœáž¸ážŠáŸáž¢áž¼ážšáž”ážŸáŸ‹ážáŸ’áž‰áž»áŸ†áŸ– áž˜áž¾áž› áž“áž·áž„áž‘áž¶áž‰áž™áž€ážœáž¸ážŠáŸáž¢áž¼ážŠáŸ‚áž›ážšáž½áž…ážšáž¶áž›áŸ‹\n"
        )
    with st.container(border=True):
        st.markdown(
            "**áž‚áž“áŸ’áž›áž¹áŸ‡**\n\n"
            "- ðŸ“± áž”áŸ’ážšáž¾áž‘áž¼ážšážŸáž–áŸ’áž‘ ážŸáž¼áž˜áž”áž„áŸ’ážœáž·áž›ážŠáŸáž€ (áž•áŸ’ážŠáŸáž€) ážŠáž¾áž˜áŸ’áž”áž¸ážƒáž¾áž‰áž˜áŸ‰ážºáž“áž»áž™ áž“áž·áž„áž€áž¶ážšáž€áŸ†ážŽážáŸ‹áž–áŸáž‰áž›áŸáž‰\n"
            "- ðŸ—£ áž…áž„áŸ‹áž±áŸ’áž™ AI áž“áž·áž™áž¶áž™áž’áž˜áŸ’áž˜ážáž¶ áž“áž·áž„ážšáž›áž¼áž“ ážŸáž¼áž˜áž”áŸ’ážšáž¾áž€áž¶ážšáž€áŸ†ážŽážáŸ‹ážŸáŸ†áž¡áŸáž„ážáž¶áž˜áž’áž˜áŸ’áž˜ážáž¶\n"
            "- â± ážœáž¸ážŠáŸáž¢áž¼ážáŸ’áž›áž¸áŸ— áž’áŸ’ážœáž¾áž”áž¶áž“áž›áž¿áž“ áž“áž·áž„áž˜áž¶áž“áž€áŸ†áž áž»ážŸážáž·áž…\n"
            "- â¬‡ ážŸáž¼áž˜áž‘áž¶áž‰áž™áž€ážœáž¸ážŠáŸáž¢áž¼áž—áŸ’áž›áž¶áž˜áŸ—áž–áŸáž›ážšáž½áž…ážšáž¶áž›áŸ‹\n"
        )


if page_id == "videos":
    videos_page()
elif page_id == "help":
    help_page()
else:
    workspace(page_id)


ADMIN_KEY = st.secrets.get("ADMIN_KEY", "")
if ADMIN_KEY and st.query_params.get("admin", "") == ADMIN_KEY:
    st.divider()
    section("ðŸ“Š ážŸáŸ’ážáž·ážáž·", "Admin")
    today_rec = today_stats()
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("ðŸŽ¬ ážœáž¸ážŠáŸáž¢áž¼", today_rec["videos"])
    a2.metric("ðŸ‘¥ áž¢áŸ’áž“áž€áž”áŸ’ážšáž¾", len(today_rec["users"]))
    a3.metric("âœ… áž‡áŸ„áž‚áž‡áŸáž™", today_rec["done"])
    a4.metric("âŒ áž”ážšáž¶áž‡áŸáž™", today_rec["failed"])
    all_stats = _load_stats()
    rows = [
        {
            "ážáŸ’áž„áŸƒ": day,
            "ážœáž¸ážŠáŸáž¢áž¼": all_stats[day]["videos"],
            "áž¢áŸ’áž“áž€áž”áŸ’ážšáž¾": len(all_stats[day]["users"]),
            "áž‡áŸ„áž‚áž‡áŸáž™": all_stats[day]["done"],
            "áž”ážšáž¶áž‡áŸáž™": all_stats[day]["failed"],
        }
        for day in sorted(all_stats.keys(), reverse=True)[:14]
    ]
    if rows:
        st.table(rows)
