"""
Module: pipeline.py
Description: Quản lý và điều phối toàn bộ luồng 5 bước tự động hóa chuyển PPTX thành Video.
"""

import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Dict, Any

try:
    from . import config
    from .extractor import run_extractor
    from .script_gen import run_script_generator
    from .tts_engine import run_tts_engine
    from .voice_cloner import run_voice_cloner
    from .video_renderer import run_video_renderer
except (ImportError, ValueError):
    import config
    from extractor import run_extractor
    from script_gen import run_script_generator
    from tts_engine import run_tts_engine
    from voice_cloner import run_voice_cloner
    from video_renderer import run_video_renderer

def format_duration(seconds: float) -> str:
    """Định dạng thời gian chạy thành chuỗi thân thiện (ví dụ: 3.4s, 1m 24s)."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}m {secs:.1f}s"


def run_full_pipeline(
    pptx_path: Path,
    custom_scripts: Optional[list] = None,
    gemini_api_key: Optional[str] = None,
    voice_name: Optional[str] = None,
    tts_rate: Optional[str] = None,
    enable_rvc: bool = False,
    output_filename: str = "output_video.mp4",
    on_progress: Optional[Callable] = None,
    slide_pause: Optional[float] = None
) -> Path:
    """Thực thi quy trình 5 bước hoàn chỉnh từ PPTX đến Video MP4 với đo đạc thời gian từng giai đoạn."""
    pipeline_start = time.perf_counter()
    
    stage_timings = {
        "step_1": {"key": "extract", "name": "Trích xuất Slide", "duration": 0.0, "status": "pending", "formatted": ""},
        "step_2": {"key": "script", "name": "Tạo Kịch Bản", "duration": 0.0, "status": "pending", "formatted": ""},
        "step_3": {"key": "tts", "name": "Tổng Hợp Giọng Nói", "duration": 0.0, "status": "pending", "formatted": ""},
        "step_4": {"key": "voice_clone", "name": "Chuyển Đổi Âm Sắc", "duration": 0.0, "status": "pending", "formatted": ""},
        "step_5": {"key": "render", "name": "Render Video 1080p", "duration": 0.0, "status": "pending", "formatted": ""},
        "total_duration": 0.0,
        "total_formatted": "0.0s"
    }

    def log(step: str, pct: int, msg: str, step_key: Optional[str] = None, elapsed: Optional[float] = None):
        total_so_far = time.perf_counter() - pipeline_start
        stage_timings["total_duration"] = round(total_so_far, 2)
        stage_timings["total_formatted"] = format_duration(total_so_far)

        if step_key and step_key in stage_timings:
            if elapsed is not None:
                stage_timings[step_key]["duration"] = round(elapsed, 2)
                stage_timings[step_key]["status"] = "completed"
                stage_timings[step_key]["formatted"] = format_duration(elapsed)
            else:
                stage_timings[step_key]["status"] = "running"

        if on_progress:
            try:
                # Thử gọi với 4 tham số (hỗ trợ timings payload)
                on_progress(step, pct, msg, stage_timings)
            except TypeError:
                # Tương thích ngược nếu callback chỉ nhận 3 tham số
                on_progress(step, pct, msg)

        print(f"[{pct}%] [{step}] {msg}")

    # ==================== BƯỚC 1: TRÍCH XUẤT SLIDE ====================
    log("Bước 1: Trích xuất Slide", 10, f"Đang đọc file PowerPoint: {pptx_path.name}...", step_key="step_1")
    t0 = time.perf_counter()
    slides_data = run_extractor(pptx_path)
    t_extract = time.perf_counter() - t0
    log("Bước 1: Trích xuất Slide", 25, f"Đã xuất thành công {len(slides_data)} trang slide độ phân giải 1080p ({format_duration(t_extract)}).", step_key="step_1", elapsed=t_extract)

    # ==================== BƯỚC 2: TẠO KỊCH BẢN ====================
    log("Bước 2: Tạo Kịch Bản", 30, "Đang khởi tạo lời giảng sư phạm cho từng slide...", step_key="step_2")
    t0 = time.perf_counter()
    if custom_scripts:
        try:
            from .script_gen import post_process_code_demos
        except (ImportError, ValueError):
            import script_gen
            post_process_code_demos = script_gen.post_process_code_demos
        scripts = post_process_code_demos(custom_scripts)
        t_script = time.perf_counter() - t0
        log("Bước 2: Tạo Kịch Bản", 45, f"Đã nạp {len(scripts)} kịch bản tùy chỉnh của bạn ({format_duration(t_script)}).", step_key="step_2", elapsed=t_script)
    else:
        scripts = run_script_generator(slides_data, gemini_api_key=gemini_api_key)
        t_script = time.perf_counter() - t0
        log("Bước 2: Tạo Kịch Bản", 45, f"AI đã hoàn thành kịch bản sư phạm cho {len(scripts)} slide ({format_duration(t_script)}).", step_key="step_2", elapsed=t_script)

    # ==================== BƯỚC 3: TỔNG HỢP GIỌNG NÓI TTS ====================
    selected_rate = tts_rate or config.TTS_RATE or "-10%"
    log("Bước 3: Tổng Hợp Giọng Nói", 50, "Đang tổng hợp giọng đọc bài giảng sư phạm...", step_key="step_3")
    t0 = time.perf_counter()
    base_audio = run_tts_engine(scripts, voice_name=voice_name, rate=selected_rate, on_progress=on_progress)
    t_tts = time.perf_counter() - t0
    log("Bước 3: Tổng Hợp Giọng Nói", 70, f"Đã tạo hoàn chỉnh {len(base_audio)} file âm thanh lồng tiếng ({format_duration(t_tts)}).", step_key="step_3", elapsed=t_tts)

    # ==================== BƯỚC 4: TỐI ƯU / CLONE GIỌNG NÓI ====================
    log("Bước 4: Chuyển Đổi Âm Sắc", 75, "Đang xử lý Voice Cloning / Tối ưu âm thanh...", step_key="step_4")
    t0 = time.perf_counter()
    final_audio = run_voice_cloner(base_audio, enable_rvc=enable_rvc)
    t_voice = time.perf_counter() - t0
    log("Bước 4: Chuyển Đổi Âm Sắc", 85, f"Âm thanh đã sẵn sàng cho bước ghép video ({format_duration(t_voice)}).", step_key="step_4", elapsed=t_voice)

    # ==================== BƯỚC 5: RENDER VIDEO 1080P ====================
    if slide_pause is not None:
        try:
            sp = float(slide_pause)
            config.SLIDE_PRE_PAUSE = min(1.0, round(sp * 0.35, 2))
            config.SLIDE_POST_PAUSE = max(0.5, round(sp - config.SLIDE_PRE_PAUSE, 2))
            config.SLIDE_PAUSE_DURATION = config.SLIDE_PRE_PAUSE + config.SLIDE_POST_PAUSE
        except Exception:
            pass

    log("Bước 5: Render Video 1080p", 90, f"Đang xuất video bài giảng cuối cùng ({output_filename} • Dừng chuyển slide: {getattr(config, 'SLIDE_PAUSE_DURATION', 2.3)}s)...", step_key="step_5")
    t0 = time.perf_counter()
    output_video = run_video_renderer(final_audio, output_name=output_filename)
    t_render = time.perf_counter() - t0
    log("Bước 5: Render Video 1080p", 98, f"Render video hoàn tất ({format_duration(t_render)}).", step_key="step_5", elapsed=t_render)

    total_time = time.perf_counter() - pipeline_start
    stage_timings["total_duration"] = round(total_time, 2)
    stage_timings["total_formatted"] = format_duration(total_time)

    # Báo cáo tổng kết thời gian
    print("\n" + "=" * 62)
    print("BẢNG TỔNG KẾT THỜI GIAN THỰC THI TỪNG GIAI ĐOẠN")
    print("-" * 62)
    print(f" 1. Trích xuất Slide PPTX    : {format_duration(t_extract):>8}  ({(t_extract/total_time)*100:4.1f}%)")
    print(f" 2. Tạo Kịch Bản AI          : {format_duration(t_script):>8}  ({(t_script/total_time)*100:4.1f}%)")
    print(f" 3. Tổng Hợp Giọng Nói TTS   : {format_duration(t_tts):>8}  ({(t_tts/total_time)*100:4.1f}%)")
    print(f" 4. Chuyển Đổi Âm Sắc / RVC  : {format_duration(t_voice):>8}  ({(t_voice/total_time)*100:4.1f}%)")
    print(f" 5. Render Video 1080p       : {format_duration(t_render):>8}  ({(t_render/total_time)*100:4.1f}%)")
    print("-" * 62)
    print(f" TỔNG THỜI GIAN TOÀN BỘ   : {format_duration(total_time):>8} (100.0%)")
    print("=" * 62 + "\n")

    log("Hoàn Thành", 100, f"Video bài giảng đã được render thành công: {output_video.name} (Tổng thời gian: {format_duration(total_time)})")

    # Lưu lại bảng timings vào output_video nếu hỗ trợ
    try:
        setattr(output_video, "timings", stage_timings)
    except Exception:
        pass
    return output_video
