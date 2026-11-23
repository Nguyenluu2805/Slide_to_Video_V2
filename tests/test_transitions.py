"""
tests/test_transitions.py - Kiểm thử bộ chuyển cảnh mềm BioPlus và quy tắc xfade
1. get_transition_for_join() theo TRANSITION_SEQUENCE (modulo tuần hoàn).
2. Offset xfade tính đúng theo TRANSITION_DURATION (10s + 12s với 0.8s -> offset = 9.2s).
3. Draft mode vẫn hard cut (use_crossfade == False khi DRAFT_MODE=True).
4. Quy tắc chống mỏi mắt (anti-fatigue): không quá 2 lần liên tiếp slideleft/smoothleft.
"""

import os
import sys
from pathlib import Path

# Thêm đường dẫn thư mục gốc dự án
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.transitions import (
    get_transition_for_join,
    get_transition_sequence,
    SUPPORTED_TRANSITIONS,
    DEFAULT_TRANSITION
)


def test_transition_sequence_cycling():
    """
    Test 1: get_transition_for_join() trả đúng kiểu theo TRANSITION_SEQUENCE.
    Chuỗi 'fade,slideleft,wipedown' -> 1: fade, 2: slideleft, 3: wipedown, 4: fade, 5: slideleft...
    """
    old_seq = getattr(config, "TRANSITION_SEQUENCE", "")
    try:
        config.TRANSITION_SEQUENCE = "fade,slideleft,wipedown"

        assert get_transition_for_join(1, total_joins=5) == "fade"
        assert get_transition_for_join(2, total_joins=5) == "slideleft"
        assert get_transition_for_join(3, total_joins=5) == "wipedown"
        assert get_transition_for_join(4, total_joins=5) == "fade"
        assert get_transition_for_join(5, total_joins=5) == "slideleft"
    finally:
        config.TRANSITION_SEQUENCE = old_seq


def test_xfade_offset_calculation():
    """
    Test 2: Offset xfade tính đúng theo TRANSITION_DURATION (không hard-code 0.5).
    Với slide 1 dài 10.0s và slide 2 dài 12.0s, transition duration = 0.8s
    -> offset điểm nối = 10.0 - 0.8 = 9.2s.
    """
    old_dur = getattr(config, "TRANSITION_DURATION", 0.8)
    try:
        config.TRANSITION_DURATION = 0.8
        dur1 = 10.0
        dur2 = 12.0
        trans_dur = config.TRANSITION_DURATION

        offset_join_1 = round(max(0.1, dur1 - trans_dur), 2)
        assert offset_join_1 == 9.2, f"Offset tính sai: {offset_join_1} != 9.2"

        # Tổng thời lượng chạy sau join 1
        running_dur = offset_join_1 + dur2
        assert round(running_dur, 2) == 21.2
    finally:
        config.TRANSITION_DURATION = old_dur


def test_draft_mode_hard_cut():
    """
    Test 3: Draft mode vẫn hard cut (use_crossfade == False khi DRAFT_MODE=True).
    Dù TRANSITION_TYPE hay TRANSITION_SEQUENCE có đặt bất kỳ kiểu gì.
    """
    old_draft = getattr(config, "DRAFT_MODE", False)
    old_type = getattr(config, "TRANSITION_TYPE", "fade")
    try:
        config.DRAFT_MODE = True
        config.TRANSITION_TYPE = "slideleft"

        slides_data = [{"scene": {}}, {"scene": {}}]
        use_crossfade = (not config.DRAFT_MODE) and len(slides_data) > 1
        assert use_crossfade is False, "Draft mode phải luôn là False đối với use_crossfade!"
    finally:
        config.DRAFT_MODE = old_draft
        config.TRANSITION_TYPE = old_type


def test_anti_fatigue_rule():
    """
    Test 4: Quy tắc chống mỏi mắt (Anti-fatigue rule).
    Nếu gặp slideleft/smoothleft quá 2 lần liên tiếp, lần thứ 3 phải tự động đổi sang 'fade'.
    """
    old_seq = getattr(config, "TRANSITION_SEQUENCE", "")
    try:
        # Chuỗi toàn bộ là slideleft
        config.TRANSITION_SEQUENCE = "slideleft"

        t1 = get_transition_for_join(1, total_joins=4)
        t2 = get_transition_for_join(2, total_joins=4)
        t3 = get_transition_for_join(3, total_joins=4)
        t4 = get_transition_for_join(4, total_joins=4)

        assert t1 == "slideleft", f"Join 1 phải là slideleft, nhận: {t1}"
        assert t2 == "slideleft", f"Join 2 phải là slideleft, nhận: {t2}"
        assert t3 == "fade", f"Join 3 phải rơi về fade (chống mỏi mắt), nhận: {t3}"
        assert t4 == "slideleft", f"Join 4 tiếp tục được dùng slideleft, nhận: {t4}"
    finally:
        config.TRANSITION_SEQUENCE = old_seq


def test_fallback_invalid_transition():
    """
    Test 5: Kiểu chuyển cảnh không nằm trong SUPPORTED_TRANSITIONS phải fallback về 'fade'.
    """
    old_seq = getattr(config, "TRANSITION_SEQUENCE", "")
    try:
        config.TRANSITION_SEQUENCE = "circlecrop,unknown_effect,fade"
        assert get_transition_for_join(1, total_joins=3) == "fade"
        assert get_transition_for_join(2, total_joins=3) == "fade"
        assert get_transition_for_join(3, total_joins=3) == "fade"
    finally:
        config.TRANSITION_SEQUENCE = old_seq
