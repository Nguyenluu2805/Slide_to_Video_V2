"""
agents/assemble.py - Module lắp ráp hoàn thiện video bài giảng V2
- Trích xuất phụ đề .srt tiếng Việt khớp timestamp thật bằng Faster-Whisper
- Chuẩn hóa âm lượng EBU R128 (-16 LUFS)
- Hardsub phụ đề vào video
- Nối các đoạn slide video thành video thành phẩm: output/video/final_lecture.mp4
"""

import os
import sys
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


def extract_presentation_subtitles(
    slides_data: List[Dict[str, Any]],
    output_srt: Path,
    pre_pause: float = 0.8,
    post_pause: float = 1.5
) -> Path:
    """
    Trích xuất phụ đề .srt chuẩn thời gian thật cho toàn bộ bài giảng bằng Faster-Whisper.
    Tự động bù trừ khoảng nghỉ pre_pause (0.8s) và post_pause (1.5s) cho từng slide.
    """
    from faster_whisper import WhisperModel

    model_size = getattr(config, "WHISPER_MODEL_SIZE", "base")
    device = getattr(config, "WHISPER_DEVICE", "cpu")

    print(f"[*] Đang tải mô hình Faster-Whisper ({model_size}) để trích xuất phụ đề...")
    whisper_model = WhisperModel(model_size, device=device, compute_type="int8")

    srt_entries = []
    current_time_offset = 0.0
    subtitle_index = 1

    for item in slides_data:
        s = item["slide"]
        sc = item["scene"]
        sid = s["id"]
        audio_file = config.PROJECT_ROOT / sc["audio_file"]

        if not audio_file.exists():
            continue

        audio_dur = get_audio_duration_seconds(audio_file)
        # Giọng đọc bắt đầu sau khoảng pre_pause
        speech_start_offset = current_time_offset + pre_pause

        segments, _ = whisper_model.transcribe(
            str(audio_file.resolve()),
            language="vi",
            beam_size=5,
            vad_filter=True
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

        # Tổng thời lượng của slide bao gồm cả 2 khoảng nghỉ
        slide_total_dur = round(audio_dur + pre_pause + post_pause, 2)
        current_time_offset += slide_total_dur

    output_srt.parent.mkdir(parents=True, exist_ok=True)
    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries) + "\n")

    print(f"[+] Đã xuất file phụ đề khớp timestamp thật ({len(srt_entries)} dòng): {output_srt.name}")
    return output_srt


def assemble_final_video(
    slides_data: List[Dict[str, Any]],
    output_video_path: Optional[Path] = None,
    output_srt_path: Optional[Path] = None
) -> Tuple[Path, Path]:
    """
    Lắp ráp toàn bộ các đoạn slide video thành video thành phẩm:
    1. Nối các slide video bằng FFmpeg concat demuxer.
    2. Trích xuất phụ đề .srt bằng Faster-Whisper.
    3. Chuẩn hóa âm thanh loudnorm -16 LUFS và hardsub phụ đề.
    """
    config.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    final_video = output_video_path or config.FINAL_VIDEO_FILE
    final_srt = output_srt_path or config.FINAL_SRT_FILE

    pre_pause = getattr(config, "SLIDE_PRE_PAUSE", 0.8)
    post_pause = getattr(config, "SLIDE_POST_PAUSE", 1.5)

    # 1. Trích xuất phụ đề Faster-Whisper
    print("\n[*] Bước 1/3: Trích xuất phụ đề tiếng Việt với Faster-Whisper...")
    extract_presentation_subtitles(
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
    sub_style = "FontSize=20,FontName=Arial,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=2,Shadow=1,MarginV=35"
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
