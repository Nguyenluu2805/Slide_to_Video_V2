"""
agents/render.py - Module Render Video từng slide bằng FFmpeg chuẩn V2
- Độ phân giải: 1920x1080 @ 30fps
- Hiệu ứng Ken Burns nhẹ nhàng: zoom 1.00 -> 1.05 mượt mà, không rung lắc
- Đồng bộ chuẩn xác thời lượng audio: Dừng 0.8s đầu slide trước khi nói, 1.5s cuối slide sau khi nói
- Checkpoint: Bỏ qua các slide đã render trước đó.
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

import config
from agents.voice import get_audio_duration_seconds


def render_single_slide_video(
    image_path: Path,
    audio_path: Path,
    output_mp4: Path,
    pre_pause: float = 0.8,
    post_pause: float = 1.5
) -> Path:
    """
    Render 1 slide ảnh + 1 file audio thành video MP4 1080p @ 30fps.
    Thời lượng khớp chính xác: Audio duration + pre_pause (0.8s) + post_pause (1.5s).
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Không tìm thấy ảnh slide: {image_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file audio: {audio_path}")

    output_mp4.parent.mkdir(parents=True, exist_ok=True)

    # 1. Đo thời lượng audio thật
    audio_dur = get_audio_duration_seconds(audio_path)
    total_dur = round(audio_dur + pre_pause + post_pause, 2)
    total_frames = int(round(total_dur * config.VIDEO_FPS))

    delay_ms = int(round(pre_pause * 1000))

    if getattr(config, "DRAFT_MODE", False):
        # Chế độ nháp: Render ảnh tĩnh, không qua zoompan, tốc độ nhanh vượt trội
        filter_complex = (
            f"[0:v]scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}[v];"
            f"[1:a]adelay=delays={delay_ms}:all=1,apad=pad_dur={post_pause}[a]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(config.VIDEO_FPS), "-loop", "1", "-i", str(image_path.resolve()),
            "-i", str(audio_path.resolve()),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-t", str(total_dur),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(output_mp4.resolve())
        ]
    else:
        # Bản cuối: Đưa ảnh vào như video 30fps thật (-framerate 30 -loop 1 -i slide.png)
        # và zoompan với d=1 để không nhân bản frame, loại bỏ hoàn toàn hiện tượng giật (judder)
        zoom_step = 0.05 / max(1, total_frames)
        filter_complex = (
            f"[0:v]scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT},"
            f"zoompan=z='min(zoom+{zoom_step:.8f},1.05)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}:fps={config.VIDEO_FPS}[v];"
            f"[1:a]adelay=delays={delay_ms}:all=1,apad=pad_dur={post_pause}[a]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(config.VIDEO_FPS), "-loop", "1", "-i", str(image_path.resolve()),
            "-i", str(audio_path.resolve()),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-t", str(total_dur),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(output_mp4.resolve())
        ]

    for attempt in range(1, 4):
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=True)
            if output_mp4.exists() and output_mp4.stat().st_size > 10240:
                return output_mp4
        except subprocess.CalledProcessError as e:
            print(f"[!] Lỗi render FFmpeg lần {attempt}/3: {e.stderr[:200]}")
            time.sleep(2)

    raise RuntimeError(f"Render video slide thất bại sau 3 lần thử: {output_mp4.name}")


def render_presentation_slides(slides_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Render toàn bộ slide thành video MP4 riêng lẻ kèm Checkpoint.
    """
    config.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    total_slides = len(slides_data)
    print(f"\n[*] Bắt đầu render video cho {total_slides} slide bằng FFmpeg 1080p @ 30fps...")

    pre_pause = getattr(config, "SLIDE_PRE_PAUSE", 0.8)
    post_pause = getattr(config, "SLIDE_POST_PAUSE", 1.5)

    for i, item in enumerate(slides_data, start=1):
        s = item["slide"]
        sc = item["scene"]
        sid = s["id"]
        title_disp = s.get("title", f"Slide {sid}")[:35]

        img_path = config.PROJECT_ROOT / s["image"]
        audio_path = config.PROJECT_ROOT / sc["audio_file"]
        target_video = config.VIDEO_DIR / f"slide_{sid:03d}.mp4"

        # Checkpoint: Nếu file video đã có và hợp lệ -> BỎ QUA
        if target_video.exists() and target_video.stat().st_size > 50000:
            sc["visual"] = str(target_video.relative_to(config.PROJECT_ROOT))
            sc["state"] = "rendered"
            print(f"[+] [Checkpoint] Bỏ qua Slide {sid}: Video đã sẵn sàng.")
            continue

        print(f"[*] [{i}/{total_slides}] Đang render video Slide {sid}: {title_disp}...")
        start_t = time.time()
        render_single_slide_video(
            image_path=img_path,
            audio_path=audio_path,
            output_mp4=target_video,
            pre_pause=pre_pause,
            post_pause=post_pause
        )
        elapsed = time.time() - start_t
        sc["visual"] = str(target_video.relative_to(config.PROJECT_ROOT))
        sc["state"] = "rendered"
        print(f"[+] Slide {sid} render thành công trong {elapsed:.1f}s.")

        # Lưu checkpoint sau mỗi slide
        checkpoint_payload = {
            "current_step": "rendered",
            "last_rendered_slide": sid,
            "total_slides": total_slides,
            "timestamp": time.time(),
            "slides": slides_data
        }
        with open(config.STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(checkpoint_payload, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Đã hoàn tất render toàn bộ {total_slides} video slide!")
    return slides_data
