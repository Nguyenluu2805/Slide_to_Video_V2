"""
Module: video_renderer.py
Description: Lap rap cac slide anh 1080p va file audio thanh video bai giang hoan chinh (.mp4)
             ho tro Chuyen canh tuan tu (Sequential Transition) sang Remotion Code Demo.
"""

import os
import sys
import json
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any

try:
    from . import config
    from .code_demo_bridge import render_code_demo_video, is_remotion_available
except (ImportError, ValueError):
    import config
    from code_demo_bridge import render_code_demo_video, is_remotion_available

def get_audio_duration(audio_path: str) -> float:
    """Lay thoi luong chinh xac cua file audio bang FFmpeg."""
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [ffmpeg_exe, "-i", audio_path]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="ignore")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if match:
        hours = float(match.group(1))
        minutes = float(match.group(2))
        seconds = float(match.group(3))
        return hours * 3600 + minutes * 60 + seconds
    return 5.0


def assemble_video(slide_items: List[Dict[str, Any]], output_video_path: Path) -> Path:
    """Lap rap tat ca slide va audio thanh video MP4 1080p bang FFmpeg voi co che chuyen canh tuan tu."""
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    temp_clips = []
    temp_dir = config.WORKSPACE_DIR / "temp_clips"
    temp_dir.mkdir(parents=True, exist_ok=True)
    for old_clip in temp_dir.glob("clip_*.mp4"):
        try: old_clip.unlink()
        except Exception: pass

    pre_pause = getattr(config, "SLIDE_PRE_PAUSE", 0.8)
    post_pause = getattr(config, "SLIDE_POST_PAUSE", 1.5)
    pre_ms = int(pre_pause * 1000)

    clip_counter = 1
    remotion_ready = is_remotion_available()

    for i, item in enumerate(slide_items, start=1):
        img_path = item["image_path"]
        audio_path = item["audio_path"]
        audio_dur = get_audio_duration(audio_path)

        has_demo = item.get("has_code_demo") and item.get("code_demo") and remotion_ready

        if not has_demo:
            # ================= SLIDE DON THUAN (LY THUYET) =================
            duration = round(audio_dur + pre_pause + post_pause, 2)
            clip_path = temp_dir / f"clip_{clip_counter:03d}.mp4"
            clip_counter += 1
            temp_clips.append(clip_path)

            cmd = [
                ffmpeg_exe, "-y",
                "-loop", "1",
                "-i", img_path,
                "-i", audio_path,
                "-filter_complex", f"[1:a]adelay=delays={pre_ms}:all=1,apad=pad_dur={post_pause}[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-r", "30",
                "-pix_fmt", "yuv420p",
                "-vf", f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2",
                "-t", str(duration),
                str(clip_path.resolve())
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        else:
            # ================= CHUYEN CANH TUAN TU: SLIDE -> CODE DEMO =================
            # Phan doan 1: Slide Intro (Hien thi slide kem loi dan nhap ngan)
            slide_intro_pause = 0.5
            intro_duration = round(audio_dur + 0.3 + slide_intro_pause, 2)
            clip_slide_intro = temp_dir / f"clip_{clip_counter:03d}_intro.mp4"
            clip_counter += 1
            temp_clips.append(clip_slide_intro)

            intro_cmd = [
                ffmpeg_exe, "-y",
                "-loop", "1",
                "-i", img_path,
                "-i", audio_path,
                "-filter_complex", f"[1:a]adelay=delays=300:all=1,apad=pad_dur={slide_intro_pause}[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-r", "30",
                "-pix_fmt", "yuv420p",
                "-vf", f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2",
                "-t", str(intro_duration),
                str(clip_slide_intro.resolve())
            ]
            subprocess.run(intro_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            # Phan doan 2: Full-screen Code Demo (Remotion IDE & Terminal)
            code_spec = item["code_demo"]
            code_audio_path = item.get("code_audio_path")
            total_demo_dur = code_spec.get("total_demo_dur")
            if not total_demo_dur:
                if code_audio_path and Path(code_audio_path).exists():
                    total_demo_dur = get_audio_duration(code_audio_path)
                else:
                    total_demo_dur = 20.0

            raw_remotion_mp4 = temp_dir / f"remotion_raw_{i:03d}.mp4"
            render_code_demo_video(
                code_spec=code_spec,
                audio_duration=total_demo_dur,
                output_mp4_path=raw_remotion_mp4,
                fps=30,
                show_subtitles=True
            )

            # Ghep audio thuyet minh vao video Remotion
            clip_code_demo = temp_dir / f"clip_{clip_counter:03d}_demo.mp4"
            clip_counter += 1
            temp_clips.append(clip_code_demo)

            demo_post_pause = 0.8
            demo_total_dur = round(total_demo_dur + demo_post_pause, 2)

            if code_audio_path:
                demo_cmd = [
                    ffmpeg_exe, "-y",
                    "-i", str(raw_remotion_mp4.resolve()),
                    "-i", str(code_audio_path),
                    "-filter_complex", f"[1:a]apad=pad_dur={demo_post_pause}[aout]",
                    "-map", "0:v",
                    "-map", "[aout]",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", "48000",
                    "-r", "30",
                    "-t", str(demo_total_dur),
                    str(clip_code_demo.resolve())
                ]
            else:
                demo_cmd = [
                    ffmpeg_exe, "-y",
                    "-i", str(raw_remotion_mp4.resolve()),
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-map", "0:v",
                    "-map", "1:a",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", "48000",
                    "-r", "30",
                    "-t", str(demo_total_dur),
                    str(clip_code_demo.resolve())
                ]
            subprocess.run(demo_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # ================= NOI TAT CA PHAN DOAN =================
    concat_list_file = temp_dir / "concat_list.txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for clip in temp_clips:
            f_path = str(clip.resolve()).replace("\\", "/")
            f.write(f"file '{f_path}'\n")

    concat_cmd = [
        ffmpeg_exe, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file.resolve()),
        "-c", "copy",
        str(output_video_path.resolve())
    ]
    subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_video_path


def run_video_renderer(slide_items: List[Dict[str, Any]] = None, output_name: str = "output_video.mp4") -> Path:
    """Ham thuc thi chinh cho Buoc 5: Render Video Hoan Chinh"""
    if slide_items is None:
        final_meta = config.WORKSPACE_DIR / "final_audio_meta.json"
        if not final_meta.exists():
            raise FileNotFoundError(f"Chua co file {final_meta}. Vui long chay Buoc 4 truoc.")
        with open(final_meta, "r", encoding="utf-8") as f:
            slide_items = json.load(f)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_video_path = config.OUTPUT_DIR / output_name

    final_video = assemble_video(slide_items, out_video_path)
    return final_video

run_step5 = run_video_renderer