"""
app.py - AI Video Agent V2 Web Studio Server
Giao diện Web trực quan hỗ trợ xem trước slide thật, duyệt kịch bản Human Review và theo dõi tiến độ.
"""

import os
import sys
import json
import time
import queue
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from werkzeug.utils import secure_filename

# Đảm bảo xuất UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import config
from agents.parse import parse_presentation

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB max upload

@app.after_request
def add_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Trạng thái tiến trình toàn cục
log_queues = []

def get_initial_timings():
    return {
        "step_1": {"name": "Trích xuất Slide", "duration": 0.0, "status": "pending", "formatted": ""},
        "step_2": {"name": "Tạo Kịch Bản", "duration": 0.0, "status": "pending", "formatted": ""},
        "step_3": {"name": "QA Kịch Bản", "duration": 0.0, "status": "pending", "formatted": ""},
        "step_4": {"name": "Lồng Tiếng TTS", "duration": 0.0, "status": "pending", "formatted": ""},
        "step_5": {"name": "Render & Hardsub", "duration": 0.0, "status": "pending", "formatted": ""},
        "total_duration": 0.0,
        "total_formatted": "0.0s"
    }

current_job = {
    "status": "idle",
    "progress": 0,
    "current_step": "",
    "log": [],
    "result_video": None,
    "error": None,
    "timings": get_initial_timings()
}

def broadcast_log(step: str, progress: int, message: str, timings: dict = None):
    current_job["current_step"] = step
    current_job["progress"] = progress
    msg_entry = {
        "time": time.strftime("%H:%M:%S"),
        "step": step,
        "progress": progress,
        "message": message
    }
    if timings:
        current_job["timings"] = timings
        msg_entry["timings"] = timings

    current_job["log"].append(msg_entry)
    data = json.dumps(msg_entry, ensure_ascii=False)
    for q in list(log_queues):
        try:
            q.put_nowait(data)
        except Exception:
            pass


@app.route('/')
def index():
    hw = config.get_hardware_device_info()
    return render_template(
        'index.html',
        default_voice=config.TTS_VOICE,
        default_rate=config.TTS_RATE,
        default_volume=config.TTS_VOLUME,
        gemini_model=config.GEMINI_MODEL,
        hardware_device=hw["device_name"]
    )


@app.route('/output/slides/<path:filename>')
def serve_slide_image(filename):
    return send_from_directory(str(config.SLIDES_DIR), filename)


@app.route('/output/video/<path:filename>')
def serve_output_video(filename):
    return send_from_directory(str(config.VIDEO_DIR), filename)


@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "Không có file nào được tải lên"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Chưa chọn file"}), 400
    if not file.filename.lower().endswith(('.pptx', '.ppt')):
        return jsonify({"error": "Chỉ chấp nhận file PowerPoint (.pptx)"}), 400

    filename = secure_filename(file.filename)
    dest_path = config.INPUT_DIR / filename
    file.save(str(dest_path))
    return jsonify({
        "success": True,
        "filename": filename,
        "path": str(dest_path),
        "message": f"Tải lên thành công: {filename}"
    })


@app.route('/api/extract-and-script', methods=['POST'])
def extract_and_script():
    """Trích xuất slide thật và tạo kịch bản V2."""
    data = request.json or {}
    filename = data.get('filename', '')
    if not filename:
        return jsonify({"error": "Chưa chỉ định file"}), 400

    pptx_path = config.INPUT_DIR / filename
    if not pptx_path.exists():
        pptx_path = config.TEST_DATA_DIR / filename
    if not pptx_path.exists():
        return jsonify({"error": f"Không tìm thấy file: {filename}"}), 404

    try:
        broadcast_log("Trích xuất Slide", 10, f"Đang trích xuất slide thật từ {filename}...")
        slides_data = parse_presentation(pptx_path)
        broadcast_log("Trích xuất Slide", 30, f"Đã trích xuất {len(slides_data)} slide 1080p thành công.")
        return jsonify({"success": True, "slides": slides_data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/script', methods=['GET', 'POST'])
def handle_script():
    """Lấy hoặc cập nhật kịch bản sau Human Review."""
    if request.method == 'GET':
        if config.SCRIPT_FILE.exists():
            with open(config.SCRIPT_FILE, 'r', encoding='utf-8') as f:
                scripts = json.load(f)
            return jsonify({"success": True, "scripts": scripts})
        return jsonify({"success": False, "scripts": []})

    data = request.json or {}
    scripts = data.get('scripts', [])
    with open(config.SCRIPT_FILE, 'w', encoding='utf-8') as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)
    return jsonify({"success": True, "message": "Đã lưu kịch bản cập nhật."})


@app.route('/api/progress-stream')
def progress_stream():
    """SSE endpoint truyền log tiến độ thời gian thực về browser."""
    def event_stream():
        q = queue.Queue()
        log_queues.append(q)
        for old_msg in current_job["log"][-20:]:
            yield f"data: {json.dumps(old_msg, ensure_ascii=False)}\n\n"
        try:
            while True:
                try:
                    data = q.get(timeout=25.0)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            if q in log_queues:
                log_queues.remove(q)

    return Response(event_stream(), mimetype="text/event-stream")


@app.route('/api/status', methods=['GET'])
def get_status():
    hw = config.get_hardware_device_info()
    return jsonify({
        "status": current_job["status"],
        "progress": current_job["progress"],
        "current_step": current_job["current_step"],
        "result_video": current_job["result_video"],
        "error": current_job["error"],
        "timings": current_job["timings"],
        "hardware": hw
    })


@app.route('/api/latest-video')
def get_latest_video():
    if config.FINAL_VIDEO_FILE.exists():
        stat = config.FINAL_VIDEO_FILE.stat()
        return jsonify({
            "exists": True,
            "filename": config.FINAL_VIDEO_FILE.name,
            "url": f"/output/video/{config.FINAL_VIDEO_FILE.name}?t={int(stat.st_mtime)}",
            "size_mb": round(stat.st_size / (1024 * 1024), 2)
        })
    return jsonify({"exists": False})


if __name__ == '__main__':
    hw = config.get_hardware_device_info()
    print("=" * 60)
    print("AI VIDEO AGENT V2 - WEB STUDIO")
    print(f"Địa chỉ: http://127.0.0.1:5000")
    print(f"Thiết bị: {hw['device_name']}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
