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
from agents.parse import parse_presentation, parse_pdf
from agents.script import generate_scripts_with_checkpoint
from agents.voice import get_audio_duration_seconds


class VideoAgentState(TypedDict, total=False):
    pptx_path: str
    auto_mode: bool
    reset_mode: bool
    draft_mode: bool
    provider: str
    voice: Optional[str]
    pages: Optional[str]
    slides: List[Dict[str, Any]]
    current_node: str
    error: Optional[str]
    final_video: Optional[str]
    final_srt: Optional[str]
    timings: Dict[str, float]


def node_parse(state: VideoAgentState) -> Dict[str, Any]:
    """Node 1: Trích xuất slide thật 1080p và speaker notes (PowerPoint .pptx hoặc PDF)."""
    input_p = Path(state["pptx_path"])
    ext = input_p.suffix.lower()
    is_pdf = ext == ".pdf"
    type_label = "PDF" if is_pdf else "PowerPoint"

    print("\n" + "=" * 60)
    print(f"📍 [NODE 1: PARSE] Đang trích xuất tài liệu {type_label} thật...")
    print("=" * 60)
    print("[TIMING] node parse bắt đầu...")
    t0 = time.time()
    pages_range = state.get("pages")

    try:
        if is_pdf:
            slides_data = parse_pdf(input_p, page_range=pages_range)
        elif ext == ".pptx":
            slides_data = parse_presentation(input_p, page_range=pages_range)
        else:
            raise ValueError(f"Chỉ nhận .pptx và .pdf, không hỗ trợ định dạng: {input_p.name}")

        elapsed = time.time() - t0
        print(f"[TIMING] node parse: {elapsed:.2f}s")
        unit_label = "trang" if is_pdf else "slide"
        print(f"[+] Trích xuất thành công {len(slides_data)} {unit_label}.")
        timings = dict(state.get("timings", {}))
        timings["parse"] = round(elapsed, 2)
        return {
            "slides": slides_data,
            "current_node": "parsed",
            "error": None,
            "timings": timings
        }
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[TIMING] node parse (lỗi): {elapsed:.2f}s")
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
    print("[TIMING] node script bắt đầu...")
    t0 = time.time()
    slides = state.get("slides", [])
    if not slides:
        return {"current_node": "error", "error": "Không có dữ liệu slide để tạo kịch bản."}

    try:
        updated_slides = generate_scripts_with_checkpoint(
            slides_data=slides,
            auto_mode=state.get("auto_mode", False),
            reset_mode=state.get("reset_mode", False)
        )
        elapsed = time.time() - t0
        print(f"[TIMING] node script: {elapsed:.2f}s")
        timings = dict(state.get("timings", {}))
        timings["script"] = round(elapsed, 2)
        return {
            "slides": updated_slides,
            "current_node": "scripted",
            "error": None,
            "timings": timings
        }
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[TIMING] node script (lỗi): {elapsed:.2f}s")
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
    print("[TIMING] node voice bắt đầu...")
    t0 = time.time()
    slides = state.get("slides", [])

    is_draft = state.get("draft_mode") or getattr(config, "DRAFT_MODE", False)
    if is_draft:
        # Chế độ nháp mặc định dùng Edge-TTS nếu không chỉ định provider khác
        provider = state.get("provider") if state.get("provider") and state.get("provider") != "zerotts" else "edge-tts"
        voice = state.get("voice") or config.EDGE_TTS_VOICE
    else:
        provider = state.get("provider", config.TTS_PROVIDER)
        voice = state.get("voice")

    try:
        from agents.voice import synthesize_presentation_audio
        updated_slides = synthesize_presentation_audio(slides, provider=provider, voice_name=voice)
        elapsed = time.time() - t0
        print(f"[TIMING] node voice: {elapsed:.2f}s")
        timings = dict(state.get("timings", {}))
        timings["voice"] = round(elapsed, 2)
        return {
            "slides": updated_slides,
            "current_node": "voiced",
            "error": None,
            "timings": timings
        }
    except ImportError:
        print("[*] Node Voice TTS đang chờ triển khai ở P2 (sẵn sàng tiếp nối).")
        return {
            "current_node": "voiced",
            "error": None
        }
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[TIMING] node voice (lỗi): {elapsed:.2f}s")
        print(f"[!] Lỗi tại node voice: {e}")
        return {"current_node": "error", "error": f"Lỗi tổng hợp giọng nói: {str(e)}"}


def node_render(state: VideoAgentState) -> Dict[str, Any]:
    """Node 4: Render video từng slide (FFmpeg 1080p, Ken Burns hoặc Static Draft)."""
    print("\n" + "=" * 60)
    print("📍 [NODE 4: RENDER] Render video từng slide bằng FFmpeg...")
    print("=" * 60)
    print("[TIMING] node render bắt đầu...")
    t0 = time.time()
    try:
        from agents.render import render_presentation_slides
        slides = state.get("slides", [])
        updated_slides = render_presentation_slides(slides)
        elapsed = time.time() - t0
        print(f"[TIMING] node render: {elapsed:.2f}s")
        timings = dict(state.get("timings", {}))
        timings["render"] = round(elapsed, 2)
        return {
            "slides": updated_slides,
            "current_node": "rendered",
            "error": None,
            "timings": timings
        }
    except ImportError:
        print("[*] Node Render đang chờ triển khai ở P2 (sẵn sàng tiếp nối).")
        return {
            "current_node": "rendered",
            "error": None
        }
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[TIMING] node render (lỗi): {elapsed:.2f}s")
        print(f"[!] Lỗi tại node render: {e}")
        return {"current_node": "error", "error": f"Lỗi render video: {str(e)}"}


def node_assemble(state: VideoAgentState) -> Dict[str, Any]:
    """Node 5: Lắp ráp video hoàn chỉnh và hardsub phụ đề .ass."""
    print("\n" + "=" * 60)
    print("📍 [NODE 5: ASSEMBLE] Lắp ráp video hoàn chỉnh và hardsub phụ đề .ass...")
    print("=" * 60)
    print("[TIMING] node assemble bắt đầu...")
    t0 = time.time()
    try:
        from agents.assemble import assemble_final_video
        slides = state.get("slides", [])
        final_video, final_srt = assemble_final_video(slides)
        elapsed = time.time() - t0
        print(f"[TIMING] node assemble: {elapsed:.2f}s")
        timings = dict(state.get("timings", {}))
        timings["assemble"] = round(elapsed, 2)
        return {
            "current_node": "assembled",
            "final_video": str(final_video),
            "final_srt": str(final_srt),
            "error": None,
            "timings": timings
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
        elapsed = time.time() - t0
        print(f"[TIMING] node assemble (lỗi): {elapsed:.2f}s")
        print(f"[!] Lỗi tại node assemble: {e}")
        return {"current_node": "error", "error": f"Lỗi assemble video: {str(e)}"}


def node_qa_final(state: VideoAgentState) -> Dict[str, Any]:
    """Node 6: Kiểm thử chất lượng và tính toàn vẹn của sản phẩm đầu ra."""
    print("\n" + "=" * 60)
    print("📍 [NODE 6: QA FINAL] Kiểm tra sản phẩm đầu ra hoàn thiện...")
    print("=" * 60)
    print("[TIMING] node qa_final bắt đầu...")
    t0 = time.time()

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

    elapsed = time.time() - t0
    print(f"[TIMING] node qa_final: {elapsed:.2f}s")
    timings = dict(state.get("timings", {}))
    timings["qa_final"] = round(elapsed, 2)
    total_pipeline_time = sum(timings.values())

    print(f"\n[+] QA Final ĐẠT CHUẨN:")
    print(f"    🎬 Video thành phẩm : {final_vid.resolve()} ({vid_size_mb} MB, {vid_dur:.1f}s)")
    print(f"    📄 Phụ đề SRT       : {final_s.resolve()}")
    print(f"    📊 Tổng số slide    : {len(slides)} slide")
    print("=" * 60)
    print(f"⏱️ [TIMING SUMMARY] TỔNG THỜI GIAN CÁC NODE: {total_pipeline_time:.2f}s")
    for k, v in timings.items():
        print(f"   - node {k}: {v:.2f}s")
    print("=" * 60)
    return {"current_node": "completed", "error": None, "timings": timings}


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

    # Nối luồng xử lý với điều hướng có điều kiện
    builder.add_edge(START, "parse")
    builder.add_conditional_edges("parse", router_after_step, {"next": "script", END: END})
    builder.add_conditional_edges("script", router_after_step, {"next": "voice", END: END})
    builder.add_conditional_edges("voice", router_after_step, {"next": "render", END: END})
    builder.add_conditional_edges("render", router_after_step, {"next": "assemble", END: END})
    builder.add_conditional_edges("assemble", router_after_step, {"next": "qa_final", END: END})
    builder.add_edge("qa_final", END)

    return builder.compile()


def run_pipeline(
    pptx_path: Path,
    auto_mode: bool = False,
    reset_mode: bool = False,
    provider: str = config.TTS_PROVIDER,
    voice: Optional[str] = None,
    draft_mode: bool = False,
    pages: Optional[str] = None
) -> Dict[str, Any]:
    """Hàm thực thi chính của LangGraph Pipeline."""
    if draft_mode:
        config.DRAFT_MODE = True
        print("[*] Chế độ --draft được kích hoạt: Tăng tốc tối đa (Edge-TTS + Static Render).")

    if reset_mode:
        print("[*] Chế độ --reset: Dọn dẹp toàn bộ dữ liệu checkpoint, audio và video cũ...")
        config.STATE_FILE.unlink(missing_ok=True)
        (config.OUTPUT_DIR / "script.json").unlink(missing_ok=True)
        if config.AUDIO_DIR.exists():
            for f in config.AUDIO_DIR.glob("slide_*.wav"):
                f.unlink(missing_ok=True)
        if config.VIDEO_DIR.exists():
            for f in config.VIDEO_DIR.glob("*.mp4"):
                f.unlink(missing_ok=True)
            for f in config.VIDEO_DIR.glob("*.ass"):
                f.unlink(missing_ok=True)
            for f in config.VIDEO_DIR.glob("*.srt"):
                f.unlink(missing_ok=True)

    pipeline_start_t = time.time()
    graph = build_pipeline_graph()

    initial_state: VideoAgentState = {
        "pptx_path": str(pptx_path.resolve()),
        "auto_mode": auto_mode,
        "reset_mode": reset_mode,
        "draft_mode": draft_mode or getattr(config, "DRAFT_MODE", False),
        "provider": provider,
        "voice": voice,
        "pages": pages,
        "slides": [],
        "current_node": "start",
        "error": None,
        "final_video": None,
        "final_srt": None,
        "timings": {}
    }

    result = graph.invoke(initial_state)
    total_elapsed = time.time() - pipeline_start_t
    print(f"\n✨ [HOÀN TẤT] Tổng thời gian thực thi toàn bộ pipeline: {total_elapsed:.2f}s ({total_elapsed/60:.2f} phút)")
    return result
