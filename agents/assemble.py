"""
agents/assemble.py - Module lắp ráp hoàn thiện video bài giảng V2
- Sinh phụ đề .ass và .srt chuẩn xác 100% trực tiếp từ kịch bản gốc (script.json)
  (Bảo toàn nguyên vẹn 99.9%, 30 giây, Ex01, LangGraph, Hybrid Workflow...)
- Style V2 hiện đại: Trắng ngà #F5F5F4, từ khóa bọc đậm {\\b1}, không hộp đen, gradient mờ ở đáy
- Tối đa 2 dòng, 38 ký tự/dòng, căn giữa tuyệt đối, không có từ lẻ loi ở dòng 2
- Chuyển cảnh mượt xfade 0.5s giữa các slide + acrossfade âm thanh
- Fade in/out 0.3s đầu và cuối video, thanh tiến trình mỏng 2px ở đáy
- Chuẩn hóa âm lượng EBU R128 (-16 LUFS)
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
from agents.subtitle_pro import build_ass_from_script, split_lines_balanced, _split_into_clauses_v2


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


def split_script_into_subtitle_blocks(script: str, max_words: int = 11, min_words: int = 4) -> List[str]:
    """Chia kịch bản thành các khối phụ đề ngắn sư phạm (đồng bộ với ASS V2)."""
    return _split_into_clauses_v2(script, max_words=max_words, min_words=min_words)


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
    2. Chia nhỏ thành câu ngắn: tối đa 2 dòng, 38 ký tự/dòng, 1-5 giây/câu.
    3. Phân bổ thời gian theo tỷ lệ số từ và độ dài audio thực tế của từng slide.
    4. Khớp chính xác với offset chuyển cảnh xfade 0.5s giữa các slide.
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

        raw_blocks = split_script_into_subtitle_blocks(script, max_words=11, min_words=4)

        weights = []
        for b in raw_blocks:
            words_count = len(b.split())
            bonus = 1.0 if b.endswith(('.', '!', '?')) else (0.5 if b.endswith((',', ';', ':')) else 0.0)
            weights.append(max(1.0, words_count + bonus))

        total_weight = sum(weights) if weights else 1.0
        durations = [(w / total_weight) * audio_dur for w in weights]

        curr_t = speech_start_offset
        for b, dur in zip(raw_blocks, durations):
            dur = max(1.0, min(5.0, dur))
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

    print(f"[+] Đã xuất file phụ đề chuẩn xác 100% từ kịch bản ({subtitle_index - 1} khối, max 38 ký tự/dòng): {output_srt.name}")
    return output_srt


def assemble_final_video(
    slides_data: List[Dict[str, Any]],
    output_video_path: Optional[Path] = None,
    output_srt_path: Optional[Path] = None
) -> Tuple[Path, Path]:
    """
    Lắp ráp toàn bộ các đoạn slide video thành video thành phẩm V2:
    1. Sinh phụ đề .ass chuyên nghiệp (Style ProV2: trắng ngà #F5F5F4, từ khóa bọc đậm, không hộp đen).
    2. Nối slide bằng xfade 0.5s fade (bản cuối) hoặc concat copy (bản nháp).
    3. Thêm lớp gradient mờ ở đáy, thanh tiến trình 2px, fade in/out 0.3s, loudnorm -16 LUFS và hardsub.
    """
    config.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    final_video = output_video_path or config.FINAL_VIDEO_FILE
    final_srt = output_srt_path or config.FINAL_SRT_FILE

    pre_pause = getattr(config, "SLIDE_PRE_PAUSE", 0.8)
    post_pause = getattr(config, "SLIDE_POST_PAUSE", 1.5)
    draft_mode = getattr(config, "DRAFT_MODE", False)
    use_crossfade = (not draft_mode) and len(slides_data) > 1

    # 1. Sinh phụ đề chuyên nghiệp .ass V2 và .srt chuẩn
    print(f"\n[*] Bước 1/3: Sinh phụ đề thuyết minh chuyên nghiệp V2 (Crossfade={use_crossfade})...")
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

    # 2. Nối các đoạn slide video (xfade 0.5s bản cuối, concat copy bản nháp)
    raw_concat_video = config.VIDEO_DIR / "_master_raw.mp4"

    if use_crossfade:
        print("\n[*] Bước 2/3: Nối các slide bằng chuyển cảnh mềm xfade 0.5s + acrossfade...")
        # Lấy danh sách video đầu vào và đo thời lượng thực tế
        slide_video_paths = []
        slide_durs = []
        for item in slides_data:
            sc = item["scene"]
            v_p = config.PROJECT_ROOT / sc["visual"]
            slide_video_paths.append(v_p)
            dur = get_audio_duration_seconds(v_p)
            slide_durs.append(dur)

        # Xây dựng lệnh FFmpeg xfade
        cmd_xfade = ["ffmpeg", "-y"]
        for vp in slide_video_paths:
            cmd_xfade.extend(["-i", str(vp.resolve())])

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

        fc_xfade = ";".join(v_filters + a_filters)
        cmd_xfade.extend([
            "-filter_complex", fc_xfade,
            "-map", f"[{last_v}]", "-map", f"[{last_a}]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "192k",
            str(raw_concat_video.resolve())
        ])

        try:
            subprocess.run(cmd_xfade, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            print(f"[+] Nối xfade hoàn tất: {raw_concat_video.name} ({running_dur:.1f}s)")
        except subprocess.CalledProcessError as e:
            print(f"[!] Lỗi xfade, tự động chuyển về phương án nối concat copy: {e.stderr[:200]}")
            use_crossfade = False

    if not use_crossfade:
        print("\n[*] Bước 2/3: Nối các đoạn slide video bằng Concat Demuxer (Hard Cut)...")
        concat_list_file = config.VIDEO_DIR / "concat_list.txt"
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for item in slides_data:
                sc = item["scene"]
                v_path = config.PROJECT_ROOT / sc["visual"]
                safe_p = str(v_path.resolve()).replace("\\", "/")
                f.write(f"file '{safe_p}'\n")

        cmd_concat = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list_file.resolve()),
            "-c", "copy",
            str(raw_concat_video.resolve())
        ]
        subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        concat_list_file.unlink(missing_ok=True)

    # 3. Chuẩn hóa âm lượng EBU R128, vẽ gradient đáy, thanh tiến trình 2px, fade in/out và hardsub
    print("\n[*] Bước 3/3: Mastering video V2 (Gradient mờ đáy, Fade in/out, Thanh tiến trình 2px, Hardsub ProV2 & Loudnorm)...")

    total_final_dur = get_audio_duration_seconds(raw_concat_video)
    fade_out_st = max(0.0, total_final_dur - 0.3)

    ass_escaped = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
    fonts_dir_path = config.PROJECT_ROOT / "fonts"
    fonts_opt = f":fontsdir='{str(fonts_dir_path.resolve()).replace('\\', '/').replace(':', '\\:')}'" if fonts_dir_path.exists() else ""

    video_width = getattr(config, "VIDEO_WIDTH", 1920)

    # Chuỗi filter hoàn chỉnh theo chuẩn V2:
    # 1. gradients tạo dải màu đen mờ dần từ 0% ở trên đến 60% ở đáy (cao 220px)
    # 2. overlay dải gradient vào đáy video (H-h)
    # 3. drawbox vẽ thanh tiến trình mỏng 2px màu trắng mờ chạy suốt video
    # 4. fade in 0.3s đầu, fade out 0.3s cuối video
    # 5. subtitles hardsub phụ đề ASS chuẩn ProV2
    # 6. loudnorm -16 LUFS và afade in/out 0.3s cho âm thanh
    fc_master = (
        f"gradients=s={video_width}x220:c0=0x00000000:c1=0x00000099:x0={video_width//2}:y0=0:x1={video_width//2}:y1=220[grad];"
        f"[0:v][grad]overlay=0:H-h:shortest=1[v_grad];"
        f"[v_grad]drawbox=x=0:y=ih-2:w='iw*(t/{total_final_dur:.2f})':h=2:color=white@0.35:t=fill[v_pb];"
        f"[v_pb]fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out_st:.2f}:d=0.3[v_fade];"
        f"[v_fade]subtitles='{ass_escaped}'{fonts_opt}[v_final];"
        f"[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.3,afade=t=out:st={fade_out_st:.2f}:d=0.3[a_final]"
    )

    cmd_final = [
        "ffmpeg", "-y",
        "-i", str(raw_concat_video.resolve()),
        "-filter_complex", fc_master,
        "-map", "[v_final]", "-map", "[a_final]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "192k",
        str(final_video.resolve())
    ]

    try:
        subprocess.run(cmd_final, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        err_text = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else str(e.stderr)
        print(f"[!] Lỗi khi mastering video: {err_text[:250]}")
        print("[*] Thử nghiệm phương án dự phòng đơn giản hóa filter...")
        # Fallback an toàn nếu filter phức tạp gặp trục trặc
        fallback_vf = f"subtitles='{ass_escaped}'{fonts_opt}" if ass_path.exists() else "null"
        cmd_fallback = [
            "ffmpeg", "-y",
            "-i", str(raw_concat_video.resolve()),
            "-vf", fallback_vf,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "192k",
            str(final_video.resolve())
        ]
        subprocess.run(cmd_fallback, check=True)
    finally:
        raw_concat_video.unlink(missing_ok=True)

    # 4. Lưu trạng thái cuối cùng vào state.json
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
