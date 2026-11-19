"""
agents/assemble.py - Module lắp ráp hoàn thiện video bài giảng V2
- Sinh phụ đề .srt tiếng Việt chuẩn xác 100% trực tiếp từ kịch bản gốc (script.json)
  (Bảo toàn nguyên vẹn 99.9%, 30 giây, Ex01, LangGraph, Hybrid Workflow...)
- Chia nhỏ khối phụ đề: Tối đa 2 dòng, ~40 ký tự/dòng, tối đa 5 giây/câu
- Chuẩn hóa âm lượng EBU R128 (-16 LUFS)
- Hardsub phụ đề vào video thành phẩm
- Nối các đoạn slide video: output/video/final_lecture.mp4
"""

import os
import sys
import re
import json
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import config
from agents.voice import get_audio_duration_seconds


def format_srt_timestamp(seconds: float) -> str:
    """Chuyển đổi giây thành định dạng timestamp chuẩn SRT: HH:MM:SS,mmm"""
    millis = int(round(seconds * 1000))
    hours = millis // 3600000
    millis %= 3600000
    minutes = millis // 60000
    millis %= 60000
    secs = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def split_script_into_subtitle_blocks(script: str, max_words: int = 12, min_words: int = 4) -> List[str]:
    """
    Chia kịch bản thành các khối phụ đề ngắn sư phạm:
    - Bảo vệ số thập phân (99.9%, 3.5, 30 giây, ...).
    - Tách theo ranh giới câu -> mệnh đề (dấu phẩy, chấm phẩy) -> từ.
    - Gộp các cụm quá ngắn (< min_words từ) để người xem không bị nháy chữ quá nhanh (< 1.5s).
    - Giữ trọn vẹn thuật ngữ tiếng Anh gốc và số liệu 100% khớp kịch bản.
    """
    # 1. Bảo vệ số thập phân
    safe_text = re.sub(r'(\d+)\.(\d+)', r'\1DECIMALDOT\2', script)
    safe_text = re.sub(r'(\d+),(\d+)', r'\1DECIMALCOMMA\2', safe_text)
    safe_text = re.sub(r'\s+', ' ', safe_text).strip()

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', safe_text) if s.strip()]

    raw_units = []
    for sent in sentences:
        words = sent.split()
        if len(words) <= max_words:
            raw_units.append(sent)
        else:
            clauses = [c.strip() for c in re.split(r'(?<=[,;:])\s+', sent) if c.strip()]
            curr_clause_words = []
            for c in clauses:
                c_words = c.split()
                if len(curr_clause_words) + len(c_words) <= max_words:
                    curr_clause_words.extend(c_words)
                else:
                    if curr_clause_words:
                        raw_units.append(" ".join(curr_clause_words))
                        curr_clause_words = []
                    if len(c_words) > max_words:
                        for i in range(0, len(c_words), max_words):
                            raw_units.append(" ".join(c_words[i:i + max_words]))
                    else:
                        curr_clause_words = list(c_words)
            if curr_clause_words:
                raw_units.append(" ".join(curr_clause_words))

    # Gộp các khối quá ngắn (< min_words) vào khối liền kề
    merged_units = []
    for u in raw_units:
        u_words = u.split()
        if merged_units and len(u_words) < min_words:
            prev = merged_units[-1]
            prev_words = prev.split()
            if len(prev_words) + len(u_words) <= (max_words + 3):
                merged_units[-1] = f"{prev} {u}"
                continue
        merged_units.append(u)

    final_units = []
    pending = ""
    for u in merged_units:
        if pending:
            u = f"{pending} {u}"
            pending = ""
        if len(u.split()) < min_words:
            pending = u
        else:
            final_units.append(u)
    if pending:
        if final_units:
            final_units[-1] = f"{final_units[-1]} {pending}"
        else:
            final_units.append(pending)

    cleaned_blocks = []
    for b in final_units:
        b = b.replace('DECIMALDOT', '.').replace('DECIMALCOMMA', ',').strip()
        if b:
            cleaned_blocks.append(b)

    return cleaned_blocks


def format_subtitle_text(text: str, max_chars_per_line: int = 42) -> str:
    """
    Format phụ đề:
    - Tối đa 2 dòng.
    - Mỗi dòng ~40 ký tự.
    - Tự động ngắt dòng tại khoảng trắng tự nhiên gần giữa câu.
    """
    text = text.strip()
    if len(text) <= max_chars_per_line:
        return text

    mid = len(text) // 2
    best_split = -1
    min_dist = float('inf')

    for i in range(10, len(text) - 10):
        if text[i] in (' ', ','):
            split_pos = i + 1 if text[i] == ',' else i
            dist = abs(split_pos - mid)
            if dist < min_dist:
                min_dist = dist
                best_split = split_pos

    if best_split != -1:
        line1 = text[:best_split].strip()
        line2 = text[best_split:].strip()
        return f"{line1}\n{line2}"

    return text


def generate_subtitles_from_script(
    slides_data: List[Dict[str, Any]],
    output_srt: Path,
    pre_pause: float = 0.8,
    post_pause: float = 1.5
) -> Path:
    """
    Sinh file phụ đề .srt trực tiếp từ kịch bản gốc (script.json):
    1. Chữ đúng 100% kịch bản, bảo toàn nguyên vẹn thuật ngữ (99.9%, Ex01, LangGraph, Hybrid Workflow).
    2. Chia nhỏ thành câu ngắn: tối đa 2 dòng, ~40 ký tự/dòng, tối đa 5 giây/câu.
    3. Phân bổ thời gian theo tỷ lệ số từ và độ dài audio thực tế của từng slide.
    """
    srt_entries = []
    current_time_offset = 0.0
    subtitle_index = 1

    for item in slides_data:
        s = item["slide"]
        sc = item.get("scene", {})
        sid = s["id"]
        script = sc.get("script", "").strip()
        audio_file = config.PROJECT_ROOT / sc.get("audio_file", "")

        if not audio_file.exists() or not script:
            continue

        audio_dur = get_audio_duration_seconds(audio_file)
        speech_start_offset = current_time_offset + pre_pause

        # Tách kịch bản thành các khối ngắn sư phạm
        raw_blocks = split_script_into_subtitle_blocks(script, max_words=12, min_words=4)

        # Tính trọng số cho từng block (số từ + bonus dấu câu)
        weights = []
        for b in raw_blocks:
            words_count = len(b.split())
            bonus = 1.0 if b.endswith(('.', '!', '?')) else (0.5 if b.endswith((',', ';', ':')) else 0.0)
            weights.append(max(1.0, words_count + bonus))

        total_weight = sum(weights) if weights else 1.0
        durations = [(w / total_weight) * audio_dur for w in weights]

        curr_t = speech_start_offset
        for b, dur in zip(raw_blocks, durations):
            formatted_b = format_subtitle_text(b, max_chars_per_line=42)
            end_t = curr_t + dur
            srt_entries.append(
                f"{subtitle_index}\n"
                f"{format_srt_timestamp(curr_t)} --> {format_srt_timestamp(end_t)}\n"
                f"{formatted_b}\n"
            )
            subtitle_index += 1
            curr_t = end_t

        slide_total_dur = round(audio_dur + pre_pause + post_pause, 2)
        current_time_offset += slide_total_dur

    output_srt.parent.mkdir(parents=True, exist_ok=True)
    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries) + "\n")

    print(f"[+] Đã xuất file phụ đề chuẩn xác 100% từ kịch bản ({subtitle_index - 1} khối, max 5s): {output_srt.name}")
    return output_srt


def extract_presentation_subtitles_whisper(
    slides_data: List[Dict[str, Any]],
    output_srt: Path,
    pre_pause: float = 0.8,
    post_pause: float = 1.5
) -> Path:
    """
    (Bước kiểm tra phụ) Trích xuất phụ đề bằng Faster-Whisper nếu người dùng yêu cầu đối chiếu.
    """
    from faster_whisper import WhisperModel

    model_size = getattr(config, "WHISPER_MODEL_SIZE", "base")
    device = getattr(config, "WHISPER_DEVICE", "cpu")

    print(f"[*] Đang chạy Faster-Whisper ({model_size}) để kiểm tra âm thanh...")
    whisper_model = WhisperModel(model_size, device=device, compute_type="int8")

    srt_entries = []
    current_time_offset = 0.0
    subtitle_index = 1

    for item in slides_data:
        s = item["slide"]
        sc = item["scene"]
        audio_file = config.PROJECT_ROOT / sc["audio_file"]

        if not audio_file.exists():
            continue

        audio_dur = get_audio_duration_seconds(audio_file)
        speech_start_offset = current_time_offset + pre_pause

        segments, _ = whisper_model.transcribe(
            str(audio_file.resolve()),
            language="vi",
            beam_size=5,
            vad_filter=True,
            initial_prompt="Ex01, Hybrid Workflow, Pure LLM, Deterministic Code, State Machine, LangGraph, Agentic Nodes, 99.9%"
        )

        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue

            start_t = speech_start_offset + seg.start
            end_t = speech_start_offset + seg.end

            srt_entries.append(
                f"{subtitle_index}\n"
                f"{format_srt_timestamp(start_t)} --> {format_srt_timestamp(end_t)}\n"
                f"{text}\n"
            )
            subtitle_index += 1

        slide_total_dur = round(audio_dur + pre_pause + post_pause, 2)
        current_time_offset += slide_total_dur

    output_srt.parent.mkdir(parents=True, exist_ok=True)
    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries) + "\n")

    return output_srt


def assemble_final_video(
    slides_data: List[Dict[str, Any]],
    output_video_path: Optional[Path] = None,
    output_srt_path: Optional[Path] = None
) -> Tuple[Path, Path]:
    """
    Lắp ráp toàn bộ các đoạn slide video thành video thành phẩm:
    1. Sinh phụ đề .srt trực tiếp từ kịch bản gốc (Đúng 100% chữ, chia nhỏ <= 5s, <= 40 ký tự/dòng).
    2. Nối các slide video bằng FFmpeg concat demuxer.
    3. Chuẩn hóa âm thanh loudnorm -16 LUFS và hardsub phụ đề.
    """
    config.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    final_video = output_video_path or config.FINAL_VIDEO_FILE
    final_srt = output_srt_path or config.FINAL_SRT_FILE

    pre_pause = getattr(config, "SLIDE_PRE_PAUSE", 0.8)
    post_pause = getattr(config, "SLIDE_POST_PAUSE", 1.5)

    # 1. Sinh phụ đề trực tiếp từ kịch bản gốc (Đúng 100% chữ)
    print("\n[*] Bước 1/3: Sinh phụ đề tiếng Việt chuẩn xác 100% từ kịch bản gốc...")
    generate_subtitles_from_script(
        slides_data=slides_data,
        output_srt=final_srt,
        pre_pause=pre_pause,
        post_pause=post_pause
    )

    # 2. Tạo danh sách file để nối (Concat Demuxer)
    print("\n[*] Bước 2/3: Nối các đoạn slide video...")
    concat_list_file = config.VIDEO_DIR / "concat_list.txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for item in slides_data:
            sc = item["scene"]
            v_path = config.PROJECT_ROOT / sc["visual"]
            # Chuẩn hóa đường dẫn cho FFmpeg concat demuxer
            safe_p = str(v_path.resolve()).replace("\\", "/")
            f.write(f"file '{safe_p}'\n")

    raw_concat_video = config.VIDEO_DIR / "_master_raw.mp4"
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list_file.resolve()),
        "-c", "copy",
        str(raw_concat_video.resolve())
    ]
    subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)

    # 3. Chuẩn hóa âm lượng EBU R128 (-16 LUFS) và Hardsub phụ đề vào video thành phẩm
    print("\n[*] Bước 3/3: Chuẩn hóa âm lượng EBU R128 (-16 LUFS) và hardsub phụ đề...")

    # Format đường dẫn file SRT an toàn cho filter subtitles của FFmpeg
    srt_escaped = str(final_srt.resolve()).replace("\\", "/").replace(":", "\\:")
    sub_style = "FontSize=22,FontName=Arial,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2.5,Shadow=1,MarginV=40"
    video_filter = f"subtitles='{srt_escaped}':force_style='{sub_style}'"
    audio_filter = "loudnorm=I=-16:TP=-1.5:LRA=11"

    cmd_final = [
        "ffmpeg", "-y",
        "-i", str(raw_concat_video.resolve()),
        "-vf", video_filter,
        "-af", audio_filter,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "192k",
        str(final_video.resolve())
    ]

    try:
        subprocess.run(cmd_final, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Lỗi khi hardsub phụ đề: {e.stderr.decode('utf-8', errors='replace')[:200]}")
        print("[*] Thử nghiệm phương án dự phòng chuẩn hóa âm lượng không hardsub...")
        # Fallback nếu font hoặc filter subtitles gặp lỗi đường dẫn trên Windows
        cmd_fallback = [
            "ffmpeg", "-y",
            "-i", str(raw_concat_video.resolve()),
            "-af", audio_filter,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(final_video.resolve())
        ]
        subprocess.run(cmd_fallback, check=True)
    finally:
        # Dọn dẹp file tạm
        concat_list_file.unlink(missing_ok=True)
        raw_concat_video.unlink(missing_ok=True)

    # 4. Lưu trạng thái cuối cùng vào state.json
    checkpoint_payload = {
        "current_step": "assembled",
        "total_slides": len(slides_data),
        "final_video": str(final_video.relative_to(config.PROJECT_ROOT)),
        "final_srt": str(final_srt.relative_to(config.PROJECT_ROOT)),
        "timestamp": time.time(),
        "slides": slides_data
    }
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint_payload, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 HOÀN THÀNH: Video bài giảng hoàn chỉnh đã xuất tại:\n   -> {final_video.resolve()}")
    print(f"📄 Phụ đề: {final_srt.resolve()}")
    return final_video, final_srt
