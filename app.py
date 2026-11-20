"""
app.py - AI Video Agent V2 Web Studio Server
Giao diện Web đơn giản: Upload slide .pptx -> Tùy chọn -> Chạy pipeline -> Xem & Tải video thành phẩm.
Tích hợp trực tiếp với LangGraph pipeline (agents/graph.py).
Mỗi lần chạy là một job riêng biệt lưu tại output/jobs/<job_id>/.
"""

import os
import sys
import json
import time
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Đảm bảo xuất UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from werkzeug.utils import secure_filename
from pptx import Presentation

import config
from agents.graph import run_pipeline

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # Tối đa 100 MB theo yêu cầu

# Thư mục lưu trữ công việc (jobs)
JOBS_DIR = config.OUTPUT_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# Bộ nhớ lưu trạng thái các job: job_id -> dict
JOBS: Dict[str, Dict[str, Any]] = {}
JOB_LOCK = threading.Lock()
ACTIVE_JOB_ID: Optional[str] = None


def count_slides_in_pptx(pptx_path: Path) -> int:
    """Đếm số slide trong file PowerPoint bằng python-pptx mà không cần chạy pipeline."""
    try:
        prs = Presentation(str(pptx_path.resolve()))
        return len(prs.slides)
    except Exception as e:
        print(f"[!] Lỗi khi đếm slide trong {pptx_path.name}: {e}")
        return 0


def count_pages_in_pdf(pdf_path: Path) -> int:
    """Đếm số trang trong file PDF bằng PyMuPDF mà không cần chạy pipeline."""
    try:
        import fitz
        doc = fitz.open(str(pdf_path.resolve()))
        cnt = len(doc)
        doc.close()
        return cnt
    except Exception as e:
        print(f"[!] Lỗi khi đếm trang PDF trong {pdf_path.name}: {e}")
        return 0


class JobLogCapture:
    """Bộ thu thập stdout dòng-theo-dòng realtime và cập nhật trạng thái các node pipeline."""
    def __init__(self, job_id: str, jobs_dict: dict, original_stdout):
        self.job_id = job_id
        self.jobs_dict = jobs_dict
        self.original_stdout = original_stdout
        self.buffer = ""
        self.lock = threading.Lock()

    def write(self, text: str):
        self.original_stdout.write(text)
        with self.lock:
            self.buffer += text
            if "\n" in self.buffer:
                lines = self.buffer.split("\n")
                for line in lines[:-1]:
                    cleaned = line.strip()
                    if cleaned:
                        self._process_line(cleaned)
                self.buffer = lines[-1]

    def flush(self):
        self.original_stdout.flush()
        with self.lock:
            if self.buffer.strip():
                self._process_line(self.buffer.strip())
                self.buffer = ""

    def _process_line(self, line: str):
        job = self.jobs_dict.get(self.job_id)
        if not job:
            return

        job["logs"].append(line)
        steps = job["step_states"]

        # Nhận diện tiến trình qua log các node
        if "[NODE 1: PARSE]" in line:
            job["step"] = "parse"
            steps["parse"] = "running"
            job["progress"] = max(job["progress"], 10)
        elif "[+] Trích xuất thành công" in line:
            steps["parse"] = "done"
            job["progress"] = max(job["progress"], 18)

        elif "[NODE 2: SCRIPT & QA]" in line:
            steps["parse"] = "done"
            job["step"] = "script"
            steps["script"] = "running"
            job["progress"] = max(job["progress"], 20)
        elif "Đã hoàn thành và lưu kịch bản" in line:
            steps["script"] = "done"
            job["progress"] = max(job["progress"], 42)

        elif "[NODE 3: VOICE TTS]" in line:
            steps["script"] = "done"
            job["step"] = "voice"
            steps["voice"] = "running"
            job["progress"] = max(job["progress"], 45)
        elif "Đã hoàn tất tạo giọng đọc cho toàn bộ" in line:
            steps["voice"] = "done"
            job["progress"] = max(job["progress"], 68)

        elif "[NODE 4: RENDER]" in line:
            steps["voice"] = "done"
            job["step"] = "render"
            steps["render"] = "running"
            job["progress"] = max(job["progress"], 70)
        elif "Đã hoàn tất render toàn bộ" in line:
            steps["render"] = "done"
            job["progress"] = max(job["progress"], 85)

        elif "[NODE 5: ASSEMBLE]" in line:
            steps["render"] = "done"
            job["step"] = "assemble"
            steps["assemble"] = "running"
            job["progress"] = max(job["progress"], 88)
        elif "HOÀN THÀNH: Video bài giảng hoàn chỉnh" in line:
            steps["assemble"] = "done"
            job["progress"] = max(job["progress"], 96)

        elif "[NODE 6: QA FINAL]" in line:
            steps["assemble"] = "done"
            job["step"] = "qa_final"
            steps["qa_final"] = "running"
            job["progress"] = max(job["progress"], 98)
        elif "QA Final ĐẠT CHUẨN" in line:
            steps["qa_final"] = "done"
            job["progress"] = 100

        elif "[!]" in line and ("Lỗi" in line or "thất bại" in line):
            curr = job.get("step")
            if curr and curr in steps and steps[curr] == "running":
                job["step_errors"][curr] = line[:120]


def configure_job_directories(job_id: str, reset_mode: bool = False) -> Path:
    """Cấu hình lại các đường dẫn output của config trỏ vào thư mục riêng của job."""
    job_dir = JOBS_DIR / job_id
    audio_dir = job_dir / "audio"
    video_dir = job_dir / "video"
    slides_dir = job_dir / "slides"

    for d in [job_dir, audio_dir, video_dir, slides_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Nếu không phải --reset và đã có script.json ở output chung, copy sang để tái sử dụng ngay kịch bản đã duyệt
    master_script = config.OUTPUT_DIR / "script.json"
    target_script = job_dir / "script.json"
    if master_script.exists() and not reset_mode and not target_script.exists():
        import shutil
        try:
            shutil.copy2(master_script, target_script)
        except Exception:
            pass

    config.AUDIO_DIR = audio_dir
    config.VIDEO_DIR = video_dir
    config.SLIDES_DIR = slides_dir
    config.STATE_FILE = job_dir / "state.json"
    config.SCRIPT_FILE = target_script
    config.FINAL_VIDEO_FILE = video_dir / "final_lecture.mp4"
    config.FINAL_SRT_FILE = video_dir / "final_lecture.srt"
    return job_dir


def restore_default_config_directories():
    """Khôi phục lại đường dẫn config về mặc định ban đầu."""
    config.AUDIO_DIR = config.OUTPUT_DIR / "audio"
    config.VIDEO_DIR = config.OUTPUT_DIR / "video"
    config.SLIDES_DIR = config.OUTPUT_DIR / "slides"
    config.STATE_FILE = config.OUTPUT_DIR / "state.json"
    config.SCRIPT_FILE = config.OUTPUT_DIR / "script.json"
    config.FINAL_VIDEO_FILE = config.VIDEO_DIR / "final_lecture.mp4"
    config.FINAL_SRT_FILE = config.VIDEO_DIR / "final_lecture.srt"


def worker_pipeline_thread(
    job_id: str,
    pptx_path: Path,
    auto_mode: bool,
    reset_mode: bool,
    provider: str,
    voice: Optional[str],
    draft_mode: bool
):
    """Luồng worker thực thi pipeline độc lập cho một job."""
    global ACTIVE_JOB_ID

    job = JOBS[job_id]
    job_dir = configure_job_directories(job_id, reset_mode)
    original_stdout = sys.stdout
    capture = JobLogCapture(job_id, JOBS, original_stdout)
    sys.stdout = capture

    try:
        print(f"\n{'='*70}")
        print(f"🎬 BẮT ĐẦU JOB: {job_id}")
        print(f"📁 Slide file  : {pptx_path.name}")
        print(f"⚡ Tùy chọn    : Auto={auto_mode}, Reset={reset_mode}, Draft={draft_mode}")
        print(f"🎙️ Giọng đọc   : Provider={provider}, Voice={voice or 'mặc định'}")
        print(f"📂 Thư mục job : {job_dir}")
        print(f"{'='*70}\n")

        # Gọi hàm run_pipeline chính thức của LangGraph
        result = run_pipeline(
            pptx_path=pptx_path,
            auto_mode=auto_mode,
            reset_mode=reset_mode,
            provider=provider,
            voice=voice,
            draft_mode=draft_mode
        )

        capture.flush()
        err = result.get("error") if isinstance(result, dict) else None

        final_vid = job_dir / "video" / "final_lecture.mp4"
        final_ass = job_dir / "video" / "final_lecture.ass"
        final_script = job_dir / "script.json"

        if err or not final_vid.exists() or final_vid.stat().st_size < 50000:
            error_msg = err or "File video hoàn thiện không tồn tại hoặc rỗng."
            job["status"] = "error"
            job["done"] = False
            job["error"] = error_msg
            curr_step = job.get("step", "assemble")
            job["step_states"][curr_step] = "error"
            job["step_errors"][curr_step] = error_msg
            print(f"[!] Job {job_id} kết thúc với lỗi: {error_msg}")
        else:
            job["status"] = "completed"
            job["done"] = True
            job["progress"] = 100
            for s in job["step_states"]:
                job["step_states"][s] = "done"

            job["outputs"] = {
                "video": f"/api/download/{job_id}/final_lecture.mp4",
                "video_stream": f"/api/video/{job_id}",
                "subtitles": f"/api/download/{job_id}/final_lecture.ass" if final_ass.exists() else f"/api/download/{job_id}/final_lecture.srt",
                "script": f"/api/download/{job_id}/script.json"
            }
            print(f"\n🎉 [THÀNH CÔNG] Job {job_id} đã hoàn tất trọn vẹn!")
            print(f"   -> Video : {final_vid.resolve()} ({final_vid.stat().st_size / (1024*1024):.2f} MB)")

    except Exception as e:
        capture.flush()
        err_msg = f"Lỗi ngoại lệ khi chạy pipeline: {str(e)}"
        print(f"\n[!] Ngoại lệ không mong muốn: {err_msg}")
        job["status"] = "error"
        job["done"] = False
        job["error"] = err_msg
        curr_step = job.get("step", "parse")
        job["step_states"][curr_step] = "error"
        job["step_errors"][curr_step] = str(e)[:100]

    finally:
        sys.stdout = original_stdout
        restore_default_config_directories()
        with JOB_LOCK:
            ACTIVE_JOB_ID = None


# ==============================================================================
# CÁC ENDPOINT FLASK API (Gọn gàng, đúng yêu cầu)
# ==============================================================================

@app.route('/')
def index():
    """Trả về giao diện web HTML duy nhất."""
    hw = config.get_hardware_device_info()
    return render_template(
        'index.html',
        hardware_info=f"{hw['device_name']} ({'Tăng tốc phần cứng' if hw['is_gpu'] else 'CPU'})",
        default_voice=config.TTS_VOICE,
        edge_voice=config.EDGE_TTS_VOICE
    )


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Nhận file .pptx hoặc .pdf, lưu vào input/, đếm số slide/trang và trả về {filename, slides, is_pdf, type}."""
    if 'file' not in request.files:
        return jsonify({"error": "Không tìm thấy file tải lên"}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({"error": "Chưa chọn file"}), 400

    lower_name = file.filename.lower()
    if not (lower_name.endswith('.pptx') or lower_name.endswith('.pdf')):
        return jsonify({"error": "Chỉ chấp nhận file định dạng PowerPoint (.pptx) và PDF (.pdf)"}), 400

    ext = Path(file.filename).suffix.lower()
    filename = secure_filename(file.filename)
    if not filename:
        filename = f"document_{int(time.time())}{ext}"

    config.INPUT_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = config.INPUT_DIR / filename
    file.save(str(dest_path))

    is_pdf = ext == '.pdf'
    if is_pdf:
        items_count = count_pages_in_pdf(dest_path)
    else:
        items_count = count_slides_in_pptx(dest_path)

    return jsonify({
        "success": True,
        "filename": filename,
        "slides": items_count,
        "is_pdf": is_pdf,
        "type": "PDF" if is_pdf else "PPTX"
    })


@app.route('/api/voices', methods=['GET'])
def api_voices():
    """Trả về danh mục đầy đủ tất cả các giọng đọc khả dụng trong hệ thống."""
    return jsonify({
        "success": True,
        "voices": getattr(config, "AVAILABLE_VOICES", []),
        "default": config.TTS_VOICE
    })


@app.route('/api/run', methods=['POST'])
def api_run():
    """
    Nhận {filename, auto, reset, draft, provider, voice},
    chạy pipeline trong thread riêng và trả về {job_id}.
    Khóa không cho phép chạy chồng khi đang có job chạy.
    """
    global ACTIVE_JOB_ID

    with JOB_LOCK:
        if ACTIVE_JOB_ID is not None and ACTIVE_JOB_ID in JOBS:
            if JOBS[ACTIVE_JOB_ID].get("status") == "running":
                return jsonify({
                    "error": "Hiện tại đang có tiến trình chạy. Vui lòng chờ cho đến khi hoàn thành."
                }), 409

    data = request.json or {}
    filename = data.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "Chưa cung cấp tên file slide PowerPoint (.pptx)"}), 400

    # Tìm file trong input/ hoặc test_data/
    pptx_path = config.INPUT_DIR / filename
    if not pptx_path.exists():
        pptx_path = config.TEST_DATA_DIR / filename
    if not pptx_path.exists():
        return jsonify({"error": f"Không tìm thấy file slide tại: {filename}"}), 404

    auto_mode = bool(data.get("auto", True))
    reset_mode = bool(data.get("reset", False))
    draft_requested = bool(data.get("draft", False))
    voice_input = str(data.get("voice", config.TTS_VOICE)).strip()

    # Xác định provider và voice linh hoạt hỗ trợ toàn bộ các giọng trong hệ thống
    if voice_input.startswith("vi-VN-") or "edge" in voice_input.lower():
        provider = "edge-tts"
        voice = voice_input if "Neural" in voice_input else config.EDGE_TTS_VOICE
        draft_mode = True if "draft" not in data else draft_requested
    elif voice_input.startswith("gtts:") or voice_input.lower() == "gtts":
        provider = "gtts"
        voice = "gtts:vi"
        draft_mode = True if "draft" not in data else draft_requested
    else:
        provider = "zerotts"
        voice = voice_input if voice_input.startswith("zerotts:") else f"zerotts:{voice_input}"
        draft_mode = draft_requested

    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"

    JOBS[job_id] = {
        "job_id": job_id,
        "filename": filename,
        "status": "running",
        "step": "parse",
        "progress": 5,
        "step_states": {
            "parse": "waiting",
            "script": "waiting",
            "voice": "waiting",
            "render": "waiting",
            "assemble": "waiting",
            "qa_final": "waiting"
        },
        "step_errors": {},
        "logs": [f"Khởi động job {job_id} cho bài giảng {filename}..."],
        "done": False,
        "error": None,
        "outputs": {},
        "created_at": time.time(),
        "dir": str(JOBS_DIR / job_id)
    }

    with JOB_LOCK:
        ACTIVE_JOB_ID = job_id

    # Khởi động thread xử lý ngầm
    t = threading.Thread(
        target=worker_pipeline_thread,
        kwargs={
            "job_id": job_id,
            "pptx_path": pptx_path,
            "auto_mode": auto_mode,
            "reset_mode": reset_mode,
            "provider": provider,
            "voice": voice,
            "draft_mode": draft_mode
        },
        daemon=True
    )
    t.start()

    return jsonify({"success": True, "job_id": job_id})


@app.route('/api/status/<job_id>', methods=['GET'])
def api_status(job_id: str):
    """Trả về trạng thái, tiến độ và log của job để frontend polling mỗi 2 giây."""
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": f"Không tìm thấy job: {job_id}"}), 404

    return jsonify({
        "job_id": job["job_id"],
        "status": job["status"],
        "step": job["step"],
        "progress": job["progress"],
        "step_states": job["step_states"],
        "step_errors": job["step_errors"],
        "logs": job["logs"][-100:],  # 100 dòng log mới nhất
        "done": job["done"],
        "error": job["error"],
        "outputs": job["outputs"]
    })


@app.route('/api/download/<job_id>/<filename>', methods=['GET'])
def api_download(job_id: str, filename: str):
    """Tải file video, phụ đề hoặc kịch bản của một job cụ thể."""
    job = JOBS.get(job_id)
    job_dir = JOBS_DIR / job_id

    if not job_dir.exists():
        return abort(404, description="Thư mục job không tồn tại")

    safe_name = secure_filename(filename)
    if safe_name in ["final_lecture.mp4", "final_lecture.ass", "final_lecture.srt"]:
        target_dir = job_dir / "video"
    elif safe_name == "script.json":
        target_dir = job_dir
    else:
        return abort(400, description="Tên file không hợp lệ")

    file_p = target_dir / safe_name
    if not file_p.exists():
        return abort(404, description=f"Không tìm thấy file: {safe_name}")

    return send_from_directory(str(target_dir.resolve()), safe_name, as_attachment=True)


@app.route('/api/video/<job_id>', methods=['GET'])
def api_video_stream(job_id: str):
    """Phát video trực tiếp trong trình duyệt để người dùng xem trước."""
    job_dir = JOBS_DIR / job_id
    video_p = job_dir / "video" / "final_lecture.mp4"
    if not video_p.exists():
        return abort(404, description="Chưa có video thành phẩm cho job này")

    return send_from_directory(str(video_p.parent.resolve()), video_p.name, mimetype="video/mp4", as_attachment=False)


@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "Dung lượng file vượt quá giới hạn cho phép (100MB)."}), 413


if __name__ == '__main__':
    hw = config.get_hardware_device_info()
    print("=" * 70)
    print("🚀 AI VIDEO AGENT V2 — WEB STUDIO")
    print("📍 Truy cập ứng dụng tại: http://localhost:5000")
    print(f"🖥️ Thiết bị phát hiện   : {hw['device_name']} ({'Tăng tốc phần cứng' if hw['is_gpu'] else 'CPU'})")
    print(f"📂 Thư mục Jobs         : {JOBS_DIR.resolve()}")
    print("=" * 70)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
