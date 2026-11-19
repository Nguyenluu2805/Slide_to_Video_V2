"""
agents/graph.py - LangGraph State Machine cho AI Video Agent V2
Điều phối toàn bộ luồng xử lý:
[PARSED] -> [SCRIPTED] -> [HUMAN REVIEW] -> [VOICED] -> [RENDERED] -> [ASSEMBLED] -> [QA_FINAL]
Kèm cơ chế Checkpoint phục hồi khi gặp sự cố gián đoạn.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, TypedDict
from langgraph.graph import StateGraph, START, END

import config
from agents.parse import parse_presentation
from agents.script import generate_scripts_with_checkpoint
from agents.voice import get_audio_duration_seconds


class VideoAgentState(TypedDict):
    pptx_path: str
    auto_mode: bool
    reset_mode: bool
    provider: str
    voice: Optional[str]
    slides: List[Dict[str, Any]]
    current_node: str
    error: Optional[str]
    final_video: Optional[str]
    final_srt: Optional[str]


def node_parse(state: VideoAgentState) -> Dict[str, Any]:
    """Node 1: Trích xuất slide thật 1080p và speaker notes."""
    print("\n" + "=" * 60)
    print("📍 [NODE 1: PARSE] Đang trích xuất slide PowerPoint thật...")
    print("=" * 60)
    pptx_p = Path(state["pptx_path"])
    try:
        slides_data = parse_presentation(pptx_p)
        print(f"[+] Trích xuất thành công {len(slides_data)} slide.")
        return {
            "slides": slides_data,
            "current_node": "parsed",
            "error": None
        }
    except Exception as e:
        print(f"[!] Lỗi tại node parse: {e}")
        return {
            "current_node": "error",
            "error": f"Lỗi parse slide: {str(e)}"
        }


def node_script(state: VideoAgentState) -> Dict[str, Any]:
    """Node 2: Sinh kịch bản 1 slide = 1 call + response_schema + QA bằng code + Checkpoint."""
    print("\n" + "=" * 60)
    print("📍 [NODE 2: SCRIPT & QA] Sinh kịch bản sư phạm và kiểm thử...")
    print("=" * 60)
    slides = state.get("slides", [])
    if not slides:
        return {"current_node": "error", "error": "Không có dữ liệu slide để tạo kịch bản."}

    try:
        updated_slides = generate_scripts_with_checkpoint(
            slides_data=slides,
            auto_mode=state.get("auto_mode", False),
            reset_mode=state.get("reset_mode", False)
        )
        return {
            "slides": updated_slides,
            "current_node": "scripted",
            "error": None
        }
    except Exception as e:
        print(f"[!] Lỗi tại node script: {e}")
        return {
            "current_node": "error",
            "error": f"Lỗi sinh kịch bản: {str(e)}"
        }


def node_voice(state: VideoAgentState) -> Dict[str, Any]:
    """Node 3: Lồng tiếng TTS (ZeroTTS chính, Edge-TTS fallback)."""
    print("\n" + "=" * 60)
    print("📍 [NODE 3: VOICE TTS] Tổng hợp giọng đọc bài giảng...")
    print("=" * 60)
    slides = state.get("slides", [])
    provider = state.get("provider", config.TTS_PROVIDER)
    voice = state.get("voice")

    try:
        from agents.voice import synthesize_presentation_audio
        updated_slides = synthesize_presentation_audio(slides, provider=provider, voice_name=voice)
        return {
            "slides": updated_slides,
            "current_node": "voiced",
            "error": None
        }
    except ImportError:
        print("[*] Node Voice TTS đang chờ triển khai ở P2 (sẵn sàng tiếp nối).")
        return {
            "current_node": "voiced",
            "error": None
        }
    except Exception as e:
        print(f"[!] Lỗi tại node voice: {e}")
        return {"current_node": "error", "error": f"Lỗi tổng hợp giọng nói: {str(e)}"}


def node_render(state: VideoAgentState) -> Dict[str, Any]:
    """Node 4: Render video từng slide (FFmpeg 1080p, Ken Burns)."""
    print("\n" + "=" * 60)
    print("📍 [NODE 4: RENDER] Render video từng slide bằng FFmpeg...")
    print("=" * 60)
    try:
        from agents.render import render_presentation_slides
        slides = state.get("slides", [])
        updated_slides = render_presentation_slides(slides)
        return {
            "slides": updated_slides,
            "current_node": "rendered",
            "error": None
        }
    except ImportError:
        print("[*] Node Render đang chờ triển khai ở P2 (sẵn sàng tiếp nối).")
        return {
            "current_node": "rendered",
            "error": None
        }
    except Exception as e:
        print(f"[!] Lỗi tại node render: {e}")
        return {"current_node": "error", "error": f"Lỗi render video: {str(e)}"}


def node_assemble(state: VideoAgentState) -> Dict[str, Any]:
    """Node 5: Trích xuất phụ đề Faster-Whisper, loudnorm -16 LUFS và nối video hoàn chỉnh."""
    print("\n" + "=" * 60)
    print("📍 [NODE 5: ASSEMBLE] Trích xuất phụ đề .srt và xuất final video...")
    print("=" * 60)
    try:
        from agents.assemble import assemble_final_video
        slides = state.get("slides", [])
        final_video, final_srt = assemble_final_video(slides)
        return {
            "current_node": "assembled",
            "final_video": str(final_video),
            "final_srt": str(final_srt),
            "error": None
        }
    except ImportError:
        print("[*] Node Assemble đang chờ triển khai ở P2 (sẵn sàng tiếp nối).")
        return {
            "current_node": "assembled",
            "final_video": str(config.FINAL_VIDEO_FILE),
            "final_srt": str(config.FINAL_SRT_FILE),
            "error": None
        }
    except Exception as e:
        print(f"[!] Lỗi tại node assemble: {e}")
        return {"current_node": "error", "error": f"Lỗi assemble video: {str(e)}"}


def node_qa_final(state: VideoAgentState) -> Dict[str, Any]:
    """Node 6: Kiểm thử chất lượng và tính toàn vẹn của sản phẩm đầu ra."""
    print("\n" + "=" * 60)
    print("📍 [NODE 6: QA FINAL] Kiểm tra sản phẩm đầu ra hoàn thiện...")
    print("=" * 60)

    final_vid = Path(state.get("final_video") or config.FINAL_VIDEO_FILE)
    final_s = Path(state.get("final_srt") or config.FINAL_SRT_FILE)

    errors = []
    if not final_vid.exists() or final_vid.stat().st_size < 100000:
        errors.append(f"File video thành phẩm không tồn tại hoặc kích thước quá nhỏ: {final_vid}")
    if not final_s.exists() or final_s.stat().st_size < 50:
        errors.append(f"File phụ đề .srt không tồn tại hoặc rỗng: {final_s}")

    slides = state.get("slides", [])
    for it in slides:
        sid = it["slide"]["id"]
        sc = it.get("scene", {})
        af = config.PROJECT_ROOT / sc.get("audio_file", "")
        vf = config.PROJECT_ROOT / sc.get("visual", "")
        if not af.exists():
            errors.append(f"Slide {sid} thiếu file audio: {af}")
        if not vf.exists():
            errors.append(f"Slide {sid} thiếu file video: {vf}")

    if errors:
        print("[!] Phát hiện lỗi tại QA Final:")
        for err in errors:
            print(f"    - {err}")
        return {"current_node": "error", "error": "; ".join(errors)}

    # Lấy thông tin video hoàn chỉnh
    vid_size_mb = round(final_vid.stat().st_size / (1024 * 1024), 2)
    vid_dur = get_audio_duration_seconds(final_vid)

    print(f"[+] QA Final ĐẠT CHUẨN:")
    print(f"    🎬 Video thành phẩm : {final_vid.resolve()} ({vid_size_mb} MB, {vid_dur:.1f}s)")
    print(f"    📄 Phụ đề SRT       : {final_s.resolve()}")
    print(f"    📊 Tổng số slide    : {len(slides)} slide")
    print("=" * 60)
    return {"current_node": "completed", "error": None}


def router_after_step(state: VideoAgentState) -> str:
    """Điều hướng có điều kiện: Nếu lỗi thì dừng, nếu tốt thì tiếp tục."""
    if state.get("error"):
        return END
    return "next"


def build_pipeline_graph():
    """Xây dựng đồ thị StateGraph LangGraph."""
    builder = StateGraph(VideoAgentState)

    # Thêm các nodes
    builder.add_node("parse", node_parse)
    builder.add_node("script", node_script)
    builder.add_node("voice", node_voice)
    builder.add_node("render", node_render)
    builder.add_node("assemble", node_assemble)
    builder.add_node("qa_final", node_qa_final)

    # Nối luồng xử lý
    builder.add_edge(START, "parse")
    builder.add_edge("parse", "script")
    builder.add_edge("script", "voice")
    builder.add_edge("voice", "render")
    builder.add_edge("render", "assemble")
    builder.add_edge("assemble", "qa_final")
    builder.add_edge("qa_final", END)

    return builder.compile()


def run_pipeline(
    pptx_path: Path,
    auto_mode: bool = False,
    reset_mode: bool = False,
    provider: str = config.TTS_PROVIDER,
    voice: Optional[str] = None
) -> Dict[str, Any]:
    """Hàm thực thi chính của LangGraph Pipeline."""
    graph = build_pipeline_graph()

    initial_state: VideoAgentState = {
        "pptx_path": str(pptx_path.resolve()),
        "auto_mode": auto_mode,
        "reset_mode": reset_mode,
        "provider": provider,
        "voice": voice,
        "slides": [],
        "current_node": "start",
        "error": None,
        "final_video": None,
        "final_srt": None
    }

    result = graph.invoke(initial_state)
    return result
