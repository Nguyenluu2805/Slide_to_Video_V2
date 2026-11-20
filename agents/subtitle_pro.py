"""
agents/subtitle_pro.py — Phụ đề kiểu video thuyết minh chuyên nghiệp V2 (chuẩn Coursera / Khan Academy / 3Blue1Brown)
Cho dự án Slide_to_Video_V2:
  1. Nguồn chữ = script.json (kịch bản đã duyệt), KHÔNG dùng Whisper nghe lại.
  2. BỎ HỘP NỀN: Trong suốt hoàn toàn, không dùng hộp nền, không gradient đáy.
  3. Màu chữ: Trắng ngà #F5F5F4, font Be Vietnam Pro size 42 (tăng từ 30 để rõ nét), viền Outline 1.4, bóng Shadow 0.8.
  4. Từ khóa: CHỈ bọc bằng {\\b1} (đậm), KHÔNG đổi màu vàng/xanh.
  5. Căn giữa tuyệt đối (Alignment 2), cách đáy 100px (MarginV 100), lề trái/phải MarginL/R 160.
  6. Chia phụ đề theo cụm ý: mỗi lần hiện <= 11 từ, <= 65 ký tự, thời lượng 1.2-3.5s, <= 20 ký tự/giây.
  7. Tối đa 2 dòng, mỗi dòng <= 38 ký tự, không để dòng 2 bị lẻ loi (orphan) — cân đều 2 dòng.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

import config

# Thuật ngữ / mẫu từ khóa nhận diện bọc đậm {\\b1}
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


def get_ass_header_v2(
    font_size: Optional[int] = None,
    outline: Optional[float] = None,
    shadow: Optional[float] = None,
    margin_v: Optional[int] = None,
) -> str:
    """Tạo Header & Style ASS chuẩn V2 không hộp nền với kích thước font tối ưu."""
    fs = font_size if font_size is not None else getattr(config, "SUBTITLE_FONT_SIZE", 42)
    ol = outline if outline is not None else getattr(config, "SUBTITLE_OUTLINE", 1.4)
    sh = shadow if shadow is not None else getattr(config, "SUBTITLE_SHADOW", 0.8)
    mv = margin_v if margin_v is not None else getattr(config, "SUBTITLE_MARGIN_V", 100)
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ProV2,Be Vietnam Pro,{fs},&H00F5F5F4,&H00F5F5F4,&H00000000,&H00000000,-1,0,0,0,100,100,0.5,0,1,{ol},{sh},2,160,160,{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


# Header & Style chuẩn V2 mặc định
ASS_HEADER_V2 = get_ass_header_v2()

# Các liên từ / giới từ tiếng Việt hỗ trợ ngắt nhịp tự nhiên theo ngữ nghĩa
CONJUNCTIONS = {
    'và', 'hoặc', 'nhưng', 'mà', 'thì', 'là', 'của', 'để', 'với', 'trong',
    'khi', 'nếu', 'như', 'do', 'tại', 'bởi', 'giúp', 'cho', 'về', 'từ', 'vào', 'ra', 'lên', 'xuống'
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
    Tuyệt đối không dùng mã màu vàng / xanh.
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


def chunk_text_pedagogical(script: str, max_words: int = 11, max_chars: int = 65) -> List[str]:
    """
    Chia kịch bản theo cụm ý (Quy tắc 3c):
    - 1 lần hiện <= 11 từ VÀ <= 65 ký tự.
    - Không ngắt cứng theo câu. Gom từ thành cụm, ngắt khi đủ 11 từ hoặc 65 ký tự.
    - Ưu tiên ngắt sau dấu phẩy / dấu câu hoặc trước liên từ.
    - Câu dài không có dấu phẩy vẫn ngắt theo giới hạn từ/ký tự.
    - Bảo toàn số thập phân 99.9%, 3.5, 30 giây.
    """
    if not script or not script.strip():
        return []

    safe = re.sub(r'(\d+)\.(\d+)', r'\1DECIMALDOT\2', script)
    safe = re.sub(r'(\d+),(\d+)', r'\1DECIMALCOMMA\2', safe)
    safe = re.sub(r'\s+', ' ', safe).strip()
    words = safe.split()
    if not words:
        return []

    chunks = []
    i = 0
    n = len(words)

    while i < n:
        # Xác định số từ tối đa có thể lấy mà không vượt quá max_words hoặc max_chars
        max_take = 0
        cur_len = 0
        for j in range(i, min(n, i + max_words)):
            w = words[j]
            new_len = cur_len + len(w) + (1 if cur_len > 0 else 0)
            if new_len > max_chars:
                break
            cur_len = new_len
            max_take += 1

        if max_take == 0:
            max_take = 1

        # Nếu lấy hết phần còn lại mà vừa vặn thì lấy luôn
        if i + max_take >= n:
            chunks.append(' '.join(words[i:n]))
            break

        # Tìm điểm ngắt tối ưu trong khoảng [min_take, max_take]
        min_take = max(4, max_take - 6)
        best_k = max_take
        best_score = -float('inf')

        for k in range(max_take, min_take - 1, -1):
            w_curr = words[i + k - 1]
            w_next = words[i + k] if (i + k < n) else ''
            w_next_clean = re.sub(r'[^a-zA-Zà-ỹÀ-Ỹ]', '', w_next).lower()

            # Điểm cơ sở: ưu tiên kích thước cụm hài hòa 7-9 từ
            score = 10 - abs(k - 8)

            # Thưởng lớn nếu ngắt tại dấu câu
            if w_curr.endswith(('.', '!', '?')):
                score += 50
            elif w_curr.endswith((',', ';', ':', '—', '-')):
                score += 40

            # Thưởng lớn nếu từ tiếp theo là liên từ / giới từ
            if w_next_clean in CONJUNCTIONS:
                score += 35

            if score > best_score:
                best_score = score
                best_k = k

        chunk_words = words[i:i + best_k]
        chunks.append(' '.join(chunk_words))
        i += best_k

    # Gộp cụm cuối nếu quá ngắn (< 3 từ) vào cụm liền trước nếu vừa
    if len(chunks) > 1:
        last_words = chunks[-1].split()
        if len(last_words) < 3:
            prev_words = chunks[-2].split()
            comb = f"{chunks[-2]} {chunks[-1]}"
            if len(prev_words) + len(last_words) <= max_words and len(comb) <= max_chars:
                chunks[-2] = comb
                chunks.pop()

    return [c.replace('DECIMALDOT', '.').replace('DECIMALCOMMA', ',').strip() for c in chunks]


def split_lines_balanced(text: str, max_chars: int = 38) -> str:
    """
    Chia 1 câu phụ đề thành tối đa 2 dòng cân đối (chuẩn V2):
    - Tối đa 2 dòng, mỗi dòng <= 38 ký tự.
    - Cân bằng độ dài 2 dòng, không để dòng 2 quá ngắn hoặc quá dài.
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
            orphan_penalty = 2000
        elif words_l2 == 2 and len(line2) < 10:
            orphan_penalty = 800

        # Phạt cực nặng nếu bất kỳ dòng nào vượt quá 38 ký tự
        overflow1 = max(0, len(line1) - max_chars) * 10000
        overflow2 = max(0, len(line2) - max_chars) * 10000

        balance_penalty = abs(len(line1) - target_mid) * 2.0

        punct_bonus = 0
        if words[i].endswith((',', ';', ':', '—', '-')):
            punct_bonus = 40

        conj_bonus = 0
        next_word_clean = re.sub(r'[^a-zA-Zà-ỹÀ-Ỹ]', '', words[i + 1]).lower()
        if next_word_clean in CONJUNCTIONS:
            conj_bonus = 30

        score = balance_penalty + overflow1 + overflow2 + orphan_penalty - punct_bonus - conj_bonus
        if score < best_score:
            best_score = score
            best_split = i

    if best_split != -1:
        line1 = " ".join(words[:best_split + 1])
        line2 = " ".join(words[best_split + 1:])
        return line1 + r"\N" + line2

    return text


def build_ass_from_script(
    slides_data: List[Dict[str, Any]],
    output_ass: Path,
    pre_pause: float = 0.8,
    post_pause: float = 1.5,
    use_crossfade: bool = True,
    crossfade_dur: float = 0.5,
    font_size: Optional[int] = None,
) -> Path:
    """
    Sinh file .ass từ script.json + duration audio thật của từng slide theo chuẩn V2:
    - BỎ HỘP NỀN: Trong suốt hoàn toàn, không dùng hộp nền, không gradient đáy.
    - Font Be Vietnam Pro, size lớn 42 rõ nét, chữ trắng ngà #F5F5F4, viền Outline 1.4, bóng Shadow 0.8.
    - Căn giữa tuyệt đối (Alignment 2), cách đáy 100px (MarginV 100), lề trái/phải 160.
    - Mỗi lần hiện: <= 11 từ VÀ <= 65 ký tự, thời lượng 1.2-3.5s, <= 20 ký tự/giây.
    - Tối đa 2 dòng, mỗi dòng <= 38 ký tự, không có từ lẻ loi ở dòng 2.
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

        cues = chunk_text_pedagogical(script, max_words=11, max_chars=65)
        if not cues:
            continue

        # Tính trọng số cho từng cụm theo số từ và dấu câu
        weights = []
        for c in cues:
            w_count = len(c.split())
            bonus = 1.0 if c.endswith(('.', '!', '?')) else (0.5 if c.endswith((',', ';', ':')) else 0.0)
            weights.append(max(1.0, w_count + bonus))

        total_weight = sum(weights) or 1.0
        durations = [(w / total_weight) * audio_dur for w in weights]

        speech_start_time = slide_start_offset + pre_pause
        curr_t = speech_start_time

        for c, raw_dur in zip(cues, durations):
            # Quy tắc cứng 3c: 1.2s - 3.5s và <= 20 ký tự/giây
            dur = max(1.2, min(3.5, raw_dur))
            if dur > 0 and (len(c) / dur) > 20.0:
                dur = min(3.5, len(c) / 18.0)

            formatted_text = split_lines_balanced(c, max_chars=38)
            highlighted = _highlight_v2(formatted_text)
            start_str = _fmt_ass_time(curr_t)
            end_str = _fmt_ass_time(curr_t + dur)
            events.append(
                f"Dialogue: 0,{start_str},{end_str},ProV2,,0,0,0,,{highlighted}"
            )
            curr_t += dur

    header = get_ass_header_v2(font_size=font_size)
    output_ass.parent.mkdir(parents=True, exist_ok=True)
    output_ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    print(f"[+] Đã xuất file phụ đề chuyên nghiệp V2 ({len(events)} khối, max 11 từ / 65 ký tự, max 38 ký tự/dòng): {output_ass.name}")
    return output_ass
