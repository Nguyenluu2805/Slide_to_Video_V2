"""
Module: code_demo_bridge.py
Description: Cầu nối điều khiển Remotion CLI trong repo code-demo-ai để render video
             mô phỏng gõ code và terminal với tốc độ điềm đạm, chuẩn nhịp người thật.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    from . import config
except (ImportError, ValueError):
    import config

def is_remotion_available() -> bool:
    """Kiểm tra xem thư mục code_demo_ai và npm/npx có sẵn sàng không."""
    code_demo_dir = getattr(config, "CODE_DEMO_DIR", config.PROJECT_ROOT / "code_demo_ai")
    if not code_demo_dir.exists():
        return False
    
    node_modules = code_demo_dir / "node_modules"
    if not node_modules.exists():
        return False

    npx_bin = shutil.which("npx") or shutil.which("npx.cmd")
    return npx_bin is not None


def format_code_demo_props(
    code_spec: Dict[str, Any],
    total_duration_sec: float,
    fps: int = 30,
    show_subtitles: bool = True
) -> Dict[str, Any]:
    """
    Chuyển đổi thông số code_demo sang cấu trúc Storyboard của code-demo-ai
    với thời lượng rộng rãi, nhịp độ điềm đạm, dễ đọc và dễ hiểu.
    """
    title = code_spec.get("title", "Code Demonstration")
    filename = code_spec.get("filename", "main.py")
    language = code_spec.get("language", "python").lower()
    code = code_spec.get("code", "").strip()
    terminal_command = code_spec.get("terminal_command", "").strip()
    terminal_output = code_spec.get("terminal_output", "").strip()
    theme = code_spec.get("theme", "one-dark")
    editor_narration = code_spec.get("editor_narration", "")
    terminal_narration = code_spec.get("terminal_narration", "")
    has_terminal = bool(terminal_command or terminal_output)

    # Đọc thời lượng chính xác từ metadata đã tính toán ở Bước 3 TTS nếu có
    if "editor_frames" in code_spec and "terminal_frames" in code_spec:
        editor_frames = int(code_spec["editor_frames"])
        terminal_frames = int(code_spec["terminal_frames"]) if has_terminal else 0
        total_frames = editor_frames + terminal_frames
    else:
        # Tối thiểu 20 giây (600 frames) cho toàn bộ demo nếu không có metadata chi tiết
        total_frames = max(600, int(round(total_duration_sec * fps)))
        if has_terminal:
            terminal_frames = max(270, int(round(total_frames * 0.42)))
            editor_frames = max(330, total_frames - terminal_frames)
            total_frames = editor_frames + terminal_frames
        else:
            editor_frames = total_frames
            terminal_frames = 0

    # Tính toán startTypingFromLine thông minh:
    # Nếu code dài (> 4 dòng), các dòng import/setup sẽ xuất hiện sẵn trên màn hình,
    # chỉ gõ chủ động từ 2 đến 3 dòng logic trọng tâm để tránh hiệu ứng gõ quá nhanh.
    raw_lines = code.split('\n')
    start_typing = code_spec.get("start_typing_from_line", 1)
    if start_typing == 1 and len(raw_lines) > 4:
        non_empty = [idx for idx, l in enumerate(raw_lines) if l.strip()]
        if len(non_empty) > 3:
            start_typing = max(1, non_empty[-2] + 1)

    scenes: List[Dict[str, Any]] = []

    # Scene 1: Code Editor typing & zoom
    scenes.append({
        "id": "scene-editor-1",
        "type": "editor",
        "filename": filename,
        "language": language,
        "code": code,
        "startTypingFromLine": start_typing,
        "highlightLines": code_spec.get("highlight_lines", []),
        "zoomScale": 1.05,
        "focusLine": code_spec.get("focus_line", start_typing),
        "speakerScript": editor_narration or code_spec.get("narration", ""),
        "durationInFrames": editor_frames
    })

    # Scene 2: Terminal execution
    if has_terminal:
        scenes.append({
            "id": "scene-terminal-2",
            "type": "terminal",
            "command": terminal_command or f"python {filename}",
            "output": terminal_output or "Program executed successfully.",
            "speakerScript": terminal_narration or "",
            "durationInFrames": terminal_frames
        })

    return {
        "storyboard": {
            "title": title,
            "description": code_spec.get("description", ""),
            "aspectRatio": "16:9",
            "theme": theme,
            "fps": fps,
            "scenes": scenes
        },
        "showSubtitles": show_subtitles
    }


def render_code_demo_video(
    code_spec: Dict[str, Any],
    audio_duration: float,
    output_mp4_path: Path,
    fps: int = 30,
    show_subtitles: bool = True
) -> Path:
    """Render video MP4 mô phỏng IDE bằng Remotion CLI."""
    code_demo_dir = getattr(config, "CODE_DEMO_DIR", config.PROJECT_ROOT / "code_demo_ai")
    if not code_demo_dir.exists():
        raise RuntimeError(f"Không tìm thấy thư mục code-demo-ai tại {code_demo_dir}")

    entry_point = "src/remotion/index.ts"
    composition_id = "CodeDemo"

    output_mp4_path = Path(output_mp4_path).resolve()
    output_mp4_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Tạo file props JSON tạm thời
    props_data = format_code_demo_props(
        code_spec=code_spec,
        total_duration_sec=audio_duration,
        fps=fps,
        show_subtitles=show_subtitles
    )

    temp_props_file = config.WORKSPACE_DIR / f"props_demo_{output_mp4_path.stem}.json"
    with open(temp_props_file, "w", encoding="utf-8") as f:
        json.dump(props_data, f, ensure_ascii=False, indent=2)

    # 2. Xây dựng lệnh gọi Remotion CLI
    npx_bin = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    cmd = [
        npx_bin,
        "remotion",
        "render",
        entry_point,
        composition_id,
        str(output_mp4_path),
        f"--props={str(temp_props_file.resolve())}",
        "--concurrency=8",
        "--gl=angle"
    ]

    tot_f = sum(s["durationInFrames"] for s in props_data["storyboard"]["scenes"])

    print(f"[*] Đang render Code Demo video bằng Remotion: {output_mp4_path.name} (thời lượng: {tot_f/fps:.1f}s, tổng frames: {tot_f})...")

    # 3. Thực thi subprocess
    result = subprocess.run(
        cmd,
        cwd=str(code_demo_dir),
        capture_output=True,
        text=True,
        shell=sys.platform == "win32",
        encoding="utf-8",
        errors="replace"
    )

    if result.returncode != 0:
        err_msg = result.stderr or result.stdout
        print(f"[!] Lỗi khi render Remotion: " + str(err_msg))
        raise RuntimeError(f"Lỗi khi render Remotion Code Demo: {err_msg[:400]}")

    if not output_mp4_path.exists() or output_mp4_path.stat().st_size == 0:
        raise RuntimeError(f"Remotion báo hoàn thành nhưng không tìm thấy file output: {output_mp4_path}")

    print(f"[+] Render Code Demo hoàn tất: {output_mp4_path.name} ({output_mp4_path.stat().st_size / 1024:.1f} KB)")
    return output_mp4_path