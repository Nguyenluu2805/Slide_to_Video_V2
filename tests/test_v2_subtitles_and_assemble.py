"""
tests/test_v2_subtitles_and_assemble.py - Kiểm thử nghiệm thu Phụ đề V2 & Chuyển cảnh mềm
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.subtitle_pro import build_ass_from_script, ASS_HEADER_V2, split_lines_balanced, _highlight_v2

def test_v2_subtitle_logic():
    print("=" * 60)
    print("KIỂM TRA LOGIC PHỤ ĐỀ V2")
    print("=" * 60)

    # 1. Kiểm tra ASS Header & Style ProV2
    assert "Style: ProV2,Be Vietnam Pro,30,&H00F5F5F4,&H00F5F5F4,&H00000000,&H00000000,-1,0,0,0,100,100,0.5,0,1,1.0,0.6,2,160,160,110,1" in ASS_HEADER_V2, "Sai Style ProV2"
    print("-> [OK] Style ProV2 chuẩn xác 100% (Font 30, Trắng ngà #F5F5F4, MarginV 110, MarginL/R 160, Alignment 2).")

    # 2. Kiểm tra từ khóa: CHỈ bọc {\b1}, KHÔNG có mã màu {\1c...}
    sample_text = "Hệ thống dùng State Machine kết hợp với 99.9% độ tin cậy và Ex01 LangGraph."
    highlighted = _highlight_v2(sample_text)
    print(f"Highlighted text: {highlighted}")
    assert r"{\b1}State Machine{\b0}" in highlighted, "Thiếu bọc đậm State Machine"
    assert r"{\b1}99.9%{\b0}" in highlighted, "Thiếu bọc đậm 99.9%"
    assert r"{\b1}Ex01{\b0}" in highlighted, "Thiếu bọc đậm Ex01"
    assert r"{\b1}LangGraph{\b0}" in highlighted, "Thiếu bọc đậm LangGraph"
    assert r"\1c" not in highlighted, "Phát hiện mã màu tô vàng/xanh bị cấm trong V2!"
    print("-> [OK] Từ khóa CHỈ bọc {\\b1} (đậm), KHÔNG đổi màu, đúng nguyên tắc tối giản V2.")

    # 3. Kiểm tra ngắt dòng cân đối <= 38 ký tự & không orphan ở dòng 2
    long_text = "Chào mừng các bạn đến với chương đầu tiên về kiến trúc Hybrid Workflow"
    balanced = split_lines_balanced(long_text, max_chars=38)
    lines = balanced.split(r"\N")
    print(f"Line 1 ({len(lines[0])} chars): {lines[0]}")
    print(f"Line 2 ({len(lines[1])} chars): {lines[1]}")
    assert len(lines) == 2, "Phải chia thành 2 dòng"
    assert len(lines[0]) <= 38, f"Dòng 1 quá dài: {len(lines[0])}"
    assert len(lines[1]) <= 38, f"Dòng 2 quá dài: {len(lines[1])}"
    assert len(lines[1].split()) >= 2, "Dòng 2 bị orphan từ đơn độc!"
    print("-> [OK] Ngắt dòng cân đối <= 38 ký tự/dòng, không bị orphan từ ở dòng 2.")

    # 4. Kiểm tra sinh file ASS từ script.json mẫu nếu có
    script_file = Path("output/script.json")
    if script_file.exists():
        data = json.loads(script_file.read_text(encoding="utf-8"))
        slides_data = []
        for i, s in enumerate(data):
            slides_data.append({
                "slide": {"id": s.get("slide_index", i+1), "title": s.get("title", "")},
                "scene": {
                    "script": s.get("script", ""),
                    "audio_file": f"output/audio/slide_{i+1:03d}.wav",
                    "visual": f"output/video/slide_{i+1:03d}.mp4",
                    "duration_sec": 60.0
                }
            })
        test_ass = Path("output/video/test_v2.ass")
        build_ass_from_script(slides_data, test_ass, use_crossfade=True, crossfade_dur=0.5)
        assert test_ass.exists() and test_ass.stat().st_size > 500, "File ASS V2 rỗng hoặc lỗi!"
        ass_txt = test_ass.read_text(encoding="utf-8")
        assert "Style: ProV2" in ass_txt, "Thiếu Style ProV2 trong file ASS"
        assert r"\1c" not in ass_txt, "Có mã màu trong file ASS V2!"
        print(f"-> [OK] Sinh file ASS V2 thành công ({test_ass.stat().st_size} bytes).")
        test_ass.unlink(missing_ok=True)

    print("\n" + "=" * 60)
    print("TẤT CẢ KIỂM THỬ PHỤ ĐỀ V2 ĐÃ PASS 100%!")
    print("=" * 60)

if __name__ == "__main__":
    test_v2_subtitle_logic()
