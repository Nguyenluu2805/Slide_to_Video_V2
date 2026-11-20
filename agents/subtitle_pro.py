"""
agents/subtitle_pro.py — Phụ đề kiểu video thuyết minh chuyên nghiệp V2 (chuẩn Coursera / Khan Academy / 3Blue1Brown)
Cho dự án Slide_to_Video_V2:
  1. Nguồn chữ = script.json (kịch bản đã duyệt), KHÔNG dùng Whisper nghe lại.
  2. Tối đa 2 dòng, 38 ký tự/dòng, 1-5 giây/câu, căn giữa tuyệt đối (Alignment 2).
  3. Font Be Vietnam Pro, size 30, PrimaryColour trắng ngà #F5F5F4, BackColour trong suốt.
  4. Từ khóa (thuật ngữ tiếng Anh, số liệu): CHỈ bọc bằng {\\b1} (đậm), KHÔNG đổi màu.
  5. Phụ đề nằm cách đáy 110px (MarginV 110), lề trái/phải MarginL/R 160.
  6. Tự động cân bằng 2 dòng phụ đề, loại bỏ hoàn toàn từ lẻ loi (orphan) ở dòng 2.
  7. Tương thích hoàn hảo với chuyển cảnh xfade 0.5s giữa các slide.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

# Thuật ngữ / mẫu từ khóa nhận diện bọc đậm {\\b1} (không đổi màu trong V2)
KEYWORD_PATTERNS = [
    r"State Machine", r"LangGraph", r"Hybrid Workflow", r"Deterministic Code",
    r"Pure LLM", r"Pure Agentic", r"Agentic(?:\s+Decision)?\s+Nodes?", r"Ex0\d",
    r"Human-In-The-Loop", r"Infinite Tool Loops?", r"Semantic Reasoning",
    r"Single Source of Truth", r"Deterministic Backbone", r"Non-deterministic",
    r"QA Checker Guardrail", r"Best Practices", r"Production",
    # Thương hiệu & Chuyên ngành Sức khỏe Hydro
    r"Kim Long Phát", r"(?:Nước|Khí)?\s*giàu Hydro", r"Hydro",
    r"Tô Văn Trực", r"Thạc sĩ(?:\s+Kỹ thuật Điện)?", r"Cao đẳng Kỹ nghệ II",
    r"Chăm Sóc Sức Khỏe(?: Chủ Động)?",
    # Số liệu, phần trăm, đơn vị
    r"\d+\.?\d*\s?%", r"\d+\s?(?:giây|đô|dòng|lần|năm|gia đình|tháng)",
]
_KEYWORD_RE = re.compile("(" + "|".join(KEYWORD_PATTERNS) + ")", re.IGNORECASE)

# Header & Style chuẩn V2 theo đặc tả Coursera / Khan Academy
ASS_HEADER_V2 = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ProV2,Be Vietnam Pro,30,&H00F5F5F4,&H00F5F5F4,&H00000000,&H00000000,-1,0,0,0,100,100,0.5,0,1,1.0,0.6,2,160,160,110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# Các liên từ / giới từ tiếng Việt hỗ trợ ngắt câu tự nhiên theo ngữ nghĩa
CONJUNCTIONS = {
    'và', 'hoặc', 'nhưng', 'mà', 'thì', 'là', 'của', 'để', 'với', 'trong',
    'khi', 'nếu', 'như', 'do', 'tại', 'bởi', 'giúp', 'cho', 'về', 'từ'
}


def _fmt_ass_time(sec: float) -> str:
    """Định dạng thời gian theo chuẩn ASS: H:MM:SS.cs"""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _highlight_v2(text: str) -> str:
    """
    Từ khóa: CHỈ bọc bằng {\\b1} (đậm), KHÔNG đổi màu (chuẩn V2 tối giản).
    Ví dụ trong .ass: {\\b1}State Machine{\\b0} — còn lại để \\b0 (thường).
    Tuyệt đối không dùng {\\1c&H...&} tô màu vàng / xanh.
    """
    parts = _KEYWORD_RE.split(text)
    out = []
    for p in parts:
        if not p:
            continue
        if _KEYWORD_RE.fullmatch(p):
            out.append(r"{\b1}" + p + r"{\b0}")
        else:
            out.append(p)
    return r"{\b0}" + "".join(out)


def split_lines_balanced(text: str, max_chars: int = 38) -> str:
    """
    Chia 1 câu phụ đề thành tối đa 2 dòng cân đối (chuẩn V2):
    - Tối đa 38 ký tự/dòng.
    - Căn bằng độ dài 2 dòng, không để dòng 2 quá ngắn hoặc quá dài.
    - Loại bỏ hoàn toàn hiện tượng từ lẻ loi (orphan) ở dòng 2.
    - Ưu tiên ngắt tại dấu phẩy / dấu chấm phẩy hoặc ngay trước liên từ.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text

    words = text.split()
    if len(words) <= 1:
        return text

    best_split = -1
    best_score = float('inf')
    target_mid = len(text) / 2.0

    for i in range(len(words) - 1):
        line1 = " ".join(words[:i + 1])
        line2 = " ".join(words[i + 1:])

        words_l2 = len(words) - 1 - i
        orphan_penalty = 0
        if words_l2 == 1:
            orphan_penalty = 600
        elif words_l2 == 2 and len(line2) < 10:
            orphan_penalty = 250

        overflow1 = max(0, len(line1) - max_chars) * 25
        overflow2 = max(0, len(line2) - max_chars) * 25

        balance_penalty = abs(len(line1) - target_mid) * 1.5

        punct_bonus = 0
        if words[i].endswith((',', ';', ':', '—', '-')):
            punct_bonus = 35

        conj_bonus = 0
        next_word_clean = re.sub(r'[^a-zA-Zà-ỹÀ-Ỹ]', '', words[i + 1]).lower()
        if next_word_clean in CONJUNCTIONS:
            conj_bonus = 25

        score = balance_penalty + overflow1 + overflow2 + orphan_penalty - punct_bonus - conj_bonus
        if score < best_score:
            best_score = score
            best_split = i

    if best_split != -1:
        line1 = " ".join(words[:best_split + 1])
        line2 = " ".join(words[best_split + 1:])
        return line1 + r"\N" + line2

    return text


def _split_into_clauses_v2(script: str, max_words: int = 11, min_words: int = 4) -> List[str]:
    """
    Chia kịch bản thành các câu hoặc mệnh đề ngắn sư phạm:
    - Bảo vệ số thập phân (99.9%, 3.5, 30 giây, ...).
    - Tách theo ranh giới câu [.!?] -> tách theo dấu phẩy / chấm phẩy -> tách từ nếu câu quá dài.
    - Đảm bảo mỗi khối <= max_words từ (tương đương 1-5 giây giọng đọc, <= 65 ký tự).
    """
    safe = re.sub(r"(\d+)\.(\d+)", r"\1DECIMALDOT\2", script)
    safe = re.sub(r"(\d+),(\d+)", r"\1DECIMALCOMMA\2", safe)
    safe = re.sub(r"\s+", " ", safe).strip()

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", safe) if s.strip()]

    raw_units = []
    for sent in sentences:
        words = sent.split()
        if len(words) <= max_words:
            raw_units.append(sent)
        else:
            clauses = [c.strip() for c in re.split(r"(?<=[,;:])\s+", sent) if c.strip()]
            curr = []
            for c in clauses:
                c_words = c.split()
                if len(curr) + len(c_words) <= max_words:
                    curr.extend(c_words)
                else:
                    if curr:
                        raw_units.append(" ".join(curr))
                        curr = []
                    if len(c_words) > max_words:
                        for i in range(0, len(c_words), max_words):
                            raw_units.append(" ".join(c_words[i:i + max_words]))
                    else:
                        curr = list(c_words)
            if curr:
                raw_units.append(" ".join(curr))

    # Gộp các khối quá ngắn (< min_words từ) vào khối liền kề
    merged = []
    for u in raw_units:
        u_words = u.split()
        if merged and len(u_words) < min_words:
            prev = merged[-1]
            if len(prev.split()) + len(u_words) <= (max_words + 3):
                merged[-1] = f"{prev} {u}"
                continue
        merged.append(u)

    final_chunks = []
    for m in merged:
        res = m.replace("DECIMALDOT", ".").replace("DECIMALCOMMA", ",").strip()
        if res:
            final_chunks.append(res)

    return final_chunks if final_chunks else [script]


def build_ass_from_script(
    slides_data: List[Dict[str, Any]],
    output_ass: Path,
    pre_pause: float = 0.8,
    post_pause: float = 1.5,
    use_crossfade: bool = True,
    crossfade_dur: float = 0.5,
) -> Path:
    """
    Sinh file .ass từ script.json + duration audio thật của từng slide theo chuẩn V2:
    - Font Be Vietnam Pro, size 30, chữ trắng ngà #F5F5F4, viền mỏng, BackColour trong suốt.
    - Căn giữa tuyệt đối (Alignment 2), cách đáy 110px (MarginV 110), lề trái/phải 160.
    - Tối đa 2 dòng, 38 ký tự/dòng, không có từ lẻ loi ở dòng 2.
    - Từ khóa: CHỈ bọc {\\b1}...{\\b0} (đậm), KHÔNG đổi màu vàng/xanh.
    - Bù trừ offset chuẩn xác khi áp dụng chuyển cảnh crossfade 0.5s giữa các slide.
    """
    from agents.voice import get_audio_duration_seconds
    import config

    events = []
    running_offset = 0.0

    for idx, item in enumerate(slides_data):
        sc = item.get("scene", {})
        script = (sc.get("script") or "").strip()
        audio_file = config.PROJECT_ROOT / sc.get("audio_file", "")

        # Ưu tiên đo thời lượng từ audio thật nếu file tồn tại
        if audio_file.exists():
            audio_dur = get_audio_duration_seconds(audio_file)
        else:
            audio_dur = float(sc.get("duration_sec") or 60.0)

        slide_total_dur = round(audio_dur + pre_pause + post_pause, 2)

        # Tính toán thời điểm bắt đầu slide trong video hoàn thiện
        if idx == 0:
            slide_start_offset = 0.0
            running_offset = slide_total_dur
        else:
            if use_crossfade:
                slide_start_offset = running_offset - crossfade_dur
                running_offset = slide_start_offset + slide_total_dur
            else:
                slide_start_offset = running_offset
                running_offset += slide_total_dur

        if not script or audio_dur <= 0:
            continue

        clauses = _split_into_clauses_v2(script, max_words=11, min_words=4)

        # Tính trọng số cho từng câu (số từ + bonus ngắt nhịp)
        weights = []
        for c in clauses:
            w_count = len(c.split())
            bonus = 1.0 if c.endswith(('.', '!', '?')) else (0.5 if c.endswith((',', ';', ':')) else 0.0)
            weights.append(max(1.0, w_count + bonus))

        total_weight = sum(weights) or 1.0
        durations = [(w / total_weight) * audio_dur for w in weights]

        speech_start_time = slide_start_offset + pre_pause
        curr_t = speech_start_time

        for c, dur in zip(clauses, durations):
            dur = max(1.0, min(5.0, dur))
            formatted_text = split_lines_balanced(c, max_chars=38)
            highlighted = _highlight_v2(formatted_text)
            start_str = _fmt_ass_time(curr_t)
            end_str = _fmt_ass_time(curr_t + dur)
            events.append(
                f"Dialogue: 0,{start_str},{end_str},ProV2,,0,0,0,,{highlighted}"
            )
            curr_t += dur

    output_ass.parent.mkdir(parents=True, exist_ok=True)
    output_ass.write_text(ASS_HEADER_V2 + "\n".join(events) + "\n", encoding="utf-8")
    print(f"[+] Đã xuất file phụ đề chuyên nghiệp V2 ({len(events)} khối, max 38 ký tự/dòng): {output_ass.name}")
    return output_ass
