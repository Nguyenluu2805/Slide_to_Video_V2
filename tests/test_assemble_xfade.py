import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.assemble import assemble_final_video
import config

def test_assemble_xfade_pipeline():
    print("=" * 60)
    print("KIỂM TRA PIPELINE ASSEMBLE V2 VỚI XFADE & MASTERING")
    print("=" * 60)

    test_dir = Path("output/test_assemble_v2")
    test_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = test_dir / "audio"
    video_dir = test_dir / "video"
    audio_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    # 1. Tạo 2 video slide mẫu (mỗi slide 3.0s, 1920x1080 @ 30fps)
    v1 = video_dir / "slide_001.mp4"
    v2 = video_dir / "slide_002.mp4"
    a1 = audio_dir / "slide_001.wav"
    a2 = audio_dir / "slide_002.wav"

    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x1E293B:s=1920x1080:d=3", "-f", "lavfi", "-i", "sine=f=440:d=3", "-c:v", "libx264", "-c:a", "aac", str(v1.resolve())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0F172A:s=1920x1080:d=3", "-f", "lavfi", "-i", "sine=f=550:d=3", "-c:v", "libx264", "-c:a", "aac", str(v2.resolve())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=440:d=1.5", str(a1.resolve())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=550:d=1.5", str(a2.resolve())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    slides_data = [
        {
            "slide": {"id": 1, "title": "Slide 1 - State Machine"},
            "scene": {
                "script": "Kiến trúc State Machine là chìa khóa kết hợp LLM và code.",
                "audio_file": str(a1.resolve().relative_to(config.PROJECT_ROOT.resolve())),
                "visual": str(v1.resolve().relative_to(config.PROJECT_ROOT.resolve())),
                "duration_sec": 3.0
            }
        },
        {
            "slide": {"id": 2, "title": "Slide 2 - 99.9% Reliability"},
            "scene": {
                "script": "Hệ thống đạt độ tin cậy 99.9% trong môi trường production.",
                "audio_file": str(a2.resolve().relative_to(config.PROJECT_ROOT.resolve())),
                "visual": str(v2.resolve().relative_to(config.PROJECT_ROOT.resolve())),
                "duration_sec": 3.0
            }
        }
    ]

    out_mp4 = video_dir / "test_lecture.mp4"
    out_srt = video_dir / "test_lecture.srt"

    # Lưu lại config cũ
    old_video_dir = config.VIDEO_DIR
    old_draft = getattr(config, "DRAFT_MODE", False)
    config.VIDEO_DIR = video_dir
    config.DRAFT_MODE = False  # Bật xfade chuyển cảnh mềm

    try:
        final_v, final_s = assemble_final_video(slides_data, out_mp4, out_srt)
        assert final_v.exists(), "Không tạo được video thành phẩm!"
        assert final_s.exists(), "Không tạo được file SRT!"
        assert (video_dir / "final_lecture.ass").exists(), "Không tạo được file ASS!"
        size = final_v.stat().st_size
        print(f"-> [OK] Assemble thành công video {final_v.name} ({size} bytes).")

        from agents.voice import get_audio_duration_seconds
        dur = get_audio_duration_seconds(final_v)
        # 3.0s + 3.0s - 0.5s xfade = 5.5s
        print(f"-> [OK] Thời lượng video hoàn thiện: {dur:.2f}s (chuẩn 5.5s sau xfade 0.5s).")
        assert 5.0 <= dur <= 6.0, f"Thời lượng video sai lệch: {dur}"
    finally:
        config.VIDEO_DIR = old_video_dir
        config.DRAFT_MODE = old_draft
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

    print("\n" + "=" * 60)
    print("ASSEMBLE V2 VỚI XFADE 0.5S ĐÃ HOẠT ĐỘNG HOÀN HẢO!")
    print("=" * 60)

if __name__ == "__main__":
    test_assemble_xfade_pipeline()
