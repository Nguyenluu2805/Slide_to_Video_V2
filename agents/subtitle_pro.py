"""
agents/subtitle_pro.py — Phụ đề kiểu video thuyết minh chuyên nghiệp (chuẩn Coursera / Khan Academy)
Cho dự án Slide_to_Video_V2:
  1. Nguồn chữ = script.json (kịch bản đã duyệt), KHÔNG dùng Whisper nghe lại.
  2. Tối đa 2 dòng, 42 ký tự/dòng, 1-5 giây/câu, <= 20 ký tự/giây.
  3. Font Be Vietnam Pro Bold 30, chữ trắng, hộp nền đen mờ 55%, viền mỏng.
  4. Từ khóa (thuật ngữ tiếng Anh, số liệu) tô vàng #FFD166.
  5. Phụ đề nằm cách đáy 90px, không che nội dung slide, không sát mép.
"""

import re
from pathlib import Path
from typing import List, Dict, Any

# Thuật ngữ / mẫu cần tô vàng — dùng non-capturing group (?:...) để tránh re.split lặp từ
KEYWORD_PATTERNS = [
    r"State Machine", r"LangGraph", r"Hybrid Workflow", r"Deterministic Code",
    r"Pure LLM", r"Pure Agentic", r"Agentic(?:\s+Decision)?\s+Nodes?", r"Ex0\d",
    r"Human-In-The-Loop", r"Infinite Tool Loops?", r"Semantic Reasoning",
    r"Single Source of Truth", r"Deterministic Backbone", r"Non-deterministic",
    r"QA Checker Guardrail", r"Best Practices", r"Production",
    r"\d+\.?\d*\s?%", r"\d+\s?(?:giây|đô|dòng|lần)",
]
_KEYWORD_RE = re.compile("(" + "|".join(KEYWORD_PATTERNS) + ")", re.IGNORECASE)

# Màu trong .ass là BGR: &HBBGGRR& — FFD166 (vàng) = &H66D1FF&
YELLOW = r"{\1c&H66D1FF&\b1}"
WHITE = r"{\1c&HFFFFFF&\b1}"

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pro,Be Vietnam Pro,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H8C000000,-1,0,0,0,100,100,0,0,4,1.2,0.5,2,120,120,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _fmt_ass_time(sec: float) -> str:
    """Định dạng thời gian theo chuẩn ASS: H:MM:SS.cs"""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _highlight(text: str) -> str:
    """Tô vàng từ khóa thuật ngữ và số liệu, phần còn lại giữ chữ trắng."""
    parts = _KEYWORD_RE.split(text)
    out = []
    for p in parts:
        if not p:
            continue
        if _KEYWORD_RE.fullmatch(p):
            out.append(YELLOW + p + WHITE)
        else:
            out.append(p)
    return "".join(out)


def _split_lines(text: str, max_chars: int = 42) -> str:
    """Chia 1 câu thành tối đa 2 dòng, ngắt ở khoảng trắng hoặc dấu phẩy gần giữa câu."""
    if len(text) <= max_chars:
        return text

    mid = len(text) // 2
    best_split = -1
    min_dist = float('inf')

    for i in range(10, len(text) - 10):
        if text[i] in (' ', ','):
            split_pos = i + 1 if text[i] == ',' else i
            dist = abs(split_pos - mid)
            if dist < min_dist:
                min_dist = dist
                best_split = split_pos

    if best_split != -1:
        line1 = text[:best_split].strip()
        line2 = text[best_split:].strip()
        return line1 + r"\N" + line2

    return text


def _split_into_clauses(script: str, max_words: int = 12) -> List[str]:
    """
    Chia kịch bản thành các câu hoặc mệnh đề ngắn sư phạm:
    - Bảo vệ số thập phân (99.9%, 3.5, 30 giây).
    - Tách theo ranh giới câu [.!?] -> tách theo dấu phẩy / chấm phẩy -> tách từ nếu câu quá dài.
    - Đảm bảo mỗi khối <= max_words từ (tương đương 3-4s giọng đọc, <= 70 ký tự).
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
            # Tách theo mệnh đề dấu phẩy / chấm phẩy / hai chấm
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

    # Gộp các khối quá ngắn (< 4 từ) vào khối liền kề
    merged = []
    for u in raw_units:
        u_words = u.split()
        if merged and len(u_words) < 4:
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
) -> Path:
    """
    Sinh file .ass từ script.json + duration audio thật của từng slide.
    Thời gian mỗi câu chia theo tỷ lệ số từ và độ dài audio thực tế.
    Tự động bù trừ khoảng nghỉ pre_pause (0.8s) và post_pause (1.5s).
    """
    from agents.voice import get_audio_duration_seconds
    import config

    events = []
    offset = 0.0

    for item in slides_data:
        sc = item.get("scene", {})
        script = (sc.get("script") or "").strip()
        audio_file = config.PROJECT_ROOT / sc.get("audio_file", "")

        # Ưu tiên đo thời lượng từ audio thật nếu file tồn tại
        if audio_file.exists():
            audio_dur = get_audio_duration_seconds(audio_file)
        else:
            audio_dur = float(sc.get("duration_sec") or 60.0)

        if not script or audio_dur <= 0:
            offset += audio_dur + pre_pause + post_pause
            continue

        clauses = _split_into_clauses(script, max_words=12)

        # Tính trọng số cho từng câu (số từ + bonus dấu câu)
        weights = []
        for c in clauses:
            w_count = len(c.split())
            bonus = 1.0 if c.endswith(('.', '!', '?')) else (0.5 if c.endswith((',', ';', ':')) else 0.0)
            weights.append(max(1.0, w_count + bonus))

        total_weight = sum(weights) or 1.0
        durations = [(w / total_weight) * audio_dur for w in weights]

        t = offset + pre_pause
        for c, dur in zip(clauses, durations):
            dur = max(1.0, min(5.0, dur))
            formatted_text = _split_lines(c, max_chars=42)
            highlighted = _highlight(formatted_text)
            start_str = _fmt_ass_time(t)
            end_str = _fmt_ass_time(t + dur)
            events.append(
                f"Dialogue: 0,{start_str},{end_str},Pro,,0,0,0,,{highlighted}"
            )
            t += dur

        slide_total_dur = round(audio_dur + pre_pause + post_pause, 2)
        offset += slide_total_dur

    output_ass.parent.mkdir(parents=True, exist_ok=True)
    output_ass.write_text(ASS_HEADER + "\n".join(events) + "\n", encoding="utf-8")
    print(f"[+] Đã xuất file phụ đề chuyên nghiệp ({len(events)} khối): {output_ass.name}")
    return output_ass
