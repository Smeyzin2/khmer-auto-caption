
import os
import re
import subprocess
import tempfile
import urllib.request
from datetime import timedelta

import imageio_ffmpeg
import streamlit as st
from google import genai

st.set_page_config(
    page_title="Khmer Auto Caption",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 Khmer Auto Caption")
st.write("បង្កើតអក្សរខ្មែរតាមពេលដោយ Gemini AI")

MODEL = "gemini-3.5-transcribe"

FONTS = {
    "Noto Sans Khmer": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskhmer/NotoSansKhmer%5Bwdth%2Cwght%5D.ttf",
        "file": "NotoSansKhmer.ttf",
        "name": "Noto Sans Khmer",
    },
    "Noto Serif Khmer": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifkhmer/NotoSerifKhmer%5Bwdth%2Cwght%5D.ttf",
        "file": "NotoSerifKhmer.ttf",
        "name": "Noto Serif Khmer",
    },
    "Battambang": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/battambang/Battambang-Regular.ttf",
        "file": "Battambang.ttf",
        "name": "Battambang",
    },
    "Moul": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/moul/Moul-Regular.ttf",
        "file": "Moul.ttf",
        "name": "Moul",
    },
    "Kantumruy Pro": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/kantumruypro/KantumruyPro%5Bwght%5D.ttf",
        "file": "KantumruyPro.ttf",
        "name": "Kantumruy Pro",
    },
    "Khmer": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/khmer/Khmer.ttf",
        "file": "Khmer.ttf",
        "name": "Khmer",
    },
}


def run_ffmpeg(args):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    return subprocess.run(
        [exe, "-y"] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def escape_path(path):
    return (
        os.path.abspath(path)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def srt_time(seconds):
    ms = max(0, int(float(seconds) * 1000))
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return (
        f"{hours:02}:{minutes:02}:"
        f"{seconds:02},{ms:03}"
    )


def get_video_duration(video_path):
    result = run_ffmpeg([
        "-i", video_path,
        "-f", "null",
        "-"
    ])
    # FFmpeg null output does not reliably expose duration.
    # Use ffprobe bundled with imageio-ffmpeg if available.
    import imageio_ffmpeg
    import shutil

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    ffprobe_path = os.path.join(
        os.path.dirname(ffmpeg_path),
        "ffprobe"
    )

    if os.path.exists(ffprobe_path):
        probe = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if probe.returncode == 0:
            try:
                return float(probe.stdout.strip())
            except ValueError:
                pass

    # Fallback: use ffmpeg output to find duration.
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run(
        [exe, "-i", video_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        probe.stderr,
    )
    if match:
        h, m, s = match.groups()
        return int(h) * 3600 + int(m) * 60 + float(s)

    return 10.0


def parse_seconds(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    value = str(value).strip()
    match = re.search(r"(\d+(?:\.\d+)?)", value)

    if match:
        return float(match.group(1))

    return None


def download_font(url, path):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()

    if len(data) < 1000:
        raise RuntimeError(
            "ឯកសារ Font មិនត្រឹមត្រូវ។ សូមសាក Font ផ្សេង។"
        )

    with open(path, "wb") as f:
        f.write(data)


def extract_audio(video_path, audio_path):
    run_ffmpeg([
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        audio_path,
    ])


def get_word_annotations(interaction):
    words = []

    for step in getattr(interaction, "steps", []) or []:
        for content in getattr(step, "content", []) or []:
            for annotation in (
                getattr(content, "annotations", []) or []
            ):
                if getattr(annotation, "type", None) != "word_info":
                    continue

                text = (
                    getattr(annotation, "text", None)
                    or getattr(annotation, "word", None)
                    or ""
                ).strip()

                start = parse_seconds(
                    getattr(annotation, "start_offset", None)
                )
                end = parse_seconds(
                    getattr(annotation, "end_offset", None)
                )

                if text and start is not None and end is not None:
                    if end > start:
                        words.append((start, end, text))

    words.sort(key=lambda x: x[0])
    return words


def group_words(words, max_chars=34, max_duration=3.5):
    captions = []
    current_words = []
    current_start = None
    current_end = None
    current_text = ""

    for start, end, word in words:
        candidate = (
            word if not current_text
            else current_text + " " + word
        )

        exceeds_chars = len(candidate) > max_chars
        exceeds_time = (
            current_start is not None
            and end - current_start > max_duration
        )

        if current_words and (exceeds_chars or exceeds_time):
            captions.append((
                current_start,
                current_end,
                current_text.strip(),
            ))
            current_words = []
            current_start = None
            current_text = ""

        if current_start is None:
            current_start = start

        current_end = end
        current_words.append(word)
        current_text = (
            word if not current_text
            else current_text + " " + word
        )

    if current_words:
        captions.append((
            current_start,
            current_end,
            current_text.strip(),
        ))

    # Remove overlapping caption times.
    fixed = []
    for start, end, text in captions:
        if fixed and start < fixed[-1][1]:
            prev_start, prev_end, prev_text = fixed[-1]
            fixed[-1] = (
                prev_start,
                max(prev_start + 0.1, start),
                prev_text,
            )
        if end > start:
            fixed.append((start, end, text))

    return fixed


def fallback_captions(transcript, duration):
    text = re.sub(r"\s+", " ", transcript).strip()
    if not text:
        return []

    # Khmer text may not contain spaces between every word.
    pieces = []
    while len(text) > 34:
        cut = text.rfind(" ", 0, 34)
        if cut < 10:
            cut = 34
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()

    if text:
        pieces.append(text)

    total = sum(max(1, len(x)) for x in pieces)
    cursor = 0.0
    captions = []

    for i, piece in enumerate(pieces):
        if i == len(pieces) - 1:
            end = max(duration, cursor + 0.2)
        else:
            end = cursor + duration * len(piece) / total

        captions.append((cursor, end, piece))
        cursor = end

    return captions


def transcribe_with_gemini(api_key, audio_path):
    client = genai.Client(api_key=api_key)

    audio_file = client.files.upload(file=audio_path)

    interaction = client.interactions.create(
        model=MODEL,
        input=[
            {
                "type": "audio",
                "uri": audio_file.uri,
                "mime_type": audio_file.mime_type,
            }
        ],
        generation_config={
            "transcription_config": {
                "language_codes": ["km-KH"],
                "mode": {
                    "type": "verbatim",
                    "timestamp_granularities": ["word"],
                },
            }
        },
    )

    transcript = (
        getattr(interaction, "output_text", None) or ""
    ).strip()

    words = get_word_annotations(interaction)
    return transcript, words


api_key = st.text_input(
    "Gemini API Key",
    type="password",
    help="បញ្ចូល API key របស់អ្នក។ កុំចែករំលែក key ជាមួយអ្នកដទៃ។",
)

st.caption(
    "ទទួល API key តាម Google AI Studio: "
    "https://aistudio.google.com/apikey"
)

st.subheader("🎨 រចនាប័ទ្មអក្សរ")

font_choice = st.selectbox(
    "ជ្រើសរើស Font ខ្មែរ",
    list(FONTS.keys()),
)

font_size = st.slider(
    "ទំហំអក្សរ", 16, 36, 24
)

outline_size = st.slider(
    "កម្រាស់គែមអក្សរ", 1, 5, 2
)

font_color = st.selectbox(
    "ពណ៌អក្សរ",
    ["ស", "លឿង", "បៃតង", "ខៀវ"],
)

color_codes = {
    "ស": "&H00FFFFFF",
    "លឿង": "&H0000FFFF",
    "បៃតង": "&H0000FF00",
    "ខៀវ": "&H00FF0000",
}

uploaded = st.file_uploader(
    "ជ្រើសរើសវីដេអូ",
    type=["mp4", "mov", "mkv", "avi", "webm"],
)

if uploaded:
    video_bytes = uploaded.getvalue()
    st.video(video_bytes)

    if st.button(
        "🚀 បង្កើតវីដេអូមានអក្សរខ្មែរ",
        type="primary",
        use_container_width=True,
    ):
        if not api_key.strip():
            st.error("សូមបញ្ចូល Gemini API Key ជាមុនសិន។")
            st.stop()

        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "input.mp4")
            audio_path = os.path.join(folder, "audio.mp3")
            srt_path = os.path.join(folder, "khmer.srt")
            output_path = os.path.join(
                folder, "khmer_subtitle.mp4"
            )

            font = FONTS[font_choice]
            font_path = os.path.join(folder, font["file"])

            with open(source, "wb") as f:
                f.write(video_bytes)

            try:
                with st.spinner("១/៤ កំពុងទាញយក Font..."):
                    download_font(font["url"], font_path)

                with st.spinner("២/៤ កំពុងដកសំឡេងចេញពីវីដេអូ..."):
                    extract_audio(source, audio_path)
                    duration = get_video_duration(source)

                with st.spinner(
                    "៣/៤ Gemini កំពុងបម្លែងសំឡេងជាអក្សរ..."
                ):
                    transcript, words = transcribe_with_gemini(
                        api_key.strip(), audio_path
                    )

                if not transcript:
                    st.error(
                        "Gemini មិនបានបញ្ជូនអត្ថបទមកទេ។"
                    )
                    st.stop()

                captions = group_words(words)

                if not captions:
                    captions = fallback_captions(
                        transcript, duration
                    )

                lines = []
                for i, (start, end, text) in enumerate(
                    captions, start=1
                ):
                    start = max(0.0, start)
                    end = max(start + 0.15, end)

                    lines.extend([
                        str(i),
                        f"{srt_time(start)} --> {srt_time(end)}",
                        text,
                        "",
                    ])

                with open(
                    srt_path, "w", encoding="utf-8-sig"
                ) as f:
                    f.write("\n".join(lines))

                with st.spinner(
                    "៤/៤ កំពុងបង្កប់អក្សរចូល MP4..."
                ):
                    subtitles = escape_path(srt_path)
                    fontsdir = escape_path(folder)

                    vf = (
                        f"subtitles=filename='{subtitles}'"
                        f":fontsdir='{fontsdir}'"
                        f":force_style='FontName={font['name']},"
                        f"FontSize={font_size},"
                        f"PrimaryColour={color_codes[font_color]},"
                        f"Outline={outline_size},"
                        "OutlineColour=&H00000000,"
                        "Shadow=1,Alignment=2,MarginV=35'"
                    )

                    run_ffmpeg([
                        "-i", source,
                        "-vf", vf,
                        "-c:v", "libx264",
                        "-preset", "ultrafast",
                        "-crf", "28",
                        "-c:a", "aac",
                        "-b:a", "96k",
                        "-movflags", "+faststart",
                        output_path,
                    ])

                with open(output_path, "rb") as f:
                    output_data = f.read()

                st.success("បង្កើតវីដេអូរួចរាល់!")
                st.subheader("🎬 វីដេអូមានអក្សរខ្មែរ")
                st.video(output_data)

                st.download_button(
                    "⬇️ ទាញយក MP4",
                    data=output_data,
                    file_name="khmer_subtitle.mp4",
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True,
                )

                st.download_button(
                    "⬇️ ទាញយកអក្សរ SRT",
                    data="\n".join(lines),
                    file_name="khmer_subtitle.srt",
                    mime="text/plain",
                    use_container_width=True,
                )

                with st.expander("មើលអត្ថបទដែល Gemini ស្គាល់"):
                    st.write(transcript)

                with st.expander("មើលពេលវេលាអក្សរ"):
                    st.write(f"ចំនួនឃ្លា៖ {len(captions)}")
                    st.code("\n".join(
                        f"{srt_time(a)} --> {srt_time(b)}  {t}"
                        for a, b, t in captions[:50]
                    ))

            except Exception as e:
                st.error("មានបញ្ហាក្នុងការបង្កើតវីដេអូ។")
                st.code(str(e))

else:
    st.info("សូមជ្រើសរើសវីដេអូជាមុនសិន។")
