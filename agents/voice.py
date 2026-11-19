"""
agents/voice.py - Module tổng hợp giọng đọc chuẩn V2 với Single Unified Interface
Hỗ trợ: ZeroTTS (ONNX local, tăng tốc GPU) làm TTS chính,
Edge-TTS (Microsoft Neural) làm fallback, gTTS/Gemini-TTS làm fallback cuối.
Kiểm tra file câm bằng FFmpeg volumedetect, retry tối đa 3 lần.
"""

import os
import sys
import re
import json
import time
import asyncio
import subprocess
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional

import config

_ZEROTTS_CACHE = None


def get_zerotts_instance():
    """Khởi tạo hoặc lấy lại instance ZeroTTS duy nhất (Singleton)."""
    global _ZEROTTS_CACHE
    if _ZEROTTS_CACHE is None:
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
        from zerotts import ZeroTTS
        import onnxruntime as ort

        available_providers = ort.get_available_providers()
        providers = []
        if "CUDAExecutionProvider" in available_providers:
            providers.append("CUDAExecutionProvider")
        if "DmlExecutionProvider" in available_providers:
            providers.append("DmlExecutionProvider")
        providers.append("CPUExecutionProvider")

        hw = config.get_hardware_device_info()
        dev_label = hw["device_name"] if hw["is_gpu"] else "CPU Đa Luồng"
        model_name = getattr(config, "ZEROTTS_MODEL", "zeroweight-ai/ZeroTTS")

        print(f"[*] Đang nạp mô hình ZeroTTS ({model_name}) trên {dev_label}...")
        _ZEROTTS_CACHE = ZeroTTS.from_pretrained(
            model_name,
            providers=providers,
            intra_op_num_threads=6
        )
        print(f"[+] Khởi tạo ZeroTTS thành công ({_ZEROTTS_CACHE.sample_rate}Hz).")
    return _ZEROTTS_CACHE


def clean_text_for_tts(text: str) -> str:
    """
    Chuẩn hóa văn bản trước khi đọc theo chuẩn V2:
    - BẢO TOÀN số thập phân (99.9%, 3.5, 30 giây, ...), ngày giờ, phần trăm.
    - Làm sạch markdown, ký tự đặc biệt, dấu gạch nối rườm rà.
    - BẢO TOÀN thuật ngữ tiếng Anh gốc và tên riêng.
    """
    if not text:
        return "Nội dung slide bài giảng."

    # 1. Bảo vệ số thập phân (99.9%, 3.5, 0.8s, ...) bằng placeholder an toàn
    cleaned = re.sub(r'(\d+)\.(\d+)', r'\1_DOT_\2', text)
    cleaned = re.sub(r'(\d+),(\d+)', r'\1_COMMA_\2', cleaned)

    # 2. Chuyển dấu gạch ngang dài / en-dash / em-dash thành dấu phẩy
    cleaned = re.sub(r'[\u2012\u2013\u2014\u2015\u2212]+', ', ', cleaned)
    # Dấu gạch ngang độc lập giữa khoảng trắng thành phẩy
    cleaned = re.sub(r'\s+-\s+', ', ', cleaned)

    # 3. Chuẩn hóa ngoặc kép, nháy đơn
    cleaned = re.sub(r'[\u2018\u2019\'\`]', ' ', cleaned)
    cleaned = re.sub(r'[\u201C\u201D\"]', ' ', cleaned)

    # 4. Ký hiệu cơ bản
    cleaned = cleaned.replace("&", " và ")
    cleaned = cleaned.replace("→", " chuyển thành ")
    cleaned = cleaned.replace(":", ", ")
    cleaned = cleaned.replace(";", ", ")

    # 5. Bỏ markdown formatting (*, #, [, ], (, ), {, }, <, >, |, ~, ^, @) - bảo vệ _ của _DOT_
    cleaned = re.sub(r'[\*\#\[\]\(\)\{\}\<\>\/\\\|\~\^\@]', ' ', cleaned)

    # 6. Bảo vệ dấu chấm lửng
    cleaned = re.sub(r'\.{3,}|…', ' … ', cleaned)

    # 7. Chuẩn hóa khoảng trắng quanh dấu câu (không ảnh hưởng _DOT_)
    cleaned = re.sub(r'\s*,\s*', ', ', cleaned)
    cleaned = re.sub(r'\s*\.\s*', '. ', cleaned)
    cleaned = re.sub(r'\s*!\s*', '! ', cleaned)
    cleaned = re.sub(r'\s*\?\s*', '? ', cleaned)

    # 8. Khôi phục số thập phân nguyên vẹn
    cleaned = cleaned.replace('_DOT_', '.')
    cleaned = cleaned.replace('_COMMA_', ',')
    cleaned = cleaned.replace('DECIMALDOT', '.')
    cleaned = cleaned.replace('DECIMALCOMMA', ',')

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def split_script_into_pedagogical_sentences(text: str, max_words: int = 24) -> List[str]:
    """
    Tách kịch bản thành các câu sư phạm ngắn gọn (tối đa max_words từ):
    - Đảm bảo ZeroTTS chạy nhanh, không bị kẹt khi gặp câu dài.
    - Giữ trọn nhịp ngắt sư phạm và bảo vệ số thập phân.
    """
    if not text or not text.strip():
        return ["Nội dung bài giảng."]

    # Bảo vệ số thập phân (3.5, 99.9, ...) bằng token an toàn
    safe_text = re.sub(r'(\d+)\.(\d+)', r'\1DECIMALDOT\2', text)
    safe_text = re.sub(r'(\d+),(\d+)', r'\1DECIMALCOMMA\2', safe_text)
    safe_text = re.sub(r'\.{3,}|…', ', ', safe_text)

    # Tách theo ranh giới câu chính
    chunks = [s.strip() for s in re.split(r'[.!?\n]+', safe_text) if s.strip()]

    raw_sentences = []
    for chunk in chunks:
        chunk = chunk.replace('DECIMALDOT', '.').replace('DECIMALCOMMA', ',')
        words = chunk.split()
        if len(words) <= max_words:
            raw_sentences.append(chunk)
        else:
            # Tách nhỏ hơn theo dấu phẩy nếu câu dài
            sub_clauses = [c.strip() for c in re.split(r'[,;:]+', chunk) if c.strip()]
            curr = []
            for clause in sub_clauses:
                c_words = clause.split()
                if len(curr) + len(c_words) <= max_words:
                    curr.extend(c_words)
                else:
                    if curr:
                        raw_sentences.append(" ".join(curr).strip())
                    curr = list(c_words)
            if curr:
                raw_sentences.append(" ".join(curr).strip())

    # Gộp các câu quá ngắn (< 4 từ) vào câu kế tiếp
    final_sentences = []
    prefix = ""
    for s in raw_sentences:
        s = s.strip()
        if not s:
            continue
        if prefix:
            s = f"{prefix}, {s}"
            prefix = ""
        if len(s.split()) < 4:
            prefix = s
        else:
            if not s.endswith(('.', '!', '?')):
                s += '.'
            final_sentences.append(s)

    if prefix:
        if final_sentences:
            final_sentences[-1] = final_sentences[-1].rstrip('.!?') + f", {prefix}."
        else:
            final_sentences.append(f"{prefix}.")

    return final_sentences if final_sentences else [text]


def is_audio_silent(audio_path: Path) -> bool:
    """
    Kiểm tra file âm thanh có bị câm hoặc hỏng hay không bằng FFmpeg volumedetect.
    Trả về True nếu âm thanh bị câm hoàn toàn (max_volume <= -80dB hoặc file rỗng).
    """
    if not audio_path.exists() or audio_path.stat().st_size < 1024:
        return True

    cmd = ["ffmpeg", "-i", str(audio_path.resolve()), "-af", "volumedetect", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")

    m = re.search(r'max_volume:\s*(-?[\d\.]+)\s*dB', res.stderr)
    if m:
        max_vol = float(m.group(1))
        # Nếu âm lượng tối đa <= -80dB thì xem như file câm
        return max_vol <= -80.0

    return False


def get_audio_duration_seconds(audio_path: Path) -> float:
    """Đo thời lượng thực tế của file âm thanh bằng FFmpeg."""
    cmd = ["ffmpeg", "-i", str(audio_path.resolve())]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 10.0


def _synthesize_zerotts(text: str, voice_code: str, output_wav: Path) -> Path:
    """Tổng hợp giọng bằng ZeroTTS local ONNX (ngắt nghỉ 0.45s giữa các câu)."""
    from zerotts.text_norm.vi_normalizer import normalize_vi_text

    cleaned = clean_text_for_tts(text)
    sentences = split_script_into_pedagogical_sentences(cleaned)

    tts = get_zerotts_instance()
    actual_voice = voice_code.split(":", 1)[1] if voice_code.startswith("zerotts:") else voice_code

    audio_chunks = []
    pause_samples = int(tts.sample_rate * 0.45)
    pause_silence = np.zeros((1, pause_samples), dtype=np.float32)

    total_s = len(sentences)
    for i, sent in enumerate(sentences):
        norm_s = normalize_vi_text(sent)
        if not norm_s.strip():
            continue
        chunk = tts.synthesize(norm_s, voice=actual_voice)
        audio_chunks.append(chunk)
        if i < total_s - 1:
            audio_chunks.append(pause_silence)

    if audio_chunks:
        full_audio = np.concatenate(audio_chunks, axis=-1)
    else:
        full_audio = np.zeros((1, tts.sample_rate), dtype=np.float32)

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    tts.save_audio(full_audio, str(output_wav.resolve()))
    return output_wav


async def _synthesize_edge_tts_async(text: str, voice_code: str, output_wav: Path) -> Path:
    """Tổng hợp giọng bằng Microsoft Edge-TTS và xuất file WAV 48kHz."""
    import edge_tts

    cleaned = clean_text_for_tts(text)
    actual_voice = voice_code if "Neural" in voice_code else config.EDGE_TTS_VOICE

    tmp_mp3 = output_wav.with_suffix(".tmp.mp3")
    rates = [config.TTS_RATE, "-5%", "+0%", None]
    
    success = False
    for r in rates:
        try:
            kw = {"rate": r} if r else {}
            comm = edge_tts.Communicate(text=cleaned, voice=actual_voice, **kw)
            await asyncio.wait_for(comm.save(str(tmp_mp3.resolve())), timeout=25.0)
            if tmp_mp3.exists() and tmp_mp3.stat().st_size > 512:
                success = True
                break
        except Exception:
            await asyncio.sleep(0.3)

    if not success or not tmp_mp3.exists():
        raise RuntimeError(f"Edge-TTS Azure không thể tổng hợp giọng đọc cho đoạn: '{text[:30]}...'")

    try:
        # Chuyển đổi MP3 sang WAV 48kHz đồng nhất với ZeroTTS
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-i", str(tmp_mp3.resolve()),
            "-ar", "48000", "-ac", "1",
            str(output_wav.resolve())
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return output_wav
    finally:
        tmp_mp3.unlink(missing_ok=True)


def _synthesize_gtts_fallback(text: str, output_wav: Path) -> Path:
    """Fallback cuối cùng bằng gTTS nếu cả ZeroTTS và Edge-TTS gặp lỗi mạng."""
    from gtts import gTTS

    cleaned = clean_text_for_tts(text)
    tmp_mp3 = output_wav.with_suffix(".gtts_tmp.mp3")
    try:
        tts = gTTS(text=cleaned, lang='vi')
        tts.save(str(tmp_mp3.resolve()))

        cmd = [
            "ffmpeg", "-y", "-i", str(tmp_mp3.resolve()),
            "-ar", "48000", "-ac", "1",
            str(output_wav.resolve())
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return output_wav
    finally:
        tmp_mp3.unlink(missing_ok=True)


def synthesize(
    text: str,
    provider: str = "zerotts",
    voice_ref: Optional[str] = None,
    output_path: Optional[Path] = None
) -> Path:
    """
    Interface thống nhất duy nhất cho toàn bộ hệ thống V2:
    def synthesize(text: str, provider: str, voice_ref: str | None) -> Path
    
    Quy tắc:
    - Trả về cùng 1 file .wav (48kHz, mono).
    - ZeroTTS là chính.
    - Fallback sang Edge-TTS khi ZeroTTS lỗi hoặc file câm.
    - Kiểm tra file câm bằng volumedetect, retry tối đa 3 lần.
    """
    if not output_path:
        output_path = config.AUDIO_DIR / f"speech_{int(time.time()*1000)}.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if getattr(config, "DRAFT_MODE", False):
        default_provider = "edge-tts"
        default_voice = config.EDGE_TTS_VOICE
    else:
        default_provider = config.TTS_PROVIDER
        default_voice = config.TTS_VOICE

    target_provider = (provider or default_provider).lower()
    target_voice = voice_ref or (config.EDGE_TTS_VOICE if "edge" in target_provider else default_voice)

    # Thử tối đa 3 lần
    for attempt in range(1, 4):
        try:
            if "zerotts" in target_provider:
                _synthesize_zerotts(text, target_voice, output_path)
            elif "edge" in target_provider:
                asyncio.run(_synthesize_edge_tts_async(text, target_voice, output_path))
            else:
                _synthesize_gtts_fallback(text, output_path)

            # Kiểm tra âm lượng bằng volumedetect
            if is_audio_silent(output_path):
                print(f"[!] Cảnh báo: File âm thanh {output_path.name} bị câm hoặc rỗng ở lần thử {attempt}.")
                if "zerotts" in target_provider:
                    print("[*] Tự động chuyển fallback sang Edge-TTS...")
                    target_provider = "edge-tts"
                    target_voice = config.EDGE_TTS_VOICE
                time.sleep(1)
                continue

            return output_path
        except Exception as e:
            print(f"[!] Lỗi TTS ({target_provider}) lần {attempt}/3: {e}")
            if "zerotts" in target_provider:
                print("[*] Gặp lỗi với ZeroTTS, tự động kích hoạt fallback Edge-TTS...")
                target_provider = "edge-tts"
                target_voice = config.EDGE_TTS_VOICE
            elif "edge" in target_provider:
                print("[*] Gặp lỗi với Edge-TTS, tự động kích hoạt fallback gTTS...")
                target_provider = "gtts"
            time.sleep(1)

    # Nếu cả 3 lần thử đều lỗi, dùng gTTS khẩn cấp
    print("[!] Kích hoạt cứu hộ cuối cùng bằng gTTS...")
    _synthesize_gtts_fallback(text, output_path)
    return output_path


def synthesize_presentation_audio(
    slides_data: List[Dict[str, Any]],
    provider: Optional[str] = None,
    voice_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Tổng hợp âm thanh cho toàn bộ slide kèm Checkpoint:
    - Bỏ qua các slide đã có file audio hợp lệ (non-silent).
    - Lưu checkpoint state.json sau mỗi slide.
    """
    config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    if getattr(config, "DRAFT_MODE", False):
        default_provider = "edge-tts"
        default_voice = config.EDGE_TTS_VOICE
    else:
        default_provider = config.TTS_PROVIDER
        default_voice = config.TTS_VOICE

    active_provider = provider or default_provider
    active_voice = voice_name or default_voice

    total_slides = len(slides_data)
    print(f"\n[*] Bắt đầu tổng hợp giọng nói cho {total_slides} slide (Provider: {active_provider})...")

    for i, item in enumerate(slides_data, start=1):
        s = item["slide"]
        sc = item["scene"]
        sid = s["id"]
        title_disp = s.get("title", f"Slide {sid}")[:35]

        target_wav = config.AUDIO_DIR / f"slide_{sid:03d}.wav"

        # Checkpoint: Nếu file wav đã tồn tại và không bị câm -> BỎ QUA
        if target_wav.exists() and not is_audio_silent(target_wav):
            dur = get_audio_duration_seconds(target_wav)
            sc["audio_file"] = str(target_wav.relative_to(config.PROJECT_ROOT))
            sc["duration_sec"] = round(dur, 2)
            sc["state"] = "voiced"
            print(f"[+] [Checkpoint] Bỏ qua Slide {sid}: File âm thanh đã sẵn sàng ({dur:.1f}s).")
            continue

        script_text = sc.get("script", "")
        if not script_text.strip():
            print(f"[!] Cảnh báo: Slide {sid} chưa có kịch bản. Sử dụng tiêu đề slide làm lời thoại.")
            script_text = f"Nội dung slide {sid}: {s.get('title', '')}."

        print(f"[*] [{i}/{total_slides}] Đang tạo giọng đọc Slide {sid}: {title_disp}...")
        start_t = time.time()
        synthesize(
            text=script_text,
            provider=active_provider,
            voice_ref=active_voice,
            output_path=target_wav
        )
        elapsed = time.time() - start_t
        real_duration = get_audio_duration_seconds(target_wav)

        sc["audio_file"] = str(target_wav.relative_to(config.PROJECT_ROOT))
        sc["duration_sec"] = round(real_duration, 2)
        sc["state"] = "voiced"

        print(f"[+] Slide {sid} hoàn thành: Thời lượng audio {real_duration:.1f}s (tạo trong {elapsed:.1f}s).")

        # Lưu checkpoint ngay sau mỗi slide
        checkpoint_payload = {
            "current_step": "voiced",
            "last_voiced_slide": sid,
            "total_slides": total_slides,
            "timestamp": time.time(),
            "slides": slides_data
        }
        with open(config.STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(checkpoint_payload, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Đã hoàn tất tạo giọng đọc cho toàn bộ {total_slides} slide!")
    return slides_data
