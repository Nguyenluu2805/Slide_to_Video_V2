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
# TTS_PROVIDER: "zerotts" (chính) | "edge-tts" (dự phòng) | "gtts" (cứu hộ)
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "zerotts").lower()
TTS_VOICE = os.getenv("TTS_VOICE", "zerotts:maichi")
ZEROTTS_MODEL = os.getenv("ZEROTTS_MODEL", "zeroweight-ai/ZeroTTS")
ZEROTTS_VOICE = os.getenv("ZEROTTS_VOICE", "maichi")
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "vi-VN-NamMinhNeural")
TTS_RATE = os.getenv("TTS_RATE", "-10%")
TTS_VOLUME = os.getenv("TTS_VOLUME", "+0%")

# Danh mục đầy đủ tất cả các giọng đọc khả dụng trong hệ thống
AVAILABLE_VOICES = [
    # Nhóm 1: ZeroTTS - Local ONNX GPU Studio (Offline, chất lượng cao, không phụ thuộc mạng)
    {
        "id": "zerotts:maichi",
        "name": "Mai Chi (ZeroTTS)",
        "gender": "Nữ",
        "provider": "zerotts",
        "desc": "Giảng viên / MC, truyền cảm (Mặc định)",
        "badge": "Studio GPU",
        "default": True
    },
    {
        "id": "zerotts:quangminh",
        "name": "Quang Minh (ZeroTTS)",
        "gender": "Nam",
        "provider": "zerotts",
        "desc": "Trầm ấm, uy tín, phóng sự & công nghệ",
        "badge": "Studio GPU",
        "default": False
    },
    {
        "id": "zerotts:giahuy",
        "name": "Gia Huy (ZeroTTS)",
        "gender": "Nam",
        "provider": "zerotts",
        "desc": "Ấm áp, tự nhiên, thuyết minh",
        "badge": "Studio GPU",
        "default": False
    },
    {
        "id": "zerotts:baotrang",
        "name": "Bảo Trang (ZeroTTS)",
        "gender": "Nữ",
        "provider": "zerotts",
        "desc": "Truyền cảm, rõ ràng, phong cách sư phạm",
        "badge": "Studio GPU",
        "default": False
    },
    {
        "id": "zerotts:huuduc",
        "name": "Hữu Đức (ZeroTTS)",
        "gender": "Nam",
        "provider": "zerotts",
        "desc": "Chững chạc, trang trọng, hội thảo",
        "badge": "Studio GPU",
        "default": False
    },
    {
        "id": "zerotts:hamy",
        "name": "Hà My (ZeroTTS)",
        "gender": "Nữ",
        "provider": "zerotts",
        "desc": "Trong trẻo, tươi sáng, trẻ trung",
        "badge": "Studio GPU",
        "default": False
    },
    {
        "id": "zerotts:tiendat",
        "name": "Tiến Đạt (ZeroTTS)",
        "gender": "Nam",
        "provider": "zerotts",
        "desc": "Năng động, hiện đại, dứt khoát",
        "badge": "Studio GPU",
        "default": False
    },
    {
        "id": "zerotts:kimoanh",
        "name": "Kim Oanh (ZeroTTS)",
        "gender": "Nữ",
        "provider": "zerotts",
        "desc": "Nhẹ nhàng, thanh lịch, trang nhã",
        "badge": "Studio GPU",
        "default": False
    },
    # Nhóm 2: Microsoft Edge-TTS Neural Cloud (Nhanh, cần kết nối mạng)
    {
        "id": "vi-VN-NamMinhNeural",
        "name": "Nam Minh (Edge-TTS)",
        "gender": "Nam",
        "provider": "edge-tts",
        "desc": "Microsoft Azure Neural, chuẩn miền Bắc",
        "badge": "Cloud Fast",
        "default": False
    },
    {
        "id": "vi-VN-HoaiMyNeural",
        "name": "Hoài My (Edge-TTS)",
        "gender": "Nữ",
        "provider": "edge-tts",
        "desc": "Microsoft Azure Neural, chuẩn miền Bắc",
        "badge": "Cloud Fast",
        "default": False
    },
    # Nhóm 3: Cứu hộ dự phòng
    {
        "id": "gtts:vi",
        "name": "Google Dịch (gTTS)",
        "gender": "Nữ",
        "provider": "gtts",
        "desc": "Google Translate TTS cứu hộ khẩn cấp",
        "badge": "Dự phòng",
        "default": False
    }
]

# 3. Cấu hình Whisper (Phụ đề .srt)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")

# 4. Cấu hình Video Rendering & Draft Mode
DRAFT_MODE = os.getenv("DRAFT_MODE", "false").lower() in ("true", "1", "yes")
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1920"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1080"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "30"))
VIDEO_FPS_FINAL = int(os.getenv("VIDEO_FPS_FINAL", "30"))
KEN_BURNS_ZOOM = float(os.getenv("KEN_BURNS_ZOOM", "1.10"))
SLIDE_PRE_PAUSE = float(os.getenv("SLIDE_PRE_PAUSE", "0.8"))    # Dừng 0.8s đầu slide trước khi nói
SLIDE_POST_PAUSE = float(os.getenv("SLIDE_POST_PAUSE", "1.5"))  # Dừng 1.5s cuối slide sau khi nói xong
SLIDE_PAUSE_DURATION = SLIDE_PRE_PAUSE + SLIDE_POST_PAUSE

# Cấu hình Chuyển cảnh mềm (BioPlus Transitions)
TRANSITION_TYPE = os.getenv("TRANSITION_TYPE", "fade")
TRANSITION_DURATION = float(os.getenv("TRANSITION_DURATION", "0.8"))
TRANSITION_SEQUENCE = os.getenv("TRANSITION_SEQUENCE", "")

# Cấu hình phụ đề (Bật/Tắt tạm thời) & kích thước Pro V2
SUBTITLES_ENABLED = os.getenv("SUBTITLES_ENABLED", "true").lower() in ("true", "1", "yes")
SUBTITLE_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", "42"))
SUBTITLE_OUTLINE = float(os.getenv("SUBTITLE_OUTLINE", "1.4"))
SUBTITLE_SHADOW = float(os.getenv("SUBTITLE_SHADOW", "0.8"))
SUBTITLE_MARGIN_V = int(os.getenv("SUBTITLE_MARGIN_V", "100"))

# 5. Hàm kiểm tra thiết bị phần cứng thực tế từ ONNX Runtime (Không báo khống)
def get_hardware_device_info() -> dict:
    """
    Trả về thông tin thiết bị thực tế dựa trên ONNX Runtime providers:
    - CUDAExecutionProvider -> device: "cuda", device_name: GPU name từ nvidia-smi hoặc "CUDA GPU"
    - DmlExecutionProvider  -> device: "dml", device_name: "DirectML GPU"
    - CPU                   -> device: "cpu", device_name: "CPU"
    """
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if "CUDAExecutionProvider" in providers:
            gpu_name = "CUDA GPU"
            try:
                import subprocess
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if res.returncode == 0 and res.stdout.strip():
                    gpu_name = res.stdout.strip().split("\n")[0].strip()
            except Exception:
                pass
            return {"device": "cuda", "device_name": gpu_name, "is_gpu": True, "providers": providers}
        elif "DmlExecutionProvider" in providers:
            return {"device": "dml", "device_name": "DirectML GPU", "is_gpu": True, "providers": providers}
        else:
            return {"device": "cpu", "device_name": "CPU", "is_gpu": False, "providers": providers}
    except Exception:
        pass
    return {"device": "cpu", "device_name": "CPU", "is_gpu": False, "providers": []}
