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

# Đảm bảo xuất UTF-8 và flush output ngay lập tức trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
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
        "--draft",
        action="store_true",
        help="Chế độ nháp siêu tốc: Edge-TTS + Static Render (không Ken Burns), kiểm tra nhanh kịch bản và phụ đề."
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
    parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Giới hạn phạm vi trang/slide cần xử lý (Ví dụ: 1-2, 1-3, hoặc 2). Mặc định xử lý toàn bộ."
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Tạm thời tắt hardsub phụ đề vào video thành phẩm (vẫn xuất file .ass/.srt)."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.slides)
    if not input_path.exists():
        print(f"[!] Lỗi: Không tìm thấy file PowerPoint/PDF tại: {input_path}")
        print("Vui lòng kiểm tra lại đường dẫn file bài giảng.")
        sys.exit(1)

    ext = input_path.suffix.lower()
    if ext not in [".pptx", ".pdf"]:
        print(f"[!] Lỗi: Định dạng file không được hỗ trợ: {input_path}")
        print("Hệ thống chỉ nhận file PowerPoint (.pptx) và PDF (.pdf).")
        sys.exit(1)

    if args.no_subtitles:
        config.SUBTITLES_ENABLED = False

    if args.draft:
        config.DRAFT_MODE = True
        if args.provider == "zerotts":
            args.provider = "edge-tts"
            if not args.voice:
                args.voice = config.EDGE_TTS_VOICE

    # Xác định thông tin loại đầu vào cho banner
    if ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(str(input_path.resolve()))
            total_items = len(doc)
            doc.close()
            input_banner = f"PDF ({total_items} trang)"
        except Exception:
            input_banner = "PDF"
    else:
        try:
            from pptx import Presentation
            prs = Presentation(str(input_path.resolve()))
            total_items = len(prs.slides)
            input_banner = f"PPTX ({total_items} slide)"
        except Exception:
            input_banner = "PPTX"

    if args.pages:
        input_banner += f" [Chọn phạm vi: {args.pages}]"

    current_fps = config.VIDEO_FPS if args.draft else getattr(config, "VIDEO_FPS_FINAL", 30)
    fps_banner = f"{current_fps}fps (bản cuối mượt)" if (not args.draft and current_fps == 60) else f"{current_fps}fps"
    sub_banner = "BẬT (hardsub .ass V2)" if config.SUBTITLES_ENABLED else "TẮT (--no-subtitles, tạm thời)"

    print("=" * 70)
    print("🚀 AI VIDEO AGENT V2 — STUDIO THUYẾT TRÌNH BÀI GIẢNG")
    print(f"📁 File Input      : {input_path}")
    print(f"📄 Input           : {input_banner}")
    print(f"⚡ Chế độ          : {'NHÁP SIÊU TỐC (--draft: Edge-TTS + Static Render)' if args.draft else 'BẢN CUỐI (ZeroTTS + Ken Burns d=1)'}")
    print(f"🎙️ TTS Provider    : {args.provider} (Voice: {args.voice or (config.EDGE_TTS_VOICE if args.draft else config.TTS_VOICE)})")
    print(f"🤖 Gemini Model    : {config.GEMINI_MODEL}")
    print(f"🎬 Video Specs     : {config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT} @ {fps_banner}")
    print(f"💬 Phụ đề          : {sub_banner}")
    print(f"⚡ Human Review    : {'TẮT (--auto)' if args.auto else 'BẬT (Chờ duyệt kịch bản)'}")
    print(f"🔄 Checkpoint Mode : {'RESET từ đầu (--reset)' if args.reset else 'Tiếp tục từ checkpoint nếu có'}")
    hw = config.get_hardware_device_info()
    print(f"🖥️ Thiết bị        : {hw['device_name']} ({'Tăng tốc phần cứng' if hw['is_gpu'] else 'CPU'})")
    print("=" * 70)

    try:
        from agents.graph import run_pipeline
        run_pipeline(
            pptx_path=input_path,
            auto_mode=args.auto,
            reset_mode=args.reset,
            provider=args.provider,
            voice=args.voice,
            draft_mode=args.draft,
            pages=args.pages,
            subtitles=config.SUBTITLES_ENABLED
        )
    except ImportError:
        print("[*] Pipeline graph đang được cấu hình...")


if __name__ == "__main__":
    main()
