"""
agents/qa.py - Module kiểm thử chất lượng kịch bản (QA Script) và video (QA Final)
Hoàn toàn bằng thuật toán code xác định, không nhờ LLM tự chấm.
"""

import re
import difflib
from typing import Dict, Any, List, Tuple


def count_vietnamese_words(text: str) -> int:
    """Đếm số từ tiếng Việt dựa trên khoảng trắng và dấu câu."""
    if not text:
        return 0
    words = text.strip().split()
    return len(words)


def extract_numbers_from_text(text: str) -> List[str]:
    """Trích xuất danh sách các số, phần trăm, số liệu trong văn bản."""
    # Bắt các số dạng: 10, 100, 3.5, 90%, 15/16, v.v.
    raw_nums = re.findall(r'\b\d+(?:[.,/]\d+)?%?\b', text)
    cleaned = []
    for n in raw_nums:
        c = n.strip(".,")
        if c and c not in cleaned:
            cleaned.append(c)
    return cleaned


def extract_opening_sentence(script: str) -> str:
    """Lấy câu mở đầu của kịch bản để so khớp trùng lặp."""
    splits = re.split(r'[.!?\n]+', script.strip())
    for s in splits:
        if len(s.strip().split()) >= 3:
            return s.strip().lower()
    return ""


def qa_script_for_slide(
    slide_entry: Dict[str, Any],
    script_data: Dict[str, Any],
    previous_openings: List[str] = None
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Kiểm tra chất lượng kịch bản của một slide theo đúng các tiêu chí V2:
    1. Đủ slide, đúng slide_id.
    2. word_count trong khoảng 150 - 220 từ.
    3. bullets_covered >= 80% bullets của slide.
    4. Không chứa các câu template sáo rỗng hoặc lặp giữa các slide.
    5. Không bịa đặt số liệu ngoài slide + speaker notes.
    6. Không đọc vẹt nguyên văn bullet dài > 15 từ.
    
    Trả về: (passed: bool, errors: List[str], grounding: Dict[str, Any])
    """
    slide = slide_entry.get("slide", {})
    slide_id = slide.get("id", 1)
    title = slide.get("title", "")
    bullets = slide.get("bullets", [])
    notes = slide.get("notes", "")

    script = script_data.get("script", "").strip()
    reported_slide_id = script_data.get("slide_id", slide_id)

    errors = []
    invented_claims = []

    # 1. Kiểm tra slide_id
    if reported_slide_id != slide_id:
        errors.append(f"Sai slide_id: mong đợi {slide_id}, nhận được {reported_slide_id}.")

    # 2. Đếm số từ thực tế bằng code
    actual_word_count = count_vietnamese_words(script)
    if actual_word_count < 150:
        errors.append(f"Kịch bản quá ngắn: {actual_word_count} từ (yêu cầu 150 - 220 từ). Cần diễn giải chi tiết hơn.")
    elif actual_word_count > 220:
        errors.append(f"Kịch bản quá dài: {actual_word_count} từ (yêu cầu 150 - 220 từ). Cần cô đọng lại lời giảng.")

    # 3. Kiểm tra bullets_covered
    bullets_covered = script_data.get("bullets_covered", [])
    bullets_missed = script_data.get("bullets_missed", [])

    total_bullets = len(bullets)
    if total_bullets > 0:
        # Tự động rà soát lại mức độ xuất hiện từ khóa của từng bullet trong script
        covered_count = 0
        detected_covered = []
        detected_missed = []

        for b in bullets:
            b_clean = re.sub(r'^[•\-\*\d\.\s]+', '', b).strip()
            # Lấy các từ khóa quan trọng (từ dài >= 3 ký tự)
            keywords = [w.lower() for w in b_clean.split() if len(w) >= 3]
            if not keywords:
                covered_count += 1
                detected_covered.append(b)
                continue

            matches = sum(1 for kw in keywords if kw in script.lower())
            match_ratio = matches / len(keywords)
            if match_ratio >= 0.4:
                covered_count += 1
                detected_covered.append(b)
            else:
                detected_missed.append(b)

        coverage_ratio = covered_count / total_bullets
        if coverage_ratio < 0.8:
            errors.append(
                f"Độ bao phủ nội dung slide chưa đạt 80% ({covered_count}/{total_bullets} bullets, đạt {coverage_ratio*100:.1f}%). "
                f"Các ý bị sót: {detected_missed[:2]}"
            )
        bullets_covered = detected_covered
        bullets_missed = detected_missed
    else:
        bullets_covered = []
        bullets_missed = []

    # 4. Kiểm tra câu template lặp và sáo rỗng
    banned_templates = [
        "điểm đáng chú ý ở đây là",
        "bullet 1 là",
        "bullet 2 là",
        "gạch đầu dòng thứ",
        "như các bạn thấy trên slide",
        "như chúng ta đã biết"
    ]
    script_lower = script.lower()
    for bt in banned_templates:
        if bt in script_lower:
            errors.append(f"Phát hiện mẫu câu template cấm: '{bt}'. Hãy diễn đạt tự nhiên như giảng viên.")

    # Kiểm tra lặp câu mở đầu với các slide trước đó
    current_opening = extract_opening_sentence(script)
    if previous_openings and current_opening:
        for prev_op in previous_openings:
            sim = difflib.SequenceMatcher(None, current_opening, prev_op).ratio()
            if sim > 0.75:
                errors.append(f"Câu mở đầu bị lặp ý với slide trước: '{current_opening[:40]}...'. Hãy đổi cách nối câu.")
                break

    # 5. Kiểm tra bịa đặt số liệu (Invented claims)
    context_text = f"{title} {' '.join(bullets)} {notes} Slide {slide_id}"
    context_nums = extract_numbers_from_text(context_text)
    script_nums = extract_numbers_from_text(script)

    for num in script_nums:
        # Bỏ qua số thứ tự slide hiện tại
        if num == str(slide_id):
            continue
        if num not in context_nums:
            invented_claims.append(num)

    if len(invented_claims) > 2:
        errors.append(
            f"Phát hiện số liệu không có trong slide hoặc speaker notes: {invented_claims}. "
            f"Cấm bịa đặt số liệu ngoài tài liệu gốc."
        )

    # 6. Kiểm tra đọc vẹt nguyên văn bullet dài > 15 từ
    for b in bullets:
        b_clean = re.sub(r'^[•\-\*\d\.\s]+', '', b).strip()
        b_words = b_clean.split()
        if len(b_words) > 15:
            if b_clean.lower() in script_lower:
                errors.append(f"Đọc vẹt nguyên văn bullet dài: '{b_clean[:40]}...'. Hãy diễn giải lại bằng văn nói.")
                break

    grounding = {
        "uses_notes": bool(notes.strip()),
        "bullets_covered": bullets_covered,
        "bullets_missed": bullets_missed,
        "invented_claims": invented_claims,
        "word_count": actual_word_count,
        "passed": len(errors) == 0,
        "errors": errors
    }

    is_passed = len(errors) == 0
    return is_passed, errors, grounding
