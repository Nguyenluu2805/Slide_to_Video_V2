"""
agents/transitions.py - Thư viện và logic điều phối chuyển cảnh xfade (chuẩn BioPlus)
Hỗ trợ: fade, slideleft, slideup, wipedown, smoothleft.
Chứa quy tắc chống mỏi mắt (anti-fatigue): không dùng slideleft/smoothleft quá 2 lần liên tiếp.
"""

import os
import sys
from typing import List, Optional
import config

# Bảng các kiểu chuyển cảnh FFmpeg xfade được hỗ trợ
SUPPORTED_TRANSITIONS = ("fade", "slideleft", "slideup", "wipedown", "smoothleft")
DEFAULT_TRANSITION = "fade"


def get_transition_sequence() -> List[str]:
    """
    Đọc chuỗi cấu hình chuyển cảnh từ TRANSITION_SEQUENCE hoặc fallback về TRANSITION_TYPE.
    Ví dụ: 'fade,slideleft,wipedown' -> ['fade', 'slideleft', 'wipedown']
    """
    seq_raw = getattr(config, "TRANSITION_SEQUENCE", "") or os.getenv("TRANSITION_SEQUENCE", "")
    if seq_raw and seq_raw.strip():
        items = [t.strip().lower() for t in seq_raw.split(",") if t.strip()]
        if items:
            return items

    fallback = (getattr(config, "TRANSITION_TYPE", "") or os.getenv("TRANSITION_TYPE", "") or DEFAULT_TRANSITION).strip().lower()
    return [fallback]


def get_transition_for_join(i: int, total_joins: int = 1) -> str:
    """
    Nhận chỉ số điểm nối (1-based: join 1, 2, 3...) và tổng số điểm nối,
    trả về tên kiểu chuyển cảnh chuẩn FFmpeg xfade.

    Quy tắc:
    1. Đọc từ chuỗi TRANSITION_SEQUENCE theo vòng lặp tuần hoàn (modulo).
    2. Chống mỏi mắt: Không để quá 2 lần liên tiếp dùng slideleft hoặc smoothleft.
       Nếu gặp lần thứ 3 thì tự động đổi sang 'fade'.
    3. Kiểm tra tính hợp lệ: Nếu kiểu không nằm trong SUPPORTED_TRANSITIONS, rơi về 'fade'.
    """
    seq = get_transition_sequence()
    if not seq:
        seq = [DEFAULT_TRANSITION]

    history: List[str] = []
    slide_variants = ("slideleft", "smoothleft")

    # Xây dựng danh sách chuyển cảnh từ join 1 đến join i theo quy tắc chống mỏi mắt
    for k in range(1, max(1, i) + 1):
        idx = (k - 1) % len(seq)
        candidate = seq[idx]

        # Kiểm tra tính hợp lệ
        if candidate not in SUPPORTED_TRANSITIONS:
            candidate = DEFAULT_TRANSITION

        # Áp dụng quy tắc chống mỏi mắt: Không quá 2 lần liên tiếp slideleft/smoothleft
        if candidate in slide_variants:
            if len(history) >= 2 and history[-1] in slide_variants and history[-2] in slide_variants:
                candidate = "fade"

        history.append(candidate)

    return history[i - 1]
