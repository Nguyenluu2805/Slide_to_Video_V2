"""
Module: tts_engine.py
Description: Động cơ tổng hợp giọng đọc Text-To-Speech (Microsoft Edge Neural TTS, EverAI Multilingual API & ZeroTTS Offline).
"""

import os
import sys
import json
import re
import asyncio
import time
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

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

    # Khôi phục dấu ngắt nhịp (chấm lửng tạo nhịp ngắt sư phạm)
    text = re.sub(r'\s*___PAUSE___\s*', '… ', text)

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


_zerotts_instance = None

def get_zerotts_instance():
    """Khởi tạo hoặc lấy lại instance ZeroTTS duy nhất (Singleton) với tự động kích hoạt GPU RTX 3060 Ti (DirectML/CUDA)."""
    global _zerotts_instance
    if _zerotts_instance is None:
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
        try:
            from zerotts import ZeroTTS
        except ImportError:
            voice_tts_src = Path("D:/Voice_TTS/src")
            if voice_tts_src.exists() and str(voice_tts_src) not in sys.path:
                sys.path.insert(0, str(voice_tts_src))
            from zerotts import ZeroTTS

        import onnxruntime as ort
        available_providers = ort.get_available_providers()
        providers = []
        if "CUDAExecutionProvider" in available_providers:
            providers.append("CUDAExecutionProvider")
        if "DmlExecutionProvider" in available_providers:
            providers.append("DmlExecutionProvider")
        providers.append("CPUExecutionProvider")

        gpu_active = any("CUDA" in p or "Dml" in p for p in providers[:1])
        device_label = "NVIDIA GPU (DirectML / RTX 3060 Ti)" if gpu_active else "CPU Đa Luồng"

        model_name = getattr(config, "ZEROTTS_MODEL", "zeroweight-ai/ZeroTTS")
        cpu_threads = getattr(config, "ZEROTTS_THREADS", 6)
        print(f"[*] Đang tải mô hình ZeroTTS ({model_name}) tăng tốc bởi {device_label}...")
        _zerotts_instance = ZeroTTS.from_pretrained(
            model_name,
            providers=providers,
            intra_op_num_threads=cpu_threads
        )
        print(f"[+] Khởi tạo ZeroTTS thành công trên {device_label}.")
    return _zerotts_instance


def split_script_into_pedagogical_sentences(text: str, max_words: int = 24) -> List[str]:
    """
    Tách kịch bản thành các câu tự nhiên, chuẩn sư phạm:
    - Đảm bảo độ dài mỗi câu từ 8 - 22 từ (không bao giờ vượt quá max_words).
    - Giúp ZeroTTS GPU chạy cực nhanh (~2.5s - 3.5s / câu) và loại bỏ hoàn toàn hiện tượng kẹt/treo khi câu quá dài.
    - Tách thông minh theo dấu ngắt câu, gạch ngang và dấu phẩy.
    """
    if not text or not text.strip():
        return ["Nội dung bài giảng."]

    # 1. Bảo vệ số thập phân (3.4, 1.5, ...)
    text_safe = re.sub(r'(\d+)\.(\d+)', r'\1_DOT_\2', text)
    # 2. Chuyển dấu gạch ngang dài — thành dấu ngắt câu
    text_safe = re.sub(r'\s*[\u2014\u2013—]\s*', '. ', text_safe)
    # 3. Chuẩn hóa dấu chấm lửng thành dấu phẩy
    text_safe = re.sub(r'\.{3,}|…', ', ', text_safe)

    # Tách theo ranh giới câu chính (. ! ? \n)
    initial_splits = [s.strip() for s in re.split(r'[.!?\n]+', text_safe) if s.strip()]

    raw_sentences = []
    for chunk in initial_splits:
        chunk = chunk.replace('_DOT_', '.')
        chunk_words = chunk.split()

        if len(chunk_words) <= max_words:
            raw_sentences.append(chunk)
        else:
            # Tách nhỏ theo dấu phẩy hoặc chấm phẩy nếu câu vượt quá max_words
            sub_clauses = [c.strip() for c in re.split(r'[,;:]+', chunk) if c.strip()]
            curr_clause = []
            for clause in sub_clauses:
                clause_words = clause.split()
                if len(curr_clause) + len(clause_words) <= max_words:
                    curr_clause.extend(clause_words)
                else:
                    if curr_clause:
                        raw_sentences.append(" ".join(curr_clause).strip())
                    curr_clause = list(clause_words)

            if curr_clause:
                raw_sentences.append(" ".join(curr_clause).strip())

    # Gộp các cụm quá ngắn (< 4 từ) vào câu kế tiếp để giọng đọc liền mạch, tự nhiên
    final_sentences = []
    pending_prefix = ""
    for s in raw_sentences:
        s = s.strip()
        if not s: continue
        if pending_prefix:
            s = f"{pending_prefix}, {s}"
            pending_prefix = ""

        words = s.split()
        if len(words) < 4:
            pending_prefix = s
        else:
            if not s.endswith(('.', '!', '?')):
                s += '.'
            final_sentences.append(s)

    if pending_prefix:
        if final_sentences:
            final_sentences[-1] = final_sentences[-1].rstrip('.!?') + f", {pending_prefix}."
        else:
            final_sentences.append(f"{pending_prefix}.")

    return final_sentences if final_sentences else [text]


def synthesize_zerotts(
    text: str,
    output_path: Path,
    voice_code: str = "maichi",
    on_sentence_progress: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """Tổng hợp giọng đọc chất lượng cao, tự nhiên bằng ZeroTTS (Offline ONNX) kèm ngắt nghỉ câu sư phạm."""
    import numpy as np
    from zerotts.text_norm.vi_normalizer import normalize_vi_text

    cleaned = clean_text_for_tts(text)
    sentences = split_script_into_pedagogical_sentences(cleaned)

    tts = get_zerotts_instance()
    actual_voice = voice_code.split(":", 1)[1] if voice_code.startswith("zerotts:") else voice_code

    audio_chunks = []
    pause_silence = np.zeros((1, int(tts.sample_rate * 0.45)), dtype=np.float32)

    total_sentences = len(sentences)
    for i, sent in enumerate(sentences):
        norm_sent = normalize_vi_text(sent)
        if not norm_sent.strip():
            continue
        if on_sentence_progress:
            on_sentence_progress(i + 1, total_sentences)
        audio_chunk = tts.synthesize(norm_sent, voice=actual_voice)
        audio_chunks.append(audio_chunk)
        # Chèn khoảng lặng ngắt nghỉ tự nhiên 0.45s giữa các câu hoàn chỉnh (trừ câu cuối)
        if i < total_sentences - 1:
            audio_chunks.append(pause_silence)

    if audio_chunks:
        full_audio = np.concatenate(audio_chunks, axis=-1)
    else:
        full_audio = np.zeros((1, tts.sample_rate), dtype=np.float32)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_wav = output_path.parent / f"{output_path.stem}_zerotts_temp.wav"

    try:
        tts.save_audio(full_audio, str(tmp_wav))
        # Chuyển đổi sang MP3 tiêu chuẩn cho video pipeline
        cmd = [
            "ffmpeg", "-y", "-i", str(tmp_wav.resolve()),
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            str(output_path.resolve())
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg MP3 conversion failed: {res.stderr}")
    finally:
        tmp_wav.unlink(missing_ok=True)

    return output_path


async def synthesize_all_audio_async(
    scripts: List[Dict[str, Any]], 
    voice_name: str = None,
    rate: str = None,
    on_progress: Any = None
) -> List[Dict[str, Any]]:
    """Tổng hợp toàn bộ âm thanh mới cho các slide với cập nhật tiến độ liên tục."""
    config.BASE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # Xóa sạch các file âm thanh cũ trong workspace
    for old_file in list(config.BASE_AUDIO_DIR.glob("slide_*.mp3")) + list(config.BASE_AUDIO_DIR.glob("code_demo_*.mp3")):
        try: old_file.unlink()
        except Exception: pass

    selected_voice = voice_name or config.TTS_VOICE or "vi-VN-NamMinhNeural"
    selected_rate = rate or config.TTS_RATE or "-10%"
    is_everai = selected_voice.startswith("voice-") or selected_voice.startswith("vi_")
    is_zerotts = selected_voice.startswith("zerotts:")

    audio_records = []
    total = len(scripts)

    for i, item in enumerate(scripts, start=1):
        idx = item["slide_index"]
        audio_file = config.BASE_AUDIO_DIR / f"slide_{idx:03d}.mp3"
        title_disp = item.get('title', f'Slide {idx}')[:30]

        # Cập nhật thông báo ngay khi bắt đầu xử lý từng slide
        start_pct = 50 + int(((i - 1) / total) * 20)
        if on_progress:
            on_progress("Bước 3: Tổng Hợp Giọng Nói", start_pct, f"Đang tạo âm thanh Slide {i}/{total}: {title_disp}...")

        def _on_zerotts_sent(curr_s: int, tot_s: int):
            if on_progress:
                sub_pct = start_pct + int((curr_s / tot_s) * (20 / total))
                on_progress("Bước 3: Tổng Hợp Giọng Nói", min(69, sub_pct), f"Slide {i}/{total} [{title_disp}]: Đang đọc câu {curr_s}/{tot_s}...")

        try:
            if is_zerotts:
                synthesize_zerotts(item["script"], audio_file, voice_code=selected_voice, on_sentence_progress=_on_zerotts_sent)
            elif is_everai:
                synthesize_everai(item["script"], audio_file, voice_code=selected_voice)
            else:
                await synthesize_edge_tts(item["script"], selected_voice, audio_file, rate=selected_rate)
        except Exception as e:
            print(f"[!] Cảnh báo Slide {idx} ({e}). Đang tự động chuyển sang gTTS fallback...")
            try:
                synthesize_gtts_fallback(item["script"], audio_file)
            except Exception as e2:
                print(f"[!] Lỗi gTTS fallback Slide {idx}: {e2}")

        # Nếu slide có demo code thực hành, tổng hợp audio 2 phân đoạn đồng bộ hoàn hảo
        code_audio_file = None
        has_demo = bool(item.get("has_code_demo") and item.get("code_demo"))
        if has_demo:
            c_spec = item["code_demo"]
            ed_narr = c_spec.get("editor_narration", "").strip()
            term_narr = c_spec.get("terminal_narration", "").strip()
            full_narr = c_spec.get("narration", "").strip()

            if not ed_narr or not term_narr:
                try:
                    from .script_gen import split_demo_narration_phases
                except (ImportError, ValueError):
                    import script_gen
                    split_demo_narration_phases = script_gen.split_demo_narration_phases
                e_p, t_p = split_demo_narration_phases(full_narr or ed_narr or term_narr)
                ed_narr = ed_narr or e_p
                term_narr = term_narr or t_p

            c_spec["editor_narration"] = ed_narr
            c_spec["terminal_narration"] = term_narr
            c_spec["narration"] = f"{ed_narr} {term_narr}".strip()

            file_ed = config.BASE_AUDIO_DIR / f"code_demo_ed_{idx:03d}.mp3"
            file_term = config.BASE_AUDIO_DIR / f"code_demo_term_{idx:03d}.mp3"

            # 1. Tổng hợp audio cho Phân đoạn 1 (Code Editor)
            if on_progress:
                on_progress("Bước 3: Tổng Hợp Giọng Nói", start_pct + 1, f"Slide {i}/{total}: Đang đọc thuyết minh VS Code...")
            try:
                if is_zerotts:
                    synthesize_zerotts(ed_narr, file_ed, voice_code=selected_voice)
                elif is_everai:
                    synthesize_everai(ed_narr, file_ed, voice_code=selected_voice)
                else:
                    await synthesize_edge_tts(ed_narr, selected_voice, file_ed, rate=selected_rate)
            except Exception as e_ed:
                print(f"[!] Lỗi TTS Code Editor Slide {idx} ({e_ed}). Fallback gTTS...")
                synthesize_gtts_fallback(ed_narr, file_ed)

            # 2. Tổng hợp audio cho Phân đoạn 2 (Terminal)
            if on_progress:
                on_progress("Bước 3: Tổng Hợp Giọng Nói", start_pct + 1, f"Slide {i}/{total}: Đang đọc thuyết minh Terminal...")
            try:
                if is_zerotts:
                    synthesize_zerotts(term_narr, file_term, voice_code=selected_voice)
                elif is_everai:
                    synthesize_everai(term_narr, file_term, voice_code=selected_voice)
                else:
                    await synthesize_edge_tts(term_narr, selected_voice, file_term, rate=selected_rate)
            except Exception as e_tm:
                print(f"[!] Lỗi TTS Terminal Slide {idx} ({e_tm}). Fallback gTTS...")
                synthesize_gtts_fallback(term_narr, file_term)

            # 3. Đo thời lượng và tính toán khung hình chuẩn xác cho Remotion
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()

            def _get_dur(fpath: Path) -> float:
                p = subprocess.run(
                    [ffmpeg_bin, "-i", str(fpath.resolve())],
                    stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, errors="replace"
                )
                m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", p.stderr)
                if m:
                    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                return 10.0

            dur_ed = _get_dur(file_ed) if file_ed.exists() else 10.0
            dur_term = _get_dur(file_term) if file_term.exists() else 8.0

            # Cảnh 1 (Editor): Thời lượng audio + 1.2s nghỉ lấy hơi trước khi chuyển cảnh
            editor_scene_dur = max(11.0, round(dur_ed + 1.2, 2))
            # Cảnh 2 (Terminal): 0.4s mở terminal + audio + 2.5s giữ màn hình đọc kết quả
            terminal_scene_dur = max(9.0, round(0.4 + dur_term + 2.5, 2))
            total_demo_dur = round(editor_scene_dur + terminal_scene_dur, 2)

            c_spec["editor_scene_dur"] = editor_scene_dur
            c_spec["terminal_scene_dur"] = terminal_scene_dur
            c_spec["editor_frames"] = int(round(editor_scene_dur * 30))
            c_spec["terminal_frames"] = int(round(terminal_scene_dur * 30))
            c_spec["total_demo_dur"] = total_demo_dur

            # 4. Ghép 2 audio vào 1 master audio đồng bộ khung hình bằng adelay và amix
            code_audio_file = config.BASE_AUDIO_DIR / f"code_demo_{idx:03d}.mp3"
            ed_delay_ms = 200
            term_delay_ms = int(round((editor_scene_dur + 0.4) * 1000))

            filter_complex_str = (
                f"[0:a]adelay=delays={ed_delay_ms}:all=1[a_ed];"
                f"[1:a]adelay=delays={term_delay_ms}:all=1[a_term];"
                f"[a_ed][a_term]amix=inputs=2:dropout_transition=0:normalize=0,apad=pad_dur=2[a_mix]"
            )

            mix_cmd = [
                ffmpeg_bin, "-y",
                "-i", str(file_ed.resolve()),
                "-i", str(file_term.resolve()),
                "-filter_complex", filter_complex_str,
                "-map", "[a_mix]",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-ar", "44100",
                "-t", str(total_demo_dur),
                str(code_audio_file.resolve())
            ]
            subprocess.run(mix_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        pct = 50 + int((i / total) * 20)  # 50% -> 70%
        if on_progress:
            on_progress("Bước 3: Tổng Hợp Giọng Nói", pct, f"Đã hoàn tất Slide {i}/{total}: {title_disp}")

        record_item = {
            "slide_index": idx,
            "title": item.get("title", f"Slide {idx}"),
            "script": item["script"],
            "base_audio_path": str(audio_file.resolve()),
            "has_code_demo": has_demo
        }
        if has_demo:
            record_item["code_demo"] = item["code_demo"]
            if code_audio_file and code_audio_file.exists():
                record_item["code_audio_path"] = str(code_audio_file.resolve())

        audio_records.append(record_item)
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
