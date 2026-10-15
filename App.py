import os
import tempfile
import subprocess
from pathlib import Path

import gradio as gr
import torch
from transformers import pipeline

# Khmer speech recognition model. The first run downloads model files.
MODEL_ID = os.getenv("WHISPER_MODEL", "sengtha/whisper-base-khmer")
_asr = None


def get_asr():
    global _asr
    if _asr is None:
        device = 0 if torch.cuda.is_available() else -1
        _asr = pipeline(
            "automatic-speech-recognition",
            model=MODEL_ID,
            device=device,
        )
    return _asr


def srt_timestamp(seconds):
    seconds = max(0.0, float(seconds))
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def extract_audio(input_path, output_path):
    # Requires ffmpeg (available in most Spaces images; install via apt if needed).
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-acodec", "pcm_s16le", output_path,
    ]
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError("មិនអាចស្រង់សំឡេងពីឯកសារបានទេ។ សូមសាកល្បងឯកសារសំឡេង WAV/MP3 ឬវីដេអូផ្សេង។")
    return output_path


def transcribe(media_file):
    if not media_file:
        raise gr.Error("សូមជ្រើសឯកសារសំឡេង ឬវីដេអូជាមុន។")

    input_path = media_file
    suffix = Path(input_path).suffix.lower()
    temp_audio = None

    try:
        if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}:
            fd, temp_audio = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            extract_audio(input_path, temp_audio)
            input_path = temp_audio

        asr = get_asr()
        result = asr(input_path, return_timestamps=True, chunk_length_s=25)
        chunks = result.get("chunks") or []

        srt_lines = []
        plain_lines = []
        index = 1

        for chunk in chunks:
            text = (chunk.get("text") or "").strip()
            timestamp = chunk.get("timestamp") or (None, None)
            start, end = timestamp
            if not text:
                continue
            plain_lines.append(text)
            if start is None:
                start = 0
            if end is None:
                end = float(start) + 3.0
            if end <= start:
                end = float(start) + 1.0
            srt_lines.extend([
                str(index),
                f"{srt_timestamp(start)} --> {srt_timestamp(end)}",
                text,
                "",
            ])
            index += 1

        # Some ASR pipelines may return only text without chunk timestamps.
        if not plain_lines:
            text = (result.get("text") or "").strip()
            if text:
                plain_lines.append(text)
                srt_lines = ["1", "00:00:00,000 --> 00:00:05,000", text, ""]

        if not plain_lines:
            raise gr.Error("AI មិនបានរកឃើញអត្ថបទទេ។ សូមសាកល្បងឯកសារផ្សេង។")

        txt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
        txt_path.write("\n".join(plain_lines))
        txt_path.close()

        srt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode="w", encoding="utf-8")
        srt_path.write("\n".join(srt_lines).strip() + "\n")
        srt_path.close()

        return "\n".join(plain_lines), srt_path.name, txt_path.name

    except gr.Error:
        raise
    except Exception as exc:
        raise gr.Error(f"ដំណើរការមិនបាន៖ {exc}")
    finally:
        if temp_audio and os.path.exists(temp_audio):
            os.remove(temp_audio)


with gr.Blocks(title="Smey Khmer Caption") as demo:
    gr.Markdown(
        """
        # Smey Khmer Caption
        បញ្ចូលសំឡេង ឬវីដេអូ ដើម្បីបង្កើតអត្ថបទខ្មែរ និងឯកសារ Subtitle `.srt`។

        **ចំណាំ៖** ការប្រើលើកដំបូងត្រូវទាញយកម៉ូដែល AI ហើយអាចចំណាយពេល និងប្រើអង្គចងចាំច្រើន។ ការប្រើប្រាស់ម៉ាស៊ីន Hosting អាស្រ័យលើកម្រិតសេវាឥតគិតថ្លៃរបស់កន្លែងដាក់កម្មវិធី។
        """
    )
    media = gr.File(
        label="ជ្រើសឯកសារសំឡេង ឬវីដេអូ",
        type="filepath",
        file_types=["audio", "video"],
    )
    run_btn = gr.Button("បង្កើត Subtitle ខ្មែរ", variant="primary")
    transcript = gr.Textbox(label="អត្ថបទដែល AI ស្គាល់", lines=8)
    srt_file = gr.File(label="ទាញយក Subtitle (.srt)")
    txt_file = gr.File(label="ទាញយកអត្ថបទ (.txt)")
    run_btn.click(
        fn=transcribe,
        inputs=[media],
        outputs=[transcript, srt_file, txt_file],
    )

if __name__ == "__main__":
    demo.queue().launch()
