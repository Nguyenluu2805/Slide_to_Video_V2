"""
agents/script.py - Module tạo kịch bản thuyết trình sư phạm chuẩn V2 bằng Google Gemini
Quy tắc: 1 slide = 1 call Gemini, response_schema ép JSON, 150 - 220 từ/slide,
Speaker notes là nguồn chính (70%), Bullets là nguồn phụ (30%).
"""

import os
import sys
import json
import time
import re
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import config
from agents.qa import qa_script_for_slide, count_vietnamese_words

# Schema ép buộc chuẩn V2
SCRIPT_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "slide_id": {"type": "INTEGER"},
        "script": {"type": "STRING"},
        "bullets_covered": {"type": "ARRAY", "items": {"type": "STRING"}},
        "bullets_missed": {"type": "ARRAY", "items": {"type": "STRING"}}
    },
    "required": ["slide_id", "script", "bullets_covered"]
}

# Danh sách model ưu tiên tự động fallback nếu model chính bị quá tải hoặc deprecate
FALLBACK_MODELS = [
    getattr(config, "GEMINI_MODEL", "gemini-3-flash-preview"),
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash"
]


def call_gemini_api_with_schema(prompt: str, model_name: str = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Gọi Gemini API kèm responseSchema và xử lý retry tự động khi gặp lỗi 429/503.
    Hỗ trợ fallback model nếu model chỉ định gặp sự cố.
    """
    api_key = config.GEMINI_API_KEY
    if not api_key:
        raise ValueError("Chưa cấu hình GEMINI_API_KEY trong file .env!")

    models_to_try = [model_name] if model_name else []
    for fm in FALLBACK_MODELS:
        if fm not in models_to_try:
            models_to_try.append(fm)

    last_error = None
    for current_model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": SCRIPT_RESPONSE_SCHEMA,
                "temperature": 0.35,
                "topP": 0.95
            }
        }

        # Thử tối đa 3 lần cho mỗi model với exponential backoff khi gặp 429 / 503
        for attempt in range(1, 4):
            try:
                resp = requests.post(url, json=payload, timeout=40)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    candidates = resp_json.get("candidates", [])
                    if not candidates:
                        raise ValueError("Gemini không trả về candidate nào.")

                    raw_text = candidates[0]["content"]["parts"][0]["text"]
                    parsed_data = json.loads(raw_text)
                    usage = resp_json.get("usageMetadata", {})
                    token_stats = {
                        "prompt_tokens": usage.get("promptTokenCount", 0),
                        "candidate_tokens": usage.get("candidatesTokenCount", 0),
                        "total_tokens": usage.get("totalTokenCount", 0),
                        "model_used": current_model
                    }
                    return parsed_data, token_stats

                elif resp.status_code in [429, 503]:
                    # Lỗi quá tải rate limit hoặc server bận
                    wait_time = 5 * attempt
                    print(f"[*] Gemini API ({current_model}) báo mã {resp.status_code}. Tạm dừng {wait_time}s thử lại...")
                    time.sleep(wait_time)
                elif resp.status_code == 404:
                    print(f"[!] Model {current_model} không khả dụng (404), chuyển sang model tiếp theo...")
                    break
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    break
            except requests.exceptions.RequestException as e:
                print(f"[*] Lỗi kết nối mạng ({e}), thử lại sau 5s...")
                time.sleep(5)
                last_error = str(e)

    raise RuntimeError(f"Gọi Gemini API thất bại sau khi thử các model: {last_error}")


def build_slide_prompt(
    slide_entry: Dict[str, Any],
    previous_summary: str = "",
    next_title: str = "",
    retry_feedback: str = ""
) -> str:
    """Tạo prompt chuẩn mực cho 1 slide theo đúng quy chuẩn V2."""
    slide = slide_entry.get("slide", {})
    slide_id = slide.get("id", 1)
    title = slide.get("title", "")
    bullets = slide.get("bullets", [])
    notes = slide.get("notes", "")

    has_notes = bool(notes.strip())

    prompt = f"""Bạn là một giảng viên đại học và chuyên gia thuyết trình xuất sắc.
Nhiệm vụ: Viết LỜI THUYẾT MINH DIỄN THUYẾT TỰ NHIÊN cho DUY NHẤT Slide số {slide_id}.

=== DỮ LIỆU ĐẦU VÀO CỦA SLIDE {slide_id} ===
- Tiêu đề slide: {title}
- Gạch đầu dòng (Bullets): {json.dumps(bullets, ensure_ascii=False)}
- Ghi chú diễn giả (Speaker Notes): {notes if has_notes else "(Không có notes, chỉ được diễn giải từ các bullet)"}

=== THÔNG TIN LIÊN KẾT BÀI GIẢNG ===
- Tóm tắt ý slide trước: {previous_summary or "Đây là slide mở đầu bài giảng."}
- Tiêu đề slide tiếp theo: {next_title or "Đây là slide kết thúc bài giảng."}

=== QUY TẮC BẮT BUỘC (TUÂN THỦ 100%) ===
1. NGUỒN NỘI DUNG (RẤT QUAN TRỌNG):
   - Speaker Notes là nguồn chính (chiếm 70% nội dung lời nói).
   - Bullets + Tiêu đề là nguồn phụ (chiếm 30% nội dung để đảm bảo không bỏ sót ý chính).
   - CẤM BỊA ĐẶT số liệu, tên người, công nghệ hoặc kết luận không có trong slide và speaker notes.
   - Nếu không có speaker notes: chỉ diễn giải mở rộng từ các bullets, tuyệt đối không thêm ý ngoài lề.

2. ĐỘ DÀI LỜI THUYẾT TRÌNH (BẮT BUỘC):
   - Tổng độ dài kịch bản PHẢI NẰM TRONG KHOẢNG TỪ 150 ĐẾN 220 TỪ TIẾNG VIỆT (Tương đương 60 - 90 giây khi đọc).
   - Không được viết dưới 150 từ. Không được viết vượt quá 220 từ.

3. CẤU TRÚC LỜI NÓI (3 PHẦN LIỀN MẠCH):
   - Mở (1 câu): Nối tiếp tự nhiên từ ý của slide trước (hoặc lời chào mở đầu nếu là slide 1).
   - Thân (3 - 5 câu): Diễn giải sâu sắc speaker notes kết hợp lần lượt từng bullet point bằng văn nói sư phạm.
   - Chốt (1 câu): Đúc kết ngắn gọn và chuyển tiếp sang slide kế tiếp.

4. VĂN PHONG SƯ PHẠM:
   - Nói tự nhiên, truyền cảm như đang giảng dạy trực tiếp trước người học.
   - KHÔNG đọc vẹt bullet. TUYỆT ĐỐI KHÔNG viết: "Bullet 1 là...", "Gạch đầu dòng thứ...", "Điểm đáng chú ý ở đây là...".
   - Giữ nguyên thuật ngữ tiếng Anh gốc: Hybrid Workflow, Version History, Files On-Demand, State Machine, Deterministic, Agentic. Không dịch gượng ép.
   - Giữ nguyên các con số, tỷ lệ phần trăm từ tài liệu gốc, không làm tròn.
"""

    if retry_feedback:
        prompt += f"""
=== LƯU Ý SỬA LỖI TỪ LẦN THỬ TRƯỚC (BẮT BUỘC KHẮC PHỤC) ===
{retry_feedback}
Hãy điều chỉnh lại kịch bản để vượt qua hoàn toàn các lỗi trên!
"""
    return prompt


def write_script_for_single_slide(
    slide_entry: Dict[str, Any],
    previous_summary: str = "",
    next_title: str = "",
    previous_openings: List[str] = None
) -> Dict[str, Any]:
    """
    Sinh kịch bản cho 1 slide, chạy QA kiểm thử bằng code, retry tối đa 3 lần nếu chưa đạt.
    """
    slide = slide_entry.get("slide", {})
    slide_id = slide.get("id", 1)
    title = slide.get("title", f"Slide {slide_id}")

    print(f"\n[*] Đang sinh kịch bản cho Slide {slide_id}: {title[:35]}...")
    retry_feedback = ""
    best_result = None
    best_grounding = None
    accumulated_tokens = {"prompt_tokens": 0, "candidate_tokens": 0, "total_tokens": 0}

    for attempt in range(1, 4):
        prompt = build_slide_prompt(
            slide_entry=slide_entry,
            previous_summary=previous_summary,
            next_title=next_title,
            retry_feedback=retry_feedback
        )

        try:
            raw_script_data, token_stats = call_gemini_api_with_schema(prompt)
            # Cộng dồn token tiêu thụ
            for k in ["prompt_tokens", "candidate_tokens", "total_tokens"]:
                accumulated_tokens[k] += token_stats.get(k, 0)
        except Exception as e:
            print(f"[!] Lỗi khi gọi Gemini (Lần {attempt}/3): {e}")
            if attempt == 3:
                raise
            time.sleep(3)
            continue

        raw_script_data["slide_id"] = slide_id
        script_text = raw_script_data.get("script", "").strip()
        word_count = count_vietnamese_words(script_text)

        # Chạy kiểm thử QA bằng code
        is_passed, errors, grounding = qa_script_for_slide(
            slide_entry=slide_entry,
            script_data=raw_script_data,
            previous_openings=previous_openings
        )

        best_result = raw_script_data
        best_grounding = grounding

        if is_passed:
            print(f"[+] Slide {slide_id} đạt chuẩn QA ({word_count} từ, {len(grounding.get('bullets_covered', []))} bullets covered) ở lần thử {attempt}.")
            break
        else:
            print(f"[-] Slide {slide_id} chưa đạt QA ở lần {attempt} ({word_count} từ). Lỗi: {'; '.join(errors)}")
            retry_feedback = "Kịch bản lần trước chưa đạt yêu cầu sau:\n" + "\n".join(f"- {err}" for err in errors)
            time.sleep(2)

    # Đóng gói đối tượng Scene chuẩn SSOT V2
    script_text = best_result.get("script", "") if best_result else ""
    word_count = count_vietnamese_words(script_text)
    # Ước tính thời lượng nói: trung bình 2.5 từ / giây
    estimated_duration = round(word_count / 2.5, 2)

    scene_data = {
        "slide_id": slide_id,
        "script": script_text,
        "word_count": word_count,
        "duration_sec": estimated_duration,
        "grounding": best_grounding or {
            "uses_notes": bool(slide.get("notes")),
            "bullets_covered": best_result.get("bullets_covered", []) if best_result else [],
            "bullets_missed": best_result.get("bullets_missed", []) if best_result else [],
            "invented_claims": []
        },
        "audio_file": f"output/audio/slide_{slide_id:03d}.wav",
        "visual": slide.get("image", f"output/slides/slide_{slide_id:03d}.png"),
        "tokens": accumulated_tokens,
        "state": "scripted"
    }

    return scene_data


def generate_scripts_with_checkpoint(
    slides_data: List[Dict[str, Any]],
    auto_mode: bool = False,
    reset_mode: bool = False
) -> List[Dict[str, Any]]:
    """
    Điều phối sinh kịch bản cho toàn bộ presentation kèm cơ chế Checkpoint:
    - Bỏ qua các slide đã hoàn thành trước đó nếu bị crash giữa chừng.
    - Lưu output/state.json và output/script.json sau TỪNG SLIDE.
    - Tích hợp Human Review kiểm duyệt trước khi chuyển sang bước voice.
    """
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Xử lý cờ --reset
    if reset_mode:
        print("[*] Nhận cờ --reset: Xóa sạch checkpoint cũ để chạy lại từ đầu...")
        config.STATE_FILE.unlink(missing_ok=True)
        config.SCRIPT_FILE.unlink(missing_ok=True)

    # 2. Đọc checkpoint hiện có nếu có
    saved_scenes_map = {}
    total_token_stats = {"prompt_tokens": 0, "candidate_tokens": 0, "total_tokens": 0}

    if config.STATE_FILE.exists():
        try:
            with open(config.STATE_FILE, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                for item in state_data.get("slides", []):
                    sid = item.get("scene", {}).get("slide_id")
                    if sid and item.get("scene", {}).get("script"):
                        saved_scenes_map[sid] = item.get("scene")
            print(f"[*] Tìm thấy Checkpoint: Đã có {len(saved_scenes_map)} slide hoàn thành kịch bản trước đó.")
        except Exception as e:
            print(f"[!] Không thể đọc state.json ({e}), khởi tạo phiên mới...")

    # 3. Duyệt từng slide và sinh kịch bản
    previous_openings = []
    total_slides = len(slides_data)

    for i, entry in enumerate(slides_data):
        sid = entry["slide"]["id"]

        # Nếu slide đã có trong checkpoint và script hợp lệ -> BỎ QUA không gọi lại Gemini
        if sid in saved_scenes_map and saved_scenes_map[sid].get("script"):
            existing_scene = saved_scenes_map[sid]
            entry["scene"] = existing_scene
            word_cnt = existing_scene.get("word_count", count_vietnamese_words(existing_scene["script"]))
            print(f"[+] [Checkpoint] Bỏ qua Slide {sid}: Kịch bản đã sẵn sàng ({word_cnt} từ).")
            # Thu thập câu mở đầu
            from agents.qa import extract_opening_sentence
            previous_openings.append(extract_opening_sentence(existing_scene["script"]))
            continue

        # Lấy thông tin ngữ cảnh slide trước và slide sau
        prev_summary = ""
        if i > 0:
            prev_slide = slides_data[i - 1]["slide"]
            prev_summary = f"{prev_slide.get('title', '')} - Ghi chú: {prev_slide.get('notes', '')[:80]}"

        next_title = ""
        if i < total_slides - 1:
            next_slide = slides_data[i + 1]["slide"]
            next_title = next_slide.get("title", "")

        # Gọi Gemini sinh kịch bản cho slide hiện tại
        scene_result = write_script_for_single_slide(
            slide_entry=entry,
            previous_summary=prev_summary,
            next_title=next_title,
            previous_openings=previous_openings
        )
        entry["scene"] = scene_result

        # Thu thập câu mở đầu
        from agents.qa import extract_opening_sentence
        previous_openings.append(extract_opening_sentence(scene_result["script"]))

        # Cộng dồn token
        tok = scene_result.get("tokens", {})
        for k in ["prompt_tokens", "candidate_tokens", "total_tokens"]:
            total_token_stats[k] += tok.get(k, 0)

        # 4. LƯU CHECKPOINT NGAY LẬP TỨC SAU MỖI SLIDE
        checkpoint_payload = {
            "current_step": "scripted",
            "last_completed_slide": sid,
            "total_slides": total_slides,
            "timestamp": time.time(),
            "total_tokens": total_token_stats,
            "slides": slides_data
        }
        with open(config.STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(checkpoint_payload, f, ensure_ascii=False, indent=2)

        # Lưu file script.json
        scripts_export = [
            {
                "slide_id": it["slide"]["id"],
                "title": it["slide"]["title"],
                "script": it["scene"]["script"],
                "word_count": it["scene"]["word_count"],
                "duration_sec": it["scene"]["duration_sec"],
                "grounding": it["scene"]["grounding"]
            }
            for it in slides_data if it["scene"].get("script")
        ]
        with open(config.SCRIPT_FILE, "w", encoding="utf-8") as f:
            json.dump(scripts_export, f, ensure_ascii=False, indent=2)

    # 5. BƯỚC HUMAN REVIEW
    if not auto_mode:
        slides_data = run_human_review(slides_data)
    else:
        print("\n[*] Cờ --auto được bật: Bỏ qua bước Human Review kịch bản.")

    # Cập nhật trạng thái slide sau khi được duyệt
    for entry in slides_data:
        entry["scene"]["state"] = "checked"

    # Lưu lại trạng thái cuối cùng của bước kịch bản
    checkpoint_payload = {
        "current_step": "checked",
        "total_slides": total_slides,
        "timestamp": time.time(),
        "total_tokens": total_token_stats,
        "slides": slides_data
    }
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint_payload, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Đã hoàn thành và lưu kịch bản {total_slides} slide vào {config.SCRIPT_FILE.name}")
    return slides_data


def run_human_review(slides_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Dừng quy trình và hiển thị bảng kiểm duyệt Human Review cho từng slide.
    Người dùng có thể bấm Y duyệt hoặc chỉnh sửa trực tiếp qua file script.json.
    """
    print("\n" + "=" * 70)
    print("👨‍🏫 BƯỚC HUMAN REVIEW — DUYỆT KỊCH BẢN TRƯỚC KHI THU ÂM")
    print("=" * 70)
    print("Vui lòng xem xét kỹ kịch bản của từng slide dưới đây:")

    for item in slides_data:
        s = item["slide"]
        sc = item["scene"]
        g = sc.get("grounding", {})

        print("\n" + "-" * 70)
        print(f"📌 [SLIDE {s['id']}] {s['title']}")
        print(f"🖼️ Ảnh slide       : {s.get('image')}")
        print(f"📝 Số từ           : {sc.get('word_count')} từ (Khoảng {sc.get('duration_sec')}s)")
        print(f"🎯 Bullets covered : {len(g.get('bullets_covered', []))}/{len(s.get('bullets', []))}")
        if g.get("invented_claims"):
            print(f"⚠️ Số liệu ngoài   : {g.get('invented_claims')}")
        print("\n💬 LỜI THUYẾT MINH:")
        print(f"\"{sc.get('script')}\"")

    print("\n" + "=" * 70)
    print("HƯỚNG DẪN DUYỆT:")
    print("1. Bấm [Y] hoặc [Enter] để CHẤP THUẬN và bắt đầu tạo giọng đọc TTS.")
    print("2. Hoặc mở file 'output/script.json', chỉnh sửa câu chữ mong muốn, sau đó quay lại đây bấm [Y].")
    print("=" * 70)

    try:
        choice = input("👉 Bạn có đồng ý chuyển sang bước tạo giọng nói? (Y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = "y"

    if choice in ["", "y", "yes"]:
        print("[+] Người dùng đã duyệt toàn bộ kịch bản. Chuyển sang bước tiếp theo!")
        # Đọc lại script.json phòng trường hợp người dùng sửa file ngoài
        if config.SCRIPT_FILE.exists():
            try:
                with open(config.SCRIPT_FILE, "r", encoding="utf-8") as f:
                    saved_scripts = json.load(f)
                    for item in slides_data:
                        sid = item["slide"]["id"]
                        for sv in saved_scripts:
                            if sv.get("slide_id") == sid:
                                item["scene"]["script"] = sv.get("script", item["scene"]["script"])
                                item["scene"]["word_count"] = count_vietnamese_words(item["scene"]["script"])
            except Exception:
                pass
        return slides_data
    else:
        print("[!] Tạm dừng quy trình theo yêu cầu người dùng. Bạn có thể chỉnh sửa kịch bản trong output/script.json.")
        sys.exit(0)
