"""
AI Video Agent V2 - Main CLI Interface
Biến slide PowerPoint (.pptx) và speaker notes thành video thuyết trình 1080p@30fps chuyên nghiệp.

Cách sử dụng:
    python main.py --slides test_data/Ex01_Hybrid_Workflow.pptx
    python main.py --slides test_data/Ex01_Hybrid_Workflow.pptx --auto
    python main.py --slides test_data/Ex01_Hybrid_Workflow.pptx --reset
"""

import sys
import argparse
from pathlib import Path

# Đảm bảo xuất UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import config

def parse_args():
    parser = argparse.ArgumentParser(
        description="AI Video Agent V2 — Chuyển đổi PowerPoint + Speaker Notes thành Video thuyết trình chuyên nghiệp 1080p."
    )
    parser.add_argument(
        "--slides", "-s",
        type=str,
        default=str(config.TEST_DATA_DIR / "Ex01_Hybrid_Workflow.pptx"),
        help="Đường dẫn tới file bài giảng .pptx (Mặc định: test_data/Ex01_Hybrid_Workflow.pptx)"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Bỏ qua bước Human Review kịch bản, chạy tự động hoàn toàn từ đầu đến cuối."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Xóa checkpoint state.json cũ và chạy lại toàn bộ quy trình từ đầu."
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=config.TTS_PROVIDER,
        choices=["zerotts", "edge-tts", "gemini-tts"],
        help=f"Engine tổng hợp giọng nói (Mặc định: {config.TTS_PROVIDER})"
    )
    parser.add_argument(
        "--voice",
        type=str,
        default=None,
        help="Tên giọng đọc (Ví dụ: zerotts:maichi hoặc vi-VN-NamMinhNeural)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    pptx_path = Path(args.slides)
    if not pptx_path.exists():
        print(f"[!] Lỗi: Không tìm thấy file PowerPoint tại: {pptx_path}")
        print("Vui lòng kiểm tra lại đường dẫn file bài giảng.")
        sys.exit(1)

    print("=" * 70)
    print("🚀 AI VIDEO AGENT V2 — STUDIO THUYẾT TRÌNH BÀI GIẢNG")
    print(f"📁 Slide Input     : {pptx_path}")
    print(f"🎙️ TTS Provider    : {args.provider}")
    print(f"🤖 Gemini Model    : {config.GEMINI_MODEL}")
    print(f"🎬 Video Specs     : {config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT} @ {config.VIDEO_FPS}fps")
    print(f"⚡ Human Review    : {'TẮT (--auto)' if args.auto else 'BẬT (Chờ duyệt kịch bản)'}")
    print(f"🔄 Checkpoint Mode : {'RESET từ đầu (--reset)' if args.reset else 'Tiếp tục từ checkpoint nếu có'}")
    hw = config.get_hardware_device_info()
    print(f"🖥️ Thiết bị        : {hw['device_name']} ({'Tăng tốc phần cứng' if hw['is_gpu'] else 'CPU'})")
    print("=" * 70)

    try:
        from agents.graph import run_pipeline
        run_pipeline(
            pptx_path=pptx_path,
            auto_mode=args.auto,
            reset_mode=args.reset,
            provider=args.provider,
            voice=args.voice
        )
    except ImportError:
        print("[*] Pipeline graph đang được cấu hình...")


if __name__ == "__main__":
    main()
