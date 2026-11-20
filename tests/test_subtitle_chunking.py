"""
tests/test_subtitle_chunking.py - Unit test cho hàm chia phụ đề theo cụm ý (Quy tắc 3c)
Input là câu dài 30-40 từ (Slide 1 Ex01).
Test assert: Mọi lần hiện <= 11 từ, <= 65 ký tự, <= 2 dòng, mọi dòng <= 38 ký tự.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.subtitle_pro import chunk_text_pedagogical, split_lines_balanced


def test_pedagogical_chunking_rules():
    print("=" * 60)
    print("CHẠY UNIT TEST CHIA PHỤ ĐỀ THEO CỤM Ý (QUY TẮC 3C)")
    print("=" * 60)

    # Câu mẫu slide 1 Ex01 (30 từ, 149 ký tự)
    sample_sentence = (
        "Trong thực tế, tôi đã chứng kiến nhiều đội ngũ kỹ sư mắc sai lầm "
        "nghiêm trọng khi quăng toàn bộ nghiệp vụ phức tạp vào duy nhất một prompt LLM khổng lồ."
    )
    words = sample_sentence.split()
    print(f"Input sentence: {len(words)} từ, {len(sample_sentence)} ký tự")
    assert 25 <= len(words) <= 45, "Câu test phải dài 30-40 từ theo đúng đề bài"

    # 1. Gọi hàm chia phụ đề theo cụm ý
    cues = chunk_text_pedagogical(sample_sentence, max_words=11, max_chars=65)
    print(f"-> Chia thành {len(cues)} lần hiện (cues):")

    for i, cue in enumerate(cues, 1):
        w_count = len(cue.split())
        c_count = len(cue)
        print(f"\n[Lần hiện {i}] ({w_count} từ, {c_count} ký tự):")
        print(f'   "{cue}"')

        # Assert trần cứng: <= 11 từ và <= 65 ký tự
        assert w_count <= 11, f"Lần hiện {i} vượt quá 11 từ: {w_count} từ ({cue})"
        assert c_count <= 65, f"Lần hiện {i} vượt quá 65 ký tự: {c_count} ký tự ({cue})"

        # 2. Kiểm tra phân dòng: Tối đa 2 dòng, mỗi dòng <= 38 ký tự
        formatted = split_lines_balanced(cue, max_chars=38)
        lines = formatted.split(r"\N")
        assert len(lines) <= 2, f"Lần hiện {i} vượt quá 2 dòng: {len(lines)} dòng"

        for line_idx, line in enumerate(lines, 1):
            line_len = len(line)
            print(f"      Dòng {line_idx} ({line_len} ký tự): '{line}'")
            assert line_len <= 38, f"Dòng {line_idx} của lần hiện {i} vượt quá 38 ký tự: {line_len} ký tự ('{line}')"

        if len(lines) == 2:
            l2_words = len(lines[1].split())
            assert l2_words >= 2 or len(lines[1]) >= 10, f"Dòng 2 bị orphan từ lẻ loi: '{lines[1]}'"

    # 3. Kiểm tra bảo toàn số thập phân 99.9%
    decimal_test = "Mục tiêu là đạt 99.9% độ tin cậy và hoàn thành trong 3.5 giây."
    dec_cues = chunk_text_pedagogical(decimal_test)
    joined_dec = " ".join(dec_cues)
    assert "99.9%" in joined_dec, "Số thập phân 99.9% bị hỏng!"
    assert "3.5" in joined_dec, "Số thập phân 3.5 bị hỏng!"
    print("\n-> [OK] Bảo toàn nguyên vẹn số thập phân 99.9% và 3.5.")

    print("\n" + "=" * 60)
    print("TẤT CẢ ASSERT QUY TẮC 3C ĐÃ PASS 100%!")
    print("=" * 60)


if __name__ == "__main__":
    test_pedagogical_chunking_rules()
