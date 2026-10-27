import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import streamlit as st
import imageio_ffmpeg

APP_TITLE = "Khmer Auto Caption — Local Whisper"
st.set_page_config(page_title=APP_TITLE, page_icon="🎬", layout="centered")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Battambang:wght@400;700&display=swap');
html, body, [class*="css"] { font-family: 'Battambang', sans-serif; }
.block-container {max-width: 900px; padding-top: 1.5rem;}
</style>
""", unsafe_allow_html=True)

st.title("🎬 Khmer Auto Caption")
st.caption("Local Whisper • មិនប្រើ Gemini / Groq / API key")

st.info(
    "កំណែនេះប្រើ Whisper ក្នុងម៉ាស៊ីនមេ ដើម្បីស្ដាប់សំឡេង និងបង្កើត Subtitle។ "
    "វាមិនបកប្រែរឿងចិនទៅខ្មែរ និងមិនបង្កើតសំឡេង AI ខ្មែរទេ។ "
    "Streamlit Cloud អាចត្រូវការពេលយូរដើម្បីទាញយកម៉ូដែលលើកដំបូង។"
)

def run_ffmpeg(args):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run([exe, *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError((result.stderr or "FFmpeg failed")[-1800:])
    return result

def fix_text(s):
    return unicodedata.normalize("NFC", str(s or "")).strip()

def stamp(sec):
    sec = max(0.0, float(sec))
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def wrap_caption(text, max_chars=32):
    # Keep each Whisper segment intact as much as possible; avoid splitting Khmer graphemes.
    text = re.sub(r"\s+", " ", fix_text(text))
    if len(text) <= max_chars:
        return text
    words = text.split(" ")
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return r"\N".join(lines)

def srt_content(segments, max_chars):
    out = []
    for i, seg in enumerate(segments, 1):
        text = wrap_caption(seg.text, max_chars)
        if not text:
            continue
        out.extend([str(i), f"{stamp(seg.start)} --> {stamp(seg.end)}", text.replace(r"\N", "\n"), ""])
    return "\n".join(out)

def escape_ass(s):
    return fix_text(s).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")

uploaded = st.file_uploader(
    "ជ្រើសរើសវីដេអូ",
    type=["mp4", "mov", "mkv", "avi", "webm"],
    help="កំណត់ទំហំ upload របស់ Streamlit Cloud អាចមានកម្រិត។"
)

with st.expander("ការកំណត់ Subtitle", expanded=True):
    language = st.selectbox(
        "ភាសាសំឡេងដើម",
        ["ស្វ័យប្រវត្តិ", "ខ្មែរ", "ចិន", "អង់គ្លេស", "ថៃ", "វៀតណាម"],
        index=0
    )
    model_name = st.selectbox(
        "ទំហំម៉ូដែល Whisper (តូចជាង = លឿនជាង)",
        ["tiny", "base", "small"],
        index=0,
        help="tiny សមស្របជាងសម្រាប់ RAM តិច ប៉ុន្តែភាពត្រឹមត្រូវអាចទាបជាង។"
    )
    font_size = st.slider("ទំហំអក្សរ", 16, 42, 28)
    outline = st.slider("កម្រាស់គែមអក្សរ", 1, 5, 2)
    font_color = st.selectbox("ពណ៌អក្សរ", ["ស", "លឿង", "បៃតង", "ខៀវ"], index=0)
    max_chars = st.slider("ចំនួនតួអក្សរអតិបរមាក្នុងមួយបន្ទាត់", 20, 44, 32)

color_map = {"ស": "&H00FFFFFF", "លឿង": "&H0000FFFF", "បៃតង": "&H0000FF00", "ខៀវ": "&H00FF0000"}

if uploaded and st.button("🚀 បង្កើត Subtitle", type="primary", use_container_width=True):
    temp_dir = Path(tempfile.mkdtemp(prefix="khmer_caption_"))
    input_path = temp_dir / ("input_" + re.sub(r"[^A-Za-z0-9._-]", "_", uploaded.name))
    audio_path = temp_dir / "audio.wav"
    srt_path = temp_dir / "captions.srt"
    ass_path = temp_dir / "captions.ass"
    output_path = temp_dir / "captioned_video.mp4"
    try:
        with open(input_path, "wb") as f:
            f.write(uploaded.getbuffer())

        progress = st.progress(0, text="កំពុងដកសំឡេងចេញពីវីដេអូ…")
        run_ffmpeg(["-y", "-i", str(input_path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio_path)])
        progress.progress(10, text="កំពុងរៀបចំ Whisper Local…")

        from faster_whisper import WhisperModel
        # CPU/int8 limits RAM usage compared with loading a large GPU model.
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        lang_map = {"ខ្មែរ": "km", "ចិន": "zh", "អង់គ្លេស": "en", "ថៃ": "th", "វៀតណាម": "vi"}
        lang_code = lang_map.get(language)
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=lang_code,
            beam_size=1,
            vad_filter=True,
            word_timestamps=False,
            condition_on_previous_text=False
        )
        segments = []
        for seg in segments_iter:
            segments.append(seg)
            if len(segments) % 8 == 0:
                progress.progress(min(70, 10 + len(segments)), text=f"កំពុងស្ដាប់សំឡេង… បាន {len(segments)} ផ្នែក")
        if not segments:
            raise RuntimeError("Whisper មិនបានរកឃើញសំឡេងនិយាយទេ។ សូមពិនិត្យវីដេអូម្ដងទៀត។")

        srt_path.write_text(srt_content(segments, max_chars), encoding="utf-8")
        progress.progress(75, text="កំពុងបង្កើត Subtitle style…")

        # ASS subtitle style; preserve Khmer Unicode text.
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Battambang,{font_size},{color_map[font_color]},&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{outline},0,2,45,45,55,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        def ass_time(sec):
            cs = int(max(0, float(sec)) * 100)
            h, cs = divmod(cs, 360000)
            m, cs = divmod(cs, 6000)
            s, cs = divmod(cs, 100)
            return f"{h}:{m:02}:{s:02}.{cs:02}"
        events = []
        for seg in segments:
            txt = escape_ass(wrap_caption(seg.text, max_chars))
            if txt:
                events.append(f"Dialogue: 0,{ass_time(seg.start)},{ass_time(seg.end)},Default,,0,0,0,,{txt}")
        ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")

        progress.progress(82, text="កំពុងដាក់ Subtitle លើវីដេអូ…")
        # FFmpeg subtitle filter uses an absolute path; escape Windows/drive punctuation defensively.
        ass_filter_path = str(ass_path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        run_ffmpeg(["-y", "-i", str(input_path), "-vf", f"ass='{ass_filter_path}'", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-c:a", "copy", "-movflags", "+faststart", str(output_path)])
        progress.progress(100, text="រួចរាល់!")

        st.success(f"បានបង្កើត Subtitle ចំនួន {len(segments)} ផ្នែក។ ភាសាដែល Whisper ស្គាល់៖ {info.language}")
        st.video(str(output_path))
        st.download_button(
            "⬇️ ទាញយកវីដេអូមាន Subtitle",
            data=output_path.read_bytes(),
            file_name="khmer_auto_caption.mp4",
            mime="video/mp4",
            use_container_width=True
        )
        st.download_button(
            "⬇️ ទាញយកឯកសារ Subtitle (.srt)",
            data=srt_path.read_bytes(),
            file_name="captions.srt",
            mime="application/x-subrip",
            use_container_width=True
        )
    except Exception as e:
        st.error("ដំណើរការមិនបានជោគជ័យ។")
        st.code(str(e))
        st.caption("លើ Streamlit Cloud ម៉ូដែល Whisper អាចត្រូវការពេលដំបូង និង RAM/CPU គ្រប់គ្រាន់។ សាកល្បងម៉ូដែល tiny ប្រសិនបើអស់ធនធាន។")

st.divider()
st.caption("កំណែ Local-only នេះមិនមាន API key, Gemini, Groq, Google Translate ឬ Edge TTS ទេ។ Whisper model ត្រូវទាញយកមកម៉ាស៊ីនមេនៅពេលប្រើដំបូង។")
