import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
import imageio_ffmpeg

APP_TITLE = "Khmer Auto Caption — Local Whisper"
st.set_page_config(page_title=APP_TITLE, page_icon="🎬", layout="centered")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Battambang:wght@400;700&display=swap');
html, body, [class*="css"] { font-family: 'Battambang', sans-serif; }
.block-container {max-width: 900px; padding-top: 1.3rem;}
div.stButton > button[kind="primary"] {border-radius: 12px; min-height: 3rem; font-weight: 700;}
div[data-testid="stFileUploader"] {border-radius: 14px;}
.link-panel {padding: 14px 16px; border: 1px solid rgba(120,120,120,.25); border-radius: 14px;}
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

if "link_preview" not in st.session_state:
    st.session_state.link_preview = None
if "link_preview_url" not in st.session_state:
    st.session_state.link_preview_url = ""

st.subheader("📥 បញ្ចូលវីដេអូ")
source_mode = st.radio(
    "ជ្រើសរើសវិធីបញ្ចូល",
    ["📱 Upload ពីទូរស័ព្ទ", "🔗 ស្វែងរក/ទាញយកតាមលីង"],
    horizontal=False,
    label_visibility="collapsed"
)

uploaded = None
video_url = ""
if source_mode == "📱 Upload ពីទូរស័ព្ទ":
    uploaded = st.file_uploader(
        "ជ្រើសរើសវីដេអូពីទូរស័ព្ទ",
        type=["mp4", "mov", "mkv", "avi", "webm", "mpeg", "mpg"],
        help="ទំហំ upload អាស្រ័យលើកម្រិត Streamlit Cloud។"
    )
else:
    st.markdown('<div class="link-panel">🔗 ស្វែងរកវីដេអូដោយលីង</div>', unsafe_allow_html=True)
    video_url = st.text_input(
        "បញ្ចូល ឬបិទភ្ជាប់លីងវីដេអូ",
        placeholder="https://www.tiktok.com/... ឬ https://www.youtube.com/watch?v=...",
        help="បញ្ចូលលីងសាធារណៈដែលអ្នកមានសិទ្ធិមើល និងទាញយក។"
    ).strip()
    if st.button("🔎 ស្វែងរកវីដេអូ", use_container_width=True):
        try:
            parsed = urlparse(video_url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                st.error("សូមបញ្ចូលលីងត្រឹមត្រូវដែលចាប់ផ្ដើមដោយ https:// ឬ http://")
                st.session_state.link_preview = None
                st.session_state.link_preview_url = ""
            else:
                import yt_dlp
                with st.spinner("កំពុងស្វែងរកព័ត៌មានវីដេអូ…"):
                    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                            "noplaylist": True, "socket_timeout": 25,
                            "extractor_retries": 1, "retries": 1}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                st.session_state.link_preview = {
                    "title": info.get("title") or "វីដេអូគ្មានចំណងជើង",
                    "duration": info.get("duration"),
                    "thumbnail": info.get("thumbnail"),
                    "webpage_url": info.get("webpage_url") or video_url,
                    "description": (info.get("description") or "")[:400],
                    "extractor": info.get("extractor_key") or info.get("extractor") or "Video",
                }
                st.session_state.link_preview_url = video_url
        except Exception as e:
            st.session_state.link_preview = None
            st.session_state.link_preview_url = ""
            st.error("រកមិនឃើញវីដេអូពីលីងនេះទេ។ សូមពិនិត្យលីង ឬសាកល្បងលីងសាធារណៈផ្សេងទៀត។")
            st.caption(str(e)[:500])

    preview = st.session_state.get("link_preview")
    if preview and st.session_state.get("link_preview_url") == video_url:
        st.markdown("---")
        st.subheader("🎬 វីដេអូដែលបានរកឃើញ")
        if preview.get("thumbnail"):
            st.image(preview["thumbnail"], use_container_width=True)
        st.markdown(f"**{preview['title']}**")
        if preview.get("duration"):
            duration = int(preview["duration"])
            st.caption(f"រយៈពេល៖ {duration // 60} នាទី {duration % 60} វិនាទី · ប្រភព៖ {preview['extractor']}")
        if preview.get("description"):
            with st.expander("ព័ត៌មានវីដេអូ"):
                st.write(preview["description"])
        st.video(preview["webpage_url"])
        st.success("បើវីដេអូត្រឹមត្រូវ អ្នកអាចចុច «បង្កើត Subtitle» ដើម្បីបន្ត។")
    else:
        st.caption("បញ្ចូលលីង រួចចុច «ស្វែងរកវីដេអូ» សិន។ កម្មវិធីនឹងបង្ហាញព័ត៌មាន និងវីដេអូឱ្យមើលមុន។")


def download_video_from_url(url, destination, status_box):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("សូមបញ្ចូលលីងពេញដែលចាប់ផ្ដើមដោយ https:// ឬ http://")
    # Direct video file URLs can be fetched without yt-dlp.
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mpeg", ".mpg"}:
        import requests
        with requests.get(url, stream=True, timeout=(15, 60), allow_redirects=True) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", "0") or 0)
            limit = 1024 * 1024 * 1024
            if total and total > limit:
                raise ValueError("វីដេអូលើស 1GB។ សូមប្រើវីដេអូតូចជាងនេះ។")
            downloaded = 0
            with open(destination, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded > limit:
                            raise ValueError("វីដេអូលើស 1GB។ សូមប្រើវីដេអូតូចជាងនេះ។")
                        file.write(chunk)
        return
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("មិនទាន់ដំឡើង yt-dlp ទេ។ សូមបន្ថែម yt-dlp ក្នុង requirements.txt។") from exc
    status_box.info("កំពុងទាញយកវីដេអូពីលីង…")
    opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(destination.with_suffix(".%(ext)s")),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": 1024 * 1024 * 1024,
        "merge_output_format": "mp4",
        "retries": 2,
        "socket_timeout": 30,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    # yt-dlp may choose a container extension depending on source.
    candidates = [destination.with_suffix(ext) for ext in (".mp4", ".mkv", ".webm", ".mov", ".avi")]
    found = next((candidate for candidate in candidates if candidate.exists() and candidate.stat().st_size), None)
    if found is None:
        # Some yt-dlp versions honor the full requested template differently.
        matches = list(destination.parent.glob(destination.stem + ".*"))
        found = next((candidate for candidate in matches if candidate.is_file() and candidate.stat().st_size), None)
    if found is None:
        raise RuntimeError("ទាញយកមិនបាន។ សូមពិនិត្យលីង ឬសាកល្បងលីងវីដេអូផ្ទាល់។")
    if found != destination:
        found.replace(destination)

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

with st.expander("🎙️ មុខងារ AI Dubbing", expanded=False):
    make_dubbing = st.checkbox("បកប្រែសំឡេងចិនទៅខ្មែរ និងបង្កើតសំឡេងខ្មែរ", value=False)
    keep_original_audio = st.checkbox("លាយសំឡេងដើមស្រាលៗក្រោមសំឡេងខ្មែរ", value=False)
    st.caption("កែឱ្យលឿនឡើងដោយបញ្ចូលឃ្លាខ្លីៗជាក្រុម មុនបកប្រែ និងបង្កើតសំឡេង។ Streamlit Cloud អាចនៅតែយឺតពេលប្រើ CPU/RAM ច្រើន។ សូមសាកល្បងវីដេអូខ្លីជាមុន។")

def _nllb_translate(text, tokenizer, model, **kwargs):
    import torch
    encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        generated = model.generate(
            **encoded,
            forced_bos_token_id=tokenizer.convert_tokens_to_ids("khm_Khmr"),
            max_length=kwargs.get("max_length", 256),
            num_beams=kwargs.get("num_beams", 2),
        )
    return [{"translation_text": tokenizer.batch_decode(generated, skip_special_tokens=True)[0]}]

def translate_chinese_to_khmer(text, translator):
    text = fix_text(text)
    if not text:
        return ""
    result = translator(text, max_length=256, num_beams=2)
    return fix_text(result[0]["translation_text"])

def synthesize_khmer(text, tokenizer, tts_model, output_wav):
    import torch
    import numpy as np
    import soundfile as sf
    text = fix_text(text)
    if not text:
        return False
    inputs = tokenizer(text, return_tensors="pt")
    with torch.no_grad():
        audio = tts_model(**inputs).waveform.squeeze().cpu().numpy()
    audio = np.asarray(audio, dtype=np.float32)
    sf.write(str(output_wav), audio, int(tts_model.config.sampling_rate))
    return True

color_map = {"ស": "&H00FFFFFF", "លឿង": "&H0000FFFF", "បៃតង": "&H0000FF00", "ខៀវ": "&H00FF0000"}

has_input = uploaded is not None if source_mode == "📱 Upload ពីទូរស័ព្ទ" else (
    bool(video_url) and bool(st.session_state.get("link_preview"))
    and st.session_state.get("link_preview_url") == video_url
)
if has_input and st.button("🚀 បង្កើត Subtitle", type="primary", use_container_width=True):
    temp_dir = Path(tempfile.mkdtemp(prefix="khmer_caption_"))
    input_path = temp_dir / "input_video.mp4"
    audio_path = temp_dir / "audio.wav"
    srt_path = temp_dir / "captions.srt"
    ass_path = temp_dir / "captions.ass"
    output_path = temp_dir / "captioned_video.mp4"
    try:
        if source_mode == "📱 Upload ពីទូរស័ព្ទ":
            with open(input_path, "wb") as f:
                f.write(uploaded.getbuffer())
        else:
            download_video_from_url(video_url, input_path, st)
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

        translated_segments = []
        dubbed_audio_path = temp_dir / "khmer_dubbing.wav"
        if make_dubbing:
            if language not in ("ចិន", "ស្វ័យប្រវត្តិ"):
                st.warning("Dubbing នេះរំពឹងថាសំឡេងដើមជាភាសាចិន។ សូមជ្រើសរើស 'ចិន' ឬ 'ស្វ័យប្រវត្តិ'។")
            progress.progress(72, text="កំពុងផ្ទុកម៉ូដែលបកប្រែ និងសំឡេងខ្មែរ…")
            import torch
            import numpy as np
            import soundfile as sf
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, VitsModel

            translation_name = "facebook/nllb-200-distilled-600M"
            translator_tokenizer = AutoTokenizer.from_pretrained(translation_name, src_lang="zho_Hans")
            translator_model = AutoModelForSeq2SeqLM.from_pretrained(translation_name)
            translator_model.eval()
            tokenizer = AutoTokenizer.from_pretrained("khmerttsopensource/khmer-tts")
            tts_model = VitsModel.from_pretrained("khmerttsopensource/khmer-tts")
            tts_model.eval()

            tts_dir = temp_dir / "tts_parts"
            tts_dir.mkdir()
            audio_parts = []
            translated_segments = []
            total = max(1, len(segments))
            # Merge short Whisper segments into larger speech chunks. This reduces
            # the number of translation and TTS model calls, which is much faster on CPU.
            chunks = []
            current = []
            chunk_start = None
            chunk_end = None
            chunk_chars = 0
            for seg in segments:
                seg_text = fix_text(seg.text)
                if not seg_text:
                    continue
                if current and (
                    float(seg.end) - float(chunk_start) >= 7.0
                    or chunk_chars + len(seg_text) > 220
                ):
                    chunks.append((chunk_start, chunk_end, current))
                    current, chunk_chars = [], 0
                    chunk_start = None
                if not current:
                    chunk_start = float(seg.start)
                current.append(seg)
                chunk_end = float(seg.end)
                chunk_chars += len(seg_text)
            if current:
                chunks.append((chunk_start, chunk_end, current))

            total_chunks = max(1, len(chunks))
            for idx, (start_sec, end_sec, chunk_segments) in enumerate(chunks):
                original_text = " ".join(fix_text(seg.text) for seg in chunk_segments)
                translated = translate_chinese_to_khmer(
                    original_text,
                    lambda text, **kwargs: _nllb_translate(text, translator_tokenizer, translator_model, **kwargs)
                )
                translated_segments.append((start_sec, end_sec, translated))
                part = tts_dir / f"part_{idx:05d}.wav"
                if translated:
                    synthesize_khmer(translated, tokenizer, tts_model, part)
                    audio_parts.append((float(start_sec), float(end_sec), part))
                progress.progress(
                    72 + int(18 * (idx + 1) / total_chunks),
                    text=f"កំពុងបង្កើតសំឡេងខ្មែរ… {idx + 1}/{total_chunks} ផ្នែក"
                )

            # Place each spoken Khmer clip at the matching original segment start time.
            # Mix clips on a silent timeline; optional original audio is mixed back later.
            if not audio_parts:
                raise RuntimeError("មិនអាចបង្កើតសំឡេងខ្មែរបានទេ។")
            max_end = max(float(seg.end) for seg in segments)
            inputs_ffmpeg = []
            filters = []
            for i, (start_sec, end_sec, part) in enumerate(audio_parts):
                inputs_ffmpeg.extend(["-i", str(part)])
                delay_ms = max(0, int(start_sec * 1000))
                filters.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},aresample=16000[a{i}]")
            mix_inputs = "".join(f"[a{i}]" for i in range(len(audio_parts)))
            filters.append(f"{mix_inputs}amix=inputs={len(audio_parts)}:duration=longest:normalize=0,atrim=0:{max_end + 0.5}[dub]")
            run_ffmpeg(["-y", *inputs_ffmpeg, "-filter_complex", ";".join(filters), "-map", "[dub]", "-ac", "1", "-ar", "16000", str(dubbed_audio_path)])
            del translator_model, translator_tokenizer, tts_model, tokenizer
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

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
        caption_items = translated_segments if make_dubbing and translated_segments else [(seg.start, seg.end, seg.text) for seg in segments]
        for start_time, end_time, caption_text in caption_items:
            txt = escape_ass(wrap_caption(caption_text, max_chars))
            if txt:
                events.append(f"Dialogue: 0,{ass_time(start_time)},{ass_time(end_time)},Default,,0,0,0,,{txt}")
        ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")

        progress.progress(82, text="កំពុងដាក់ Subtitle លើវីដេអូ…")
        # FFmpeg subtitle filter uses an absolute path; escape Windows/drive punctuation defensively.
        ass_filter_path = str(ass_path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        run_ffmpeg(["-y", "-i", str(input_path), "-vf", f"ass='{ass_filter_path}'", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-c:a", "copy", "-movflags", "+faststart", str(output_path)])
        final_output = output_path
        if make_dubbing and dubbed_audio_path.exists():
            dubbed_output = temp_dir / "khmer_dubbed_video.mp4"
            if keep_original_audio:
                run_ffmpeg(["-y", "-i", str(output_path), "-i", str(dubbed_audio_path), "-filter_complex", "[0:a]volume=0.18[orig];[1:a]volume=1.0[dub];[orig][dub]amix=inputs=2:duration=first:normalize=0[mix]", "-map", "0:v:0", "-map", "[mix]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(dubbed_output)])
            else:
                run_ffmpeg(["-y", "-i", str(output_path), "-i", str(dubbed_audio_path), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(dubbed_output)])
            final_output = dubbed_output
        progress.progress(100, text="រួចរាល់!")

        st.success(f"បានបង្កើត Subtitle ចំនួន {len(segments)} ផ្នែក។ ភាសាដែល Whisper ស្គាល់៖ {info.language}")
        st.video(str(final_output))
        st.download_button(
            "⬇️ ទាញយកវីដេអូមាន Subtitle" + (" និងសំឡេងខ្មែរ" if make_dubbing else ""),
            data=final_output.read_bytes(),
            file_name="khmer_dubbed_video.mp4" if make_dubbing else "khmer_auto_caption.mp4",
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
