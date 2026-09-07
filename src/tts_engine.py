"""
Module: tts_engine.py
Description: Động cơ tổng hợp giọng đọc Text-To-Speech (Microsoft Edge Neural TTS & EverAI Multilingual API).
"""

import os
import sys
import json
import re
import asyncio
import time
import requests
from pathlib import Path
from typing import List, Dict, Any

try:
    from . import config
except (ImportError, ValueError):
    import config

EVERAI_BASE_URL = "https://www.everai.vn/api/v1/tts"


import subprocess

def clean_text_for_tts(text: str) -> str:
    """Chuẩn hóa văn bản, làm sạch ký tự đặc biệt, dấu gạch nối và ký hiệu code/toán học để giọng đọc mượt mà, ngắt nghỉ sư phạm."""
    if not text:
        return "Nội dung slide bài giảng."

    # Chuẩn hóa mọi biến thể dấu gạch ngang (em-dash, en-dash, hyphen) thành dấu phẩy
    text = re.sub(r'[\u2012\u2013\u2014\u2015\u2212\-]+', ', ', text)

    # Chuẩn hóa dấu ngoặc kép / đơn cong & thẳng
    text = re.sub(r'[\u2018\u2019\'\`]', ' ', text)
    text = re.sub(r'[\u201C\u201D\"]', ' ', text)

    # Ký tự toán học & biểu tượng
    text = text.replace("%", " phần trăm ")
    text = text.replace("&", " và ")
    text = text.replace("=", " gán bằng ")
    text = text.replace("+", " cộng ")
    text = text.replace(":", ", ")
    text = text.replace(";", ", ")
    text = text.replace("→", " chuyển thành ")
    text = text.replace("←", " từ ")
    text = text.replace("✓", " ")
    text = text.replace("⚡", " ")
    text = text.replace("◈", " ")
    text = re.sub(r'[Σ∑]', ' tổng ', text)
    text = re.sub(r'[•·]', ' ', text)

    # Sửa chữ viết tắt có dấu chấm: D.E.E.P -> DEEP
    text = re.sub(r'\b([A-Za-z])\.([A-Za-z])\.([A-Za-z])\.([A-Za-z])\b', r'\1\2\3\4', text)
    text = re.sub(r'\b([A-Za-z])\.([A-Za-z])\.([A-Za-z])\b', r'\1\2\3', text)
    text = re.sub(r'\b([A-Za-z])\.([A-Za-z])\b', r'\1\2', text)

    # Loại bỏ code blocks, markdown symbols, dấu ngoặc
    text = re.sub(r'[\*\#\_\[\]\(\)\{\}\<\>\/\\\|\~\^\@\$]', ' ', text)

    # Tách dấu chấm trong tên biến/thư viện (ví dụ numpy.array -> numpy array, .shape -> shape)
    text = re.sub(r'(?<=\w)\.(?=\w)', ' ', text)
    text = re.sub(r'\.(?=[a-zA-Z])', ' ', text)

    # Bảo vệ dấu chấm lửng
    text = re.sub(r'\.{3,}', ' ___PAUSE___ ', text)
    text = text.replace('…', ' ___PAUSE___ ')

    # Chuẩn hóa khoảng trắng quanh dấu câu
    text = re.sub(r'\s*,\s*', ', ', text)
    text = re.sub(r'\s*\.\s*', '. ', text)
    text = re.sub(r'\s*!\s*', '! ', text)
    text = re.sub(r'\s*\?\s*', '? ', text)

    # Khôi phục dấu ngắt nhịp
    text = re.sub(r'\s*___PAUSE___\s*', ', ', text)

    # Tránh lặp dấu phẩy hoặc chấm thừa
    text = re.sub(r',\s*,+', ', ', text)
    text = re.sub(r'\.\s*\.+', '. ', text)
    text = re.sub(r',\s*\.', '.', text)
    text = re.sub(r'\.\s*,', ',', text)
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) < 3:
        return "Nội dung slide bài giảng tiếp theo."
    return text


def synthesize_gtts_fallback(text: str, output_path: Path) -> bool:
    """Fallback an toàn bằng gTTS nếu kết nối EdgeTTS gặp sự cố mạng."""
    from gtts import gTTS
    cleaned = clean_text_for_tts(text)
    tts = gTTS(text=cleaned, lang='vi')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tts.save(str(output_path.resolve()))
    return True


async def _synthesize_single_unit(text: str, voice: str, out_path: Path, desired_rate: str = "-10%") -> bool:
    """Thử tổng hợp một câu/đoạn qua EdgeTTS với các mức tốc độ dự phòng nếu Azure từ chối."""
    import edge_tts
    rates_to_try = [desired_rate, "-5%", "+0%", None]
    tmp_path = out_path.with_suffix(".tmp.mp3")

    for r in rates_to_try:
        if tmp_path.exists():
            try: tmp_path.unlink()
            except Exception: pass
        try:
            kw = {"rate": r} if r else {}
            comm = edge_tts.Communicate(text=text, voice=voice, **kw)
            await asyncio.wait_for(comm.save(str(tmp_path.resolve())), timeout=35.0)
            if tmp_path.exists() and tmp_path.stat().st_size > 256:
                if out_path.exists():
                    try: out_path.unlink()
                    except Exception: pass
                tmp_path.rename(out_path)
                return True
        except Exception:
            await asyncio.sleep(0.3)

    if tmp_path.exists():
        try: tmp_path.unlink()
        except Exception: pass
    return False


async def synthesize_edge_tts(text: str, voice: str, output_path: Path, rate: str = None, volume: str = None) -> bool:
    """Tổng hợp giọng bằng Microsoft Neural TTS (Edge TTS) với kiến trúc bảo toàn giọng đọc và chống lỗi server Azure."""
    cleaned = clean_text_for_tts(text)
    rate_val = rate or config.TTS_RATE or "-10%"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Tầng 1: Thử đọc toàn bộ nội dung slide
    if await _synthesize_single_unit(cleaned, voice, output_path, desired_rate=rate_val):
        return True

    # Tầng 2: Nếu câu quá dài bị Azure từ chối, phân đoạn theo câu tự nhiên và ghép nối mượt mà
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned) if len(s.strip()) > 1]
    if not sentences:
        sentences = [cleaned]

    temp_files = []
    try:
        for i, sent in enumerate(sentences):
            temp_p = output_path.parent / f"{output_path.stem}_part_{i:02d}.mp3"
            ok = await _synthesize_single_unit(sent, voice, temp_p, desired_rate=rate_val)
            if not ok:
                raise RuntimeError(f"Azure TTS không thể tổng hợp câu: '{sent[:30]}...'")
            temp_files.append(temp_p)
            await asyncio.sleep(0.1)

        # Ghép các đoạn câu lại bằng FFmpeg copy stream (không mất chất lượng, tốc độ tức thì)
        concat_txt = output_path.parent / f"{output_path.stem}_concat.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for tf in temp_files:
                f.write(f"file '{tf.name}'\n")

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_txt.resolve()),
            "-c", "copy", str(output_path.resolve())
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {res.stderr}")

        return True
    finally:
        for tf in temp_files:
            tf.unlink(missing_ok=True)
        (output_path.parent / f"{output_path.stem}_concat.txt").unlink(missing_ok=True)


def synthesize_everai(
    text: str,
    output_path: Path,
    voice_code: str = "vi_male_lehoang_mb",
    api_key: str = None,
    timeout_secs: int = 120
) -> Path:
    """Tổng hợp giọng bằng EverAI Multilingual API."""
    key = api_key or config.EVERAI_API_KEY
    if not key:
        raise ValueError("Chưa cấu hình EVERAI_API_KEY trong .env hoặc giao diện.")

    headers = {
        "Authorization": f"Bearer {key.strip()}",
        "Content-Type": "application/json"
    }

    payload = {
        "input_text": clean_text_for_tts(text),
        "voice_code": voice_code,
        "model_id": "everai-v1.6",
        "audio_type": "mp3",
        "bitrate": 128,
        "speed_rate": 0.92,
        "pitch_rate": 1.0
    }

    resp = requests.post(EVERAI_BASE_URL, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"EverAI API Error ({resp.status_code}): {resp.text}")

    data = resp.json()
    if data.get("status") != 1 or "result" not in data:
        err_msg = data.get("error_message", "Unknown error")
        raise RuntimeError(f"EverAI Error: {err_msg}")

    request_id = data["result"]["request_id"]
    get_url = f"{EVERAI_BASE_URL}/{request_id}"

    start_time = time.time()
    while time.time() - start_time < timeout_secs:
        status_resp = requests.get(get_url, headers=headers, timeout=15)
        if status_resp.status_code == 200:
            status_data = status_resp.json()
            res = status_data.get("result", {})
            status = res.get("status", "").lower()

            if status in ["done", "success"]:
                audio_link = res.get("audio_link")
                if not audio_link:
                    raise RuntimeError(f"EverAI task {request_id} không có audio_link.")
                audio_bytes = requests.get(audio_link, timeout=60).content
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(audio_bytes)
                return output_path
            elif status in ["fail", "failed", "error"]:
                raise RuntimeError(f"EverAI xử lý thất bại cho request: {request_id}")

        time.sleep(1.5)

    raise TimeoutError(f"EverAI timeout ({timeout_secs}s) cho request: {request_id}")


async def synthesize_all_audio_async(
    scripts: List[Dict[str, Any]], 
    voice_name: str = None,
    rate: str = None,
    on_progress: Any = None
) -> List[Dict[str, Any]]:
    """Tổng hợp toàn bộ âm thanh mới cho các slide với cập nhật tiến độ liên tục."""
    config.BASE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # Xóa sạch các file âm thanh cũ trong workspace
    for old_file in config.BASE_AUDIO_DIR.glob("slide_*.mp3"):
        try: old_file.unlink()
        except Exception: pass

    selected_voice = voice_name or config.TTS_VOICE or "vi-VN-NamMinhNeural"
    selected_rate = rate or config.TTS_RATE or "-10%"
    is_everai = selected_voice.startswith("voice-") or selected_voice.startswith("vi_")

    audio_records = []
    total = len(scripts)

    for i, item in enumerate(scripts, start=1):
        idx = item["slide_index"]
        audio_file = config.BASE_AUDIO_DIR / f"slide_{idx:03d}.mp3"

        try:
            if is_everai:
                synthesize_everai(item["script"], audio_file, voice_code=selected_voice)
            else:
                await synthesize_edge_tts(item["script"], selected_voice, audio_file, rate=selected_rate)
        except Exception as e:
            print(f"[!] Cảnh báo Slide {idx} ({e}). Đang tự động chuyển sang gTTS fallback...")
            try:
                synthesize_gtts_fallback(item["script"], audio_file)
            except Exception as e2:
                print(f"[!] Lỗi gTTS fallback Slide {idx}: {e2}")

        pct = 50 + int((i / total) * 20)  # 50% -> 70%
        title_disp = item.get('title', f'Slide {idx}')[:30]
        if on_progress:
            on_progress("Bước 3: Tổng Hợp Giọng Nói", pct, f"Đã lồng tiếng Slide {i}/{total}: {title_disp}")

        audio_records.append({
            "slide_index": idx,
            "title": item.get("title", f"Slide {idx}"),
            "script": item["script"],
            "base_audio_path": str(audio_file.resolve())
        })
        await asyncio.sleep(0.1)

    return audio_records


def run_tts_engine(scripts: List[Dict[str, Any]] = None, voice_name: str = None, rate: str = None, on_progress: Any = None) -> List[Dict[str, Any]]:
    """Hàm thực thi chính cho Bước 3: Tổng hợp Audio TTS"""
    if scripts is None:
        script_file = config.WORKSPACE_DIR / "script.json"
        if not script_file.exists():
            raise FileNotFoundError(f"Chưa có file {script_file}. Vui lòng chạy Bước 2 trước.")
        with open(script_file, "r", encoding="utf-8") as f:
            scripts = json.load(f)

    audio_records = asyncio.run(synthesize_all_audio_async(scripts, voice_name=voice_name, rate=rate, on_progress=on_progress))

    output_meta = config.WORKSPACE_DIR / "base_audio_meta.json"
    with open(output_meta, "w", encoding="utf-8") as f:
        json.dump(audio_records, f, ensure_ascii=False, indent=2)

    return audio_records

run_step3 = run_tts_engine
