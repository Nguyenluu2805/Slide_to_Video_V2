# 🎬 AI Video Agent V2 — Chuyển Đổi Slide Thuyết Trình Thành Video

Hệ thống **AI Agent tự động hóa chuyển đổi bài giảng PowerPoint (`.pptx`) kèm Speaker Notes thành Video thuyết trình chuyên nghiệp 1080p (`.mp4`)**. Tích hợp kịch bản sư phạm tự nhiên (Google Gemini 2.5 Flash), lồng tiếng tiếng Việt chất lượng cao (ZeroTTS ONNX local / Microsoft Edge Neural TTS dự phòng), phụ đề `.srt` khớp timestamp thật từ Faster-Whisper và điều phối luồng xử lý bằng LangGraph State Machine có checkpoint phục hồi sau sự cố.

---

## 🎯 Mục Tiêu V2 — Chỉ 1 Việc Duy Nhất

* **Đầu vào:** 1 file `.pptx` thuyết trình + Speaker Notes.
* **Đầu ra:** 1 video thuyết trình `.mp4` 1920x1080 @ 30fps, giọng đọc tiếng Việt tự nhiên, phụ đề `.srt` khớp timestamp thật, kịch bản bám sát nội dung slide.
* **Bộ kiểm thử chuẩn:** `test_data/Ex01_Hybrid_Workflow.pptx` (Chương Ex01: Kiến Trúc Hybrid Workflow).

> [!NOTE]
> **Định hướng V2:** Tập trung hoàn toàn vào video thuyết trình bài giảng chất lượng cao. Đã loại bỏ hoàn toàn các thành phần dư thừa: Code demo, Remotion, RVC, ElevenLabs, EverAI và bộ vẽ Slide Card giả.

---

## ✨ Điểm Cốt Lõi Của Kiến Trúc V2

1. **Trích xuất Slide Thật 1080p (`agents/parse.py`)**:
   * **Ưu tiên 1:** PowerPoint COM trên Windows (`win32com.client`).
   * **Ưu tiên 2:** LibreOffice headless (`soffice --headless --convert-to pdf` rồi xuất PNG 1920x1080).
   * **Không có cả 2:** Dừng và báo lỗi rõ ràng. Tuyệt đối không vẽ card PIL giả.
   * **Validation:** Cảnh báo các slide rỗng, thiếu title, bullets hoặc speaker notes vào `state.json`.

2. **Kịch Bản Bám Sát Slide & Speaker Notes (`agents/script.py`)**:
   * Quy tắc 1 slide = 1 call Gemini kèm `response_schema` bắt buộc.
   * Nguồn: Speaker notes là nguồn chính (70%), bullets + title là nguồn phụ (30%). Cấm bịa đặt số liệu ngoài slide.
   * Độ dài: 150–220 từ tiếng Việt (~60–90 giây/slide).
   * Cấu trúc: Mở (nối từ slide trước) -> Thân (diễn giải notes + bullets) -> Chốt (chuyển sang slide sau). Giữ nguyên thuật ngữ tiếng Anh gốc.

3. **QA Kịch Bản Bằng Code (`agents/qa.py`)**:
   * Kiểm tra tự động bằng code: Độ dài từ (150–220 từ), độ bao phủ bullet (`bullets_covered >= 80%`), phát hiện câu template lặp và đánh dấu `invented_claims`.

4. **Human Review Bắt Buộc Trước Khi Lồng Tiếng**:
   * Hệ thống dừng lại hiển thị ảnh slide + kịch bản + số từ + bullet coverage để người dùng bấm `Y` duyệt hoặc chỉnh sửa trực tiếp tại `output/script.json`.
   * Cờ `--auto` cho phép bỏ qua bước duyệt khi chạy tự động hoàn toàn.

5. **Phòng Thu Lồng Tiếng Tách Biệt (`agents/voice.py`)**:
   * Một interface duy nhất: `synthesize(text, provider, voice_ref) -> Path`.
   * **ZeroTTS (ONNX local)** là engine chính: Tự động phân đoạn câu sư phạm (max 24 từ), ngắt nghỉ 0.45s, hỗ trợ tăng tốc GPU qua CUDA/DirectML.
   * **Edge-TTS** (`vi-VN-NamMinhNeural` / `vi-VN-HoaiMyNeural`) là engine dự phòng 100% miễn phí.
   * Kiểm tra file âm thanh câm bằng `volumedetect`.

6. **Render & Assemble Chuẩn Phát Sóng (`agents/render.py`, `agents/assemble.py`)**:
   * FFmpeg render video 1920x1080 @ 30fps, Ken Burns hiệu ứng phóng nhẹ (1.00 -> 1.05), thời lượng khớp chính xác với âm thanh thật.
   * Faster-Whisper trích xuất phụ đề `.srt` tiếng Việt theo timestamp thật.
   * Chuẩn hóa âm thanh chuẩn EBU R128 (`loudnorm -16 LUFS`), hardsub phụ đề vào video.

7. **LangGraph State Machine & Checkpoint Phục Hồi (`agents/graph.py`)**:
   * `[PARSED] -> [SCRIPTED] -> [QA_SCRIPT] -> [HUMAN REVIEW] -> [VOICED] -> [RENDERED] -> [QA_FINAL] -> [ASSEMBLED]`.
   * Lưu checkpoint `output/state.json` sau mỗi slide. Khi gặp sự cố mạng hoặc tắt ngang, chạy lại lệnh cũ sẽ tiếp tục ngay từ slide gián đoạn mà không cần gọi lại Gemini hay tổng hợp lại giọng đọc các slide trước đó.

---

## 📁 Cấu Trúc Dự Án V2

```
AI_Video_Agent_V2/
├── main.py                     # CLI chính: python main.py --slides <file> [--auto] [--reset]
├── app.py                      # Web Studio (Flask)
├── requirements.txt            # Thư viện dùng chung
├── requirements-windows.txt    # Thư viện đặc thù Windows (pywin32)
├── .env.example                # Mẫu biến môi trường
├── config.py                   # Cấu hình tập trung duy nhất
├── README.md                   # Hướng dẫn dự án
├── agents/                     # Các module kiến trúc V2
│   ├── __init__.py
│   ├── parse.py                # Trích xuất slide & xuất ảnh thật 1080p
│   ├── script.py               # 1 slide = 1 Gemini call + response_schema
│   ├── qa.py                   # Code-based QA kịch bản & video
│   ├── voice.py                # Interface TTS thống nhất: ZeroTTS & Edge-TTS
│   ├── render.py               # FFmpeg render slide video Ken Burns
│   ├── assemble.py             # Faster-Whisper .srt + loudnorm -16 LUFS + nối video
│   └── graph.py                # LangGraph State Machine & Checkpoint
├── test_data/
│   └── Ex01_Hybrid_Workflow.pptx # Bài giảng test chuẩn 6 slide
└── output/                     # Thư mục đầu ra sản phẩm (gitignored)
    ├── state.json              # Checkpoint trạng thái
    ├── script.json             # Kịch bản các slide
    ├── slides/                 # Ảnh slide 1080p thật
    ├── audio/                  # File âm thanh từng slide
    └── video/
        ├── final_lecture.mp4   # Video bài giảng thành phẩm
        └── final_lecture.srt   # Phụ đề khớp thời gian thật
```

---

## 🚀 Hướng Dẫn Cài Đặt & Sử Dụng

### 1. Cài đặt môi trường & Tăng tốc GPU CUDA (ZeroTTS)

```bash
# Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt

# Trên hệ điều hành Windows (cần thiết cho PowerPoint COM)
pip install -r requirements-windows.txt
```

#### Hướng dẫn cấu hình ONNX Runtime GPU:
> [!IMPORTANT]
> Gói `onnxruntime` (bản CPU) và `onnxruntime-gpu` (bản GPU) **không thể cài đặt chung**. Khi nâng cấp hoặc chuyển đổi, bắt buộc phải gỡ bản cũ trước:

1. **Kiểm tra phiên bản CUDA bằng lệnh `nvidia-smi`:**
   ```bash
   nvidia-smi
   ```
2. **Cài đặt phiên bản `onnxruntime-gpu` tương thích:**
   * **CUDA 12.x / 13.x** (Driver NVIDIA từ 2023 trở lại đây, `nvidia-smi` báo CUDA 12.x / 13.x):
     ```bash
     pip uninstall onnxruntime -y
     pip install onnxruntime-gpu>=1.20
     ```
   * **CUDA 11.8** (`nvidia-smi` báo CUDA Version 11.8):
     ```bash
     pip uninstall onnxruntime -y
     pip install onnxruntime-gpu==1.19.2
     ```
   * **Máy không có GPU NVIDIA:** Giữ nguyên `onnxruntime` bản CPU (`pip install onnxruntime`), hệ thống sẽ tự động chạy CPU an toàn mà không cần GPU.
3. **Kiểm tra xác nhận CUDA Provider:**
   ```bash
   python -c "import onnxruntime as ort; print(ort.get_available_providers())"
   ```
   Danh sách trả về phải chứa `'CUDAExecutionProvider'`.

### 2. Cấu hình biến môi trường
Tạo file `.env` từ `.env.example`:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

TTS_PROVIDER=zerotts
ZEROTTS_MODEL=zeroweight-ai/ZeroTTS
ZEROTTS_VOICE=maichi
EDGE_TTS_VOICE=vi-VN-NamMinhNeural

VIDEO_WIDTH=1920
VIDEO_HEIGHT=1080
VIDEO_FPS=30
SLIDE_PRE_PAUSE=0.8
SLIDE_POST_PAUSE=1.5
```

### 3. Khởi chạy Web Studio (Giao diện đồ họa tiện lợi)
```bash
python app.py
```
Mở trình duyệt tại: **`http://localhost:5000`**
- **Khối 1 — Input:** Kéo thả file `.pptx` (tối đa 100MB), hệ thống tự động đếm số slide.
- **Khối 2 — Tùy chọn:** Bật/tắt tự động (`--auto`), chạy lại từ đầu (`--reset`), chế độ nháp siêu tốc (`--draft`), chọn giọng đọc (`ZeroTTS - maichi` hoặc `Edge-TTS - NamMinh`). Nút Chạy tự động khóa chống chạy chồng.
- **Khối 3 — Tiến độ & Kết quả:** Thanh tiến độ thời gian thực, 6 bước (`Parse` → `Script` → `Voice` → `Render` → `Assemble` → `QA`), log chi tiết, xem trước video và tải video (.mp4), phụ đề (.ass), kịch bản (.json).

### 4. Chạy qua dòng lệnh CLI
```bash
# Chạy có duyệt kịch bản (Human Review)
python main.py --slides test_data/Ex01_Hybrid_Workflow.pptx

# Chạy tự động hoàn toàn
python main.py --slides test_data/Ex01_Hybrid_Workflow.pptx --auto

# Chạy chế độ nháp siêu tốc (Edge-TTS + Render tĩnh)
python main.py --slides test_data/Ex01_Hybrid_Workflow.pptx --auto --draft

# Chạy lại từ đầu (xóa sạch checkpoint cũ)
python main.py --slides test_data/Ex01_Hybrid_Workflow.pptx --reset
```

### 5. Chạy bộ kiểm thử tự động
```bash
python -m unittest tests.test_advanced_suite
```

---

## 📜 Giấy Phép & Tác Quyền
Dự án được xây dựng và chuẩn hóa phục vụ sản xuất nội dung bài giảng thuyết trình số chất lượng cao.
