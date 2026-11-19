"""
config.py - Cấu hình tập trung cho AI Video Agent V2
Single Source of Truth cho toàn bộ hệ thống.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Đảm bảo xuất UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thư mục gốc dự án
PROJECT_ROOT = Path(__file__).resolve().parent

# Tải file .env từ thư mục gốc
load_dotenv(PROJECT_ROOT / ".env")

# Thư mục dữ liệu & đầu ra V2
TEST_DATA_DIR = PROJECT_ROOT / "test_data"
INPUT_DIR = PROJECT_ROOT / "input"
OUTPUT_DIR = PROJECT_ROOT / "output"
SLIDES_DIR = OUTPUT_DIR / "slides"
AUDIO_DIR = OUTPUT_DIR / "audio"
VIDEO_DIR = OUTPUT_DIR / "video"

# Các file đầu ra chuẩn V2
STATE_FILE = OUTPUT_DIR / "state.json"
SCRIPT_FILE = OUTPUT_DIR / "script.json"
FINAL_VIDEO_FILE = VIDEO_DIR / "final_lecture.mp4"
FINAL_SRT_FILE = VIDEO_DIR / "final_lecture.srt"

# Tự động tạo các thư mục cần thiết
for directory in [INPUT_DIR, TEST_DATA_DIR, OUTPUT_DIR, SLIDES_DIR, AUDIO_DIR, VIDEO_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# 1. Cấu hình Gemini LLM
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# 2. Cấu hình Voice / TTS
# TTS_PROVIDER: "zerotts" (chính) | "edge-tts" (dự phòng) | "gemini-tts" (dự phòng 2)
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "zerotts").lower()
TTS_VOICE = os.getenv("TTS_VOICE", "zerotts:maichi")
ZEROTTS_MODEL = os.getenv("ZEROTTS_MODEL", "zeroweight-ai/ZeroTTS")
ZEROTTS_VOICE = os.getenv("ZEROTTS_VOICE", "maichi")
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "vi-VN-NamMinhNeural")
TTS_RATE = os.getenv("TTS_RATE", "-10%")
TTS_VOLUME = os.getenv("TTS_VOLUME", "+0%")

# 3. Cấu hình Whisper (Phụ đề .srt)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")

# 4. Cấu hình Video Rendering & Draft Mode
DRAFT_MODE = os.getenv("DRAFT_MODE", "false").lower() in ("true", "1", "yes")
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1920"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1080"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "30"))
SLIDE_PRE_PAUSE = float(os.getenv("SLIDE_PRE_PAUSE", "0.8"))    # Dừng 0.8s đầu slide trước khi nói
SLIDE_POST_PAUSE = float(os.getenv("SLIDE_POST_PAUSE", "1.5"))  # Dừng 1.5s cuối slide sau khi nói xong
SLIDE_PAUSE_DURATION = SLIDE_PRE_PAUSE + SLIDE_POST_PAUSE

# 5. Hàm kiểm tra thiết bị phần cứng thực tế (Không báo khống)
def get_hardware_device_info() -> dict:
    """Trả về thông tin thiết bị thực tế (CPU hoặc GPU CUDA)."""
    try:
        import torch
        if torch.cuda.is_available():
            dev_name = torch.cuda.get_device_name(0)
            return {"device": "cuda", "device_name": dev_name, "is_gpu": True}
    except Exception:
        pass
    return {"device": "cpu", "device_name": "CPU", "is_gpu": False}
