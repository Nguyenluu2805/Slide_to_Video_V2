"""
agents/assemble.py - Module lắp ráp hoàn thiện video bài giảng V2
- Sinh phụ đề .ass và .srt chuẩn xác 100% trực tiếp từ kịch bản gốc (script.json)
  (Bảo toàn nguyên vẹn 99.9%, 30 giây, Ex01, LangGraph, Hybrid Workflow...)
- Style V2 tối giản: Trắng ngà #F5F5F4, từ khóa bọc đậm {\\b1}, chỉ viền mỏng (KHÔNG hộp nền, KHÔNG gradient đáy)
- Chia theo cụm ý (Quy tắc 3c): Mỗi lần hiện <= 11 từ VÀ <= 65 ký tự, thời lượng 1.2-3.5s, <= 20 ký tự/giây
- Tối đa 2 dòng, mỗi dòng <= 38 ký tự, căn giữa tuyệt đối, không có từ lẻ loi ở dòng 2
- Chuyển cảnh mềm (Quy tắc 4): xfade=transition=fade:duration=0.5 giữa các slide + acrossfade=d=0.5 cho audio
- Fade in 0.3s đầu video, fade out 0.3s cuối video
- Chỉ 1 lần encode cuối duy nhất: xfade -> fade in/out -> hardsub .ass -> loudnorm=I=-16:TP=-1.5:LRA=11
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
from agents.subtitle_pro import (
    build_ass_from_script,
    split_lines_balanced,
    chunk_text_pedagogical
)


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


def split_script_into_subtitle_blocks(script: str, max_words: int = 11, max_chars: int = 65) -> List[str]:
    """Chia kịch bản thành các khối phụ đề ngắn sư phạm (đồng bộ với ASS V2)."""
    return chunk_text_pedagogical(script, max_words=max_words, max_chars=max_chars)


def format_subtitle_text(text: str, max_chars_per_line: int = 38) -> str:
    """Format văn bản phụ đề cân bằng 2 dòng (tối đa 38 ký tự/dòng)."""
    balanced = split_lines_balanced(text, max_chars=max_chars_per_line)
    return balanced.replace(r"\N", "\n")


def generate_subtitles_from_script(
    slides_data: List[Dict[str, Any]],
    output_srt: Path,
    pre_pause: float = 0.8,
    post_pause: float = 1.5,
    use_crossfade: bool = True,
    crossfade_dur: float = 0.5
) -> Path:
    """
    Sinh file phụ đề .srt trực tiếp từ kịch bản gốc (script.json) chuẩn V2:
    1. Chữ đúng 100% kịch bản, bảo toàn nguyên vẹn thuật ngữ (99.9%, Ex01, LangGraph, Hybrid Workflow).
    2. Mỗi lần hiện <= 11 từ VÀ <= 65 ký tự, thời lượng 1.2-3.5s, <= 20 ký tự/giây.
    3. Tối đa 2 dòng, mỗi dòng <= 38 ký tự, không có từ lẻ loi ở dòng 2.
    4. Phân bổ thời gian theo tỷ lệ số từ và độ dài audio thực tế của từng slide.
    5. Khớp chính xác với offset chuyển cảnh xfade 0.5s giữa các slide.
    """
    srt_entries = []
    running_offset = 0.0
    subtitle_index = 1

    for idx, item in enumerate(slides_data):
        sc = item.get("scene", {})
        script = sc.get("script", "").strip()
        audio_file = config.PROJECT_ROOT / sc.get("audio_file", "")

        if not audio_file.exists() or not script:
            continue

        audio_dur = get_audio_duration_seconds(audio_file)
        slide_total_dur = round(audio_dur + pre_pause + post_pause, 2)

        if idx == 0:
            slide_start_offset = 0.0
            running_offset = slide_total_dur
        else:
            if use_crossfade:
                slide_start_offset = running_offset - crossfade_dur
                running_offset = slide_start_offset + slide_total_dur
            else:
                slide_start_offset = running_offset
                running_offset += slide_total_dur

        speech_start_offset = slide_start_offset + pre_pause

        cues = chunk_text_pedagogical(script, max_words=11, max_chars=65)

        weights = []
        for b in cues:
            words_count = len(b.split())
            bonus = 1.0 if b.endswith(('.', '!', '?')) else (0.5 if b.endswith((',', ';', ':')) else 0.0)
            weights.append(max(1.0, words_count + bonus))

        total_weight = sum(weights) if weights else 1.0
        durations = [(w / total_weight) * audio_dur for w in weights]

        curr_t = speech_start_offset
        for b, raw_dur in zip(cues, durations):
            dur = max(1.2, min(3.5, raw_dur))
            if dur > 0 and (len(b) / dur) > 20.0:
                dur = min(3.5, len(b) / 18.0)

            formatted_b = format_subtitle_text(b, max_chars_per_line=38)
            end_t = curr_t + dur
            srt_entries.append(
                f"{subtitle_index}\n"
                f"{format_srt_timestamp(curr_t)} --> {format_srt_timestamp(end_t)}\n"
                f"{formatted_b}\n"
            )
            subtitle_index += 1
            curr_t = end_t

    output_srt.parent.mkdir(parents=True, exist_ok=True)
    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries) + "\n")

    print(f"[+] Đã xuất file phụ đề chuẩn xác 100% từ kịch bản ({subtitle_index - 1} khối, max 11 từ / 65 ký tự, max 38 ký tự/dòng): {output_srt.name}")
    return output_srt


def assemble_final_video(
    slides_data: List[Dict[str, Any]],
    output_video_path: Optional[Path] = None,
    output_srt_path: Optional[Path] = None
) -> Tuple[Path, Path]:
    """
    Lắp ráp toàn bộ các đoạn slide video thành video thành phẩm V2:
    1. Sinh phụ đề .ass chuyên nghiệp (Style ProV2: trắng ngà #F5F5F4, từ khóa bọc đậm, KHÔNG hộp nền).
    2. Chuyển cảnh mềm (Bản cuối): Chỉ 1 lần encode cuối duy nhất:
       xfade 0.5s -> fade in/out 0.3s -> hardsub .ass -> loudnorm=I=-16:TP=-1.5:LRA=11.
    3. Bản nháp (--draft): Concat copy (hard cut) -> hardsub .ass + loudnorm.
    """
    config.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    final_video = output_video_path or config.FINAL_VIDEO_FILE
    final_srt = output_srt_path or config.FINAL_SRT_FILE

    pre_pause = getattr(config, "SLIDE_PRE_PAUSE", 0.8)
    post_pause = getattr(config, "SLIDE_POST_PAUSE", 1.5)
    draft_mode = getattr(config, "DRAFT_MODE", False)
    use_crossfade = (not draft_mode) and len(slides_data) > 1

    # 1. Sinh phụ đề chuyên nghiệp .ass V2 và .srt chuẩn
    print(f"\n[*] Bước 1/2: Sinh phụ đề thuyết minh V2 (Crossfade={use_crossfade})...")
    ass_path = config.VIDEO_DIR / "final_lecture.ass"
    build_ass_from_script(
        slides_data=slides_data,
        output_ass=ass_path,
        pre_pause=pre_pause,
        post_pause=post_pause,
        use_crossfade=use_crossfade,
        crossfade_dur=0.5
    )

    # Đồng thời xuất file .srt chuẩn phục vụ xuất bản / LMS
    generate_subtitles_from_script(
        slides_data=slides_data,
        output_srt=final_srt,
        pre_pause=pre_pause,
        post_pause=post_pause,
        use_crossfade=use_crossfade,
        crossfade_dur=0.5
    )

    # Chuẩn bị đường dẫn ASS và fontsdir an toàn cho FFmpeg
    ass_escaped = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
    fonts_dir_path = config.PROJECT_ROOT / "fonts"
    fonts_opt = f":fontsdir='{str(fonts_dir_path.resolve()).replace('\\', '/').replace(':', '\\:')}'" if fonts_dir_path.exists() else ""

    # 2. Xử lý video và audio
    if use_crossfade:
        print("\n[*] Bước 2/2: Thực hiện 1 lần encode duy nhất (xfade 0.5s + fade in/out 0.3s + hardsub V2 + loudnorm)...")
        slide_video_paths = []
        slide_durs = []
        for item in slides_data:
            sc = item["scene"]
            v_p = config.PROJECT_ROOT / sc["visual"]
            slide_video_paths.append(v_p)
            dur = get_audio_duration_seconds(v_p)
            slide_durs.append(dur)

        # Xây dựng lệnh FFmpeg duy nhất
        cmd_single = ["ffmpeg", "-y"]
        for vp in slide_video_paths:
            cmd_single.extend(["-i", str(vp.resolve())])

        v_filters = []
        a_filters = []
        last_v = "0:v"
        last_a = "0:a"
        running_dur = slide_durs[0]

        for i in range(1, len(slide_video_paths)):
            offset = max(0.1, running_dur - 0.5)
            out_v = f"v{i}"
            out_a = f"a{i}"
            v_filters.append(f"[{last_v}][{i}:v]xfade=transition=fade:duration=0.5:offset={offset:.2f}[{out_v}]")
            a_filters.append(f"[{last_a}][{i}:a]acrossfade=d=0.5[{out_a}]")
            running_dur = offset + slide_durs[i]
            last_v = out_v
            last_a = out_a

        fade_out_st = max(0.0, running_dur - 0.3)

        # Chuỗi filter hoàn thiện V2: xfade -> fade in/out -> hardsub .ass (KHÔNG hộp nền, KHÔNG gradient đáy)
        v_filters.append(
            f"[{last_v}]fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out_st:.2f}:d=0.3,subtitles='{ass_escaped}'{fonts_opt}[v_final]"
        )
        a_filters.append(
            f"[{last_a}]loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.3,afade=t=out:st={fade_out_st:.2f}:d=0.3[a_final]"
        )

        fc_single = ";".join(v_filters + a_filters)
        cmd_single.extend([
            "-filter_complex", fc_single,
            "-map", "[v_final]", "-map", "[a_final]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "192k",
            str(final_video.resolve())
        ])

        try:
            subprocess.run(cmd_single, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            print(f"[+] Encode duy nhất hoàn tất thành công: {final_video.name} ({running_dur:.1f}s)")
        except subprocess.CalledProcessError as e:
            err_text = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else str(e.stderr)
            print(f"[!] Lỗi xfade encode duy nhất: {err_text[:250]}")
            print("[*] Chuyển sang phương án dự phòng concat copy...")
            use_crossfade = False

    if not use_crossfade:
        print("\n[*] Bước 2/2: Nối các slide (Concat Demuxer) & Hardsub phụ đề V2...")
        concat_list_file = config.VIDEO_DIR / "concat_list.txt"
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for item in slides_data:
                sc = item["scene"]
                v_path = config.PROJECT_ROOT / sc["visual"]
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
        concat_list_file.unlink(missing_ok=True)

        total_final_dur = get_audio_duration_seconds(raw_concat_video)
        fade_out_st = max(0.0, total_final_dur - 0.3)

        cmd_final = [
            "ffmpeg", "-y",
            "-i", str(raw_concat_video.resolve()),
            "-vf", f"fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out_st:.2f}:d=0.3,subtitles='{ass_escaped}'{fonts_opt}",
            "-af", f"loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.3,afade=t=out:st={fade_out_st:.2f}:d=0.3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "192k",
            str(final_video.resolve())
        ]

        try:
            subprocess.run(cmd_final, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        except subprocess.CalledProcessError as e:
            err_text = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else str(e.stderr)
            print(f"[!] Lỗi khi hardsub phụ đề: {err_text[:250]}")
            print("[*] Fallback: Chuẩn hóa âm lượng EBU R128 không hardsub...")
            cmd_fallback = [
                "ffmpeg", "-y",
                "-i", str(raw_concat_video.resolve()),
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                str(final_video.resolve())
            ]
            subprocess.run(cmd_fallback, check=True)
        finally:
            raw_concat_video.unlink(missing_ok=True)

    # 3. Lưu trạng thái cuối cùng vào state.json
    try:
        final_video_rel = str(final_video.resolve().relative_to(config.PROJECT_ROOT.resolve()))
        final_srt_rel = str(final_srt.resolve().relative_to(config.PROJECT_ROOT.resolve()))
        final_ass_rel = str(ass_path.resolve().relative_to(config.PROJECT_ROOT.resolve()))
    except Exception:
        final_video_rel = str(final_video)
        final_srt_rel = str(final_srt)
        final_ass_rel = str(ass_path)

    checkpoint_payload = {
        "current_step": "assembled",
        "total_slides": len(slides_data),
        "final_video": final_video_rel,
        "final_srt": final_srt_rel,
        "final_ass": final_ass_rel,
        "timestamp": time.time(),
        "slides": slides_data
    }
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint_payload, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 HOÀN THÀNH: Video bài giảng V2 hoàn chỉnh đã xuất tại:\n   -> {final_video.resolve()}")
    print(f"📄 Phụ đề ASS V2: {ass_path.resolve()}")
    print(f"📄 Phụ đề SRT V2: {final_srt.resolve()}")
    return final_video, final_srt
