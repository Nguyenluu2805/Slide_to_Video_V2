"""
Module: script_gen.py
Description: Sinh kịch bản sư phạm tự nhiên, truyền cảm bằng AI (Gemini / OpenAI / Offline Engine)
             kèm kiến trúc thuyết minh 2 phân đoạn chuẩn mực cho Code Demo Remotion.
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

try:
    from . import config
except (ImportError, ValueError):
    import config

SYSTEM_PROMPT = """Bạn là một giáo sư, chuyên gia thuyết trình và giảng viên đại học xuất sắc với phong cách sư phạm đỉnh cao, truyền cảm, cuốn hút và đậm chất văn nói diễn thuyết.
Nhiệm vụ: Chuyển đổi nội dung slide bài giảng thành BÀI GIẢNG ĐIỆN TỬ DIỄN THUYẾT HOÀN CHỈNH (Lời thuyết minh lồng tiếng sống động cho video).

QUY TẮC BẮT BUỘC ĐỂ GIỌNG ĐỌC AI NHẤN NHÁ VÀ TỰ NHIÊN NHƯ NGƯỜI THẬT:
1. VĂN PHONG VĂN NÓI DIỄN THUYẾT: Dùng văn nói tự nhiên, có câu hỏi tương tác ("Vậy... câu hỏi đặt ra là gì?...", "Đúng vậy!", "Các bạn hãy chú ý điểm mấu chốt này...").
2. NGHỆ THUẬT DẤU CÂU TẠO NHỊP ĐIỆU (RẤT QUAN TRỌNG):
   - Sử dụng dấu chấm lửng `...` trước các từ khóa hoặc sau câu hỏi để tạo quãng ngắt lấy hơi kịch tính.
   - Sử dụng dấu gạch ngang `—` để nhấn mạnh ý tương phản hoặc giải thích chốt hạ.
   - Sử dụng dấu chấm than `!` tại các kết luận mang tính đúc kết.
3. TIÊU CHUẨN ĐỈNH CAO CHO PHẦN THỰC HÀNH CODE (CHUYỂN CẢNH TUẦN TỰ):
   - Nếu slide chứa mã nguồn, thuật toán, câu lệnh, ví dụ code hoặc yêu cầu lập trình/thực hành:
     Hãy đặt "has_code_demo": true và cung cấp object "code_demo":
     {
       "filename": "tên file (ví dụ: main.py, quicksort.py, demo.sh, server.js)",
       "language": "python | javascript | typescript | bash | cpp | java",
       "code": "đoạn mã nguồn cô đọng (CHỈ TỪ 4 ĐẾN 7 DÒNG), chuẩn cú pháp và chạy được",
       "terminal_command": "lệnh chạy (ví dụ: python quicksort.py)",
       "terminal_output": "kết quả in ra terminal sống động, chân thực",
       "highlight_lines": [các dòng mấu chốt cần highlight],
       "start_typing_from_line": chỉ số dòng bắt đầu gõ mới (các dòng import/comment trước đó sẽ xuất hiện sẵn),
       "editor_narration": "Lời giảng chi tiết trong lúc gõ code trên VS Code (2-3 câu sư phạm điềm đạm, chỉ rõ từng dòng lệnh trọng tâm đang viết và lý do)",
       "terminal_narration": "Lời giảng chi tiết trong lúc chạy terminal (2-3 câu sư phạm hướng dẫn chạy lệnh và phân tích kết quả đầu ra)",
       "narration": "Gộp cả editor_narration và terminal_narration"
     }
     QUY TẮC PHÂN CHIA LỜI THUYẾT MINH DEMO:
     + editor_narration: Tập trung hoàn toàn vào màn hình soạn thảo VS Code ("Trước hết... các bạn hãy quan sát trên màn hình trình soạn thảo. Tại dòng số 4, chúng ta khai báo... Điểm mấu chốt ở đây là...").
     + terminal_narration: Bắt đầu bằng việc mở terminal và chạy lệnh ("Bây giờ... chúng ta cùng mở terminal và thực thi lệnh... Hãy chú ý kết quả trả về ngay bên dưới... Điều này xác nhận rằng...").
     + Trường "script" của slide sẽ là LỜI DẪN NHẬP SLIDE trước khi chuyển sang màn hình code (1-2 câu ngắn gọn: ví dụ "Tiếp theo... chúng ta cùng chuyển sang phần thực hành: Cài đặt và thực thi... Hãy cùng quan sát trực tiếp trên màn hình lập trình nhé!").
   - Nếu slide chỉ là lý thuyết, giới thiệu tổng quan, khái niệm, kết luận:
     Đặt "has_code_demo": false và viết trường "script" từ 4 - 8 câu hoàn chỉnh (35 - 55 giây).

ĐỊNH DẠNG ĐẦU RA BẮT BUỘC:
Trả về DUY NHẤT một mảng JSON (Array of Objects):
[
  {
    "slide_index": 1,
    "title": "Tiêu đề của slide",
    "has_code_demo": false,
    "script": "Lời giảng lý thuyết..."
  },
  {
    "slide_index": 2,
    "title": "Thực hành thuật toán QuickSort",
    "has_code_demo": true,
    "script": "Sau đây... chúng ta cùng bước vào phần thực hành trọng tâm: Cài đặt và kiểm chứng thuật toán QuickSort trong Python. Hãy cùng theo dõi từng bước triển khai trên môi trường lập trình nhé!",
    "code_demo": {
      "filename": "quicksort.py",
      "language": "python",
      "code": "def quicksort(arr):\\n    if len(arr) <= 1:\\n        return arr\\n    pivot = arr[len(arr) // 2]\\n    left = [x for x in arr if x < pivot]\\n    middle = [x for x in arr if x == pivot]\\n    right = [x for x in arr if x > pivot]\\n    return quicksort(left) + middle + quicksort(right)\\n\\nprint(quicksort([38, 27, 43, 3, 9, 82]))",
      "terminal_command": "python quicksort.py",
      "terminal_output": "[3, 9, 27, 38, 43, 82]\\nProcess finished with exit code 0",
      "highlight_lines": [4, 5, 8],
      "start_typing_from_line": 3,
      "editor_narration": "Trước hết... các bạn hãy cùng quan sát màn hình soạn thảo VS Code. Tại dòng số 4, chúng ta xác định phần tử pivot nằm ngay tại vị trí trung tâm mảng để phân chia dữ liệu. Tiếp theo ở các dòng từ 5 đến 7, kỹ thuật list comprehension được áp dụng để chia mảng thành ba phân vùng: nhỏ hơn, bằng và lớn hơn điểm chốt pivot. Điểm mấu chốt là hàm sau đó gọi đệ quy ở dòng số 8 để hoàn thiện việc sắp xếp tuần tự.",
      "terminal_narration": "Bây giờ... chúng ta cùng chuyển sang cửa sổ terminal và thực thi chương trình với lệnh python quicksort.py. Các bạn hãy nhìn vào kết quả in ra: mảng số nguyên ban đầu đã được sắp xếp tăng dần hoàn hảo với độ phức tạp tối ưu O(n log n)!",
      "narration": "Trước hết... các bạn hãy cùng quan sát màn hình soạn thảo VS Code. Tại dòng số 4, chúng ta xác định phần tử pivot nằm ngay tại vị trí trung tâm mảng để phân chia dữ liệu. Tiếp theo ở các dòng từ 5 đến 7, kỹ thuật list comprehension được áp dụng để chia mảng thành ba phân vùng: nhỏ hơn, bằng và lớn hơn điểm chốt pivot. Điểm mấu chốt là hàm sau đó gọi đệ quy ở dòng số 8 để hoàn thiện việc sắp xếp tuần tự. Bây giờ... chúng ta cùng chuyển sang cửa sổ terminal và thực thi chương trình với lệnh python quicksort.py. Các bạn hãy nhìn vào kết quả in ra: mảng số nguyên ban đầu đã được sắp xếp tăng dần hoàn hảo với độ phức tạp tối ưu O(n log n)!"
    }
  }
]
"""

def split_demo_narration_phases(narration: str) -> Tuple[str, str]:
    """
    Tách lời dẫn demo thành 2 phân đoạn sư phạm:
    Phân đoạn 1 (Editor): Giải thích cấu trúc và mã nguồn trên VS Code.
    Phân đoạn 2 (Terminal): Hướng dẫn chạy lệnh và phân tích kết quả terminal.
    """
    if not narration:
        return ("", "")

    sentences = [s.strip() for s in re.split(r'(?<=[.!?…])\s+', narration) if s.strip()]
    if len(sentences) <= 1:
        return (narration, narration)

    terminal_markers = [
        "bây giờ", "tiếp theo chúng ta cùng mở terminal", "mở terminal",
        "chuyển sang cửa sổ terminal", "chuyển sang terminal", "thực thi lệnh",
        "chạy thử nghiệm", "khi chạy chương trình", "khi thực thi", "chạy lệnh",
        "kết quả trả về", "nhìn vào kết quả"
    ]

    split_idx = -1
    for idx, s in enumerate(sentences[1:], start=1):
        s_lower = s.lower()
        if any(m in s_lower for m in terminal_markers):
            split_idx = idx
            break

    if split_idx == -1:
        split_idx = max(1, len(sentences) // 2)

    editor_text = " ".join(sentences[:split_idx]).strip()
    terminal_text = " ".join(sentences[split_idx:]).strip()
    return (editor_text, terminal_text)


def generate_script_gemini(slides_data: List[Dict[str, Any]], api_key: str) -> List[Dict[str, Any]]:
    """Tạo kịch bản bài giảng bằng Google Gemini API kèm nhận diện Code Demo."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key.strip())
    prompt = f"Hãy đóng vai một giảng viên sư phạm xuất sắc và viết lời giảng chi tiết, truyền cảm cho từng slide dưới đây (nhận diện các slide có thực hành code để sinh demo_code tương ứng):\n\n{json.dumps(slides_data, ensure_ascii=False, indent=2)}"

    models_to_try = [config.GEMINI_MODEL, "gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
    last_err = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=SYSTEM_PROMPT),
                            types.Part.from_text(text=prompt)
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    response_mime_type="application/json"
                )
            )
            data = json.loads(response.text.strip())
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "slides" in data:
                return data["slides"]
            return data
        except Exception as e:
            last_err = e
            continue

    raise last_err or RuntimeError("Không thể kết nối Gemini API.")


def is_code_slide(slide: Dict[str, Any]) -> bool:
    """Nhận diện xem slide có chứa mã nguồn hoặc yêu cầu thực hành lập trình không."""
    title = slide.get("title", "").lower()
    bullets = [b.lower() for b in slide.get("bullet_points", [])]
    notes = slide.get("speaker_notes", "").lower()
    all_text = " ".join([title] + bullets + [notes])

    code_syntax_markers = [
        "def ", "class ", "import ", "return ", "console.log", "print(",
        "function ", "const ", "let ", "public static", "int main",
        "npm ", "pip install", "curl ", "git clone", "```", "/>", "</",
        "docker run", "docker build", "docker ps", "kubectl"
    ]
    if any(marker in all_text for marker in code_syntax_markers):
        return True

    demo_action_phrases = [
        "cài đặt code", "thực hành code", "viết hàm", "chạy chương trình",
        "demo code", "live coding", "mã nguồn minh họa", "thực hành lập trình",
        "demo ·", "thực hành ·", "cài đặt &"
    ]
    if any(phrase in all_text for phrase in demo_action_phrases):
        return True

    for b in bullets:
        if any(tok in b for tok in [" = ", "()", "->", "::"]):
            if any(kw in b for kw in ["quicksort", "sort", "search", "api", "app", "func", "data", "list", "dict", "docker", "container"]):
                return True

    return False


def synthesize_offline_code_demo(slide: Dict[str, Any]) -> Dict[str, Any]:
    """Sinh kịch bản code demo tự động cho chế độ ngoại tuyến (Offline) với kịch bản 2 phân đoạn chuyên sâu."""
    title = slide.get("title", "").strip()
    bullets = slide.get("bullet_points", [])
    combined = (title + " " + " ".join(bullets)).lower()

    if "docker" in combined or "container" in combined or "vm" in combined or "môi trường" in combined:
        filename = "demo.sh"
        language = "bash"
        code = (
            "# 1. Đóng gói ứng dụng vào Container Image\n"
            "docker build -t myapp:2.0 .\n\n"
            "# 2. Chạy ứng dụng trên môi trường độc lập\n"
            "docker run -d -p 8080:8080 --name app_prod myapp:2.0\n\n"
            "# 3. Kiểm tra trạng thái container\n"
            "docker ps"
        )
        cmd = "bash demo.sh"
        output = (
            "Successfully built 8f3c2a1e0b9d\n"
            "Successfully tagged myapp:2.0\n"
            "CONTAINER ID   IMAGE        COMMAND                  STATUS         PORTS\n"
            "c3a1b2d4e5f6   myapp:2.0    \"java -jar app.jar\"     Up 5 seconds   0.0.0.0:8080->8080/tcp"
        )
        editor_narr = (
            "Trước hết... các bạn hãy cùng quan sát màn hình soạn thảo VS Code. "
            "Tại dòng số 2, chúng ta sử dụng lệnh docker build để đóng gói toàn bộ mã nguồn cùng môi trường runtime vào một Image duy nhất. "
            "Tiếp theo ở dòng số 5, chúng ta khởi chạy container với tham số trừ p để ánh xạ cổng mạng 8080, đảm bảo ứng dụng vận hành độc lập hoàn toàn với máy chủ."
        )
        term_narr = (
            "Bây giờ... chúng ta cùng mở terminal và chạy thử nghiệm file bash demo.sh. "
            "Các bạn hãy quan sát kết quả trả về ngay bên dưới: container đã khởi chạy thành công sau vài giây với trạng thái Up và cổng kết nối chính xác. "
            "Điều này chứng minh ứng dụng của chúng ta giờ đây có thể chạy mượt mà ở bất kỳ môi trường nào mà không bao giờ gặp lỗi lệch phiên bản nữa!"
        )
        highlights = [2, 5]
        start_typing = 4
    elif "quicksort" in combined or "sắp xếp" in combined:
        filename = "quicksort.py"
        language = "python"
        code = (
            "def quicksort(arr):\n"
            "    if len(arr) <= 1:\n"
            "        return arr\n"
            "    pivot = arr[len(arr) // 2]\n"
            "    left = [x for x in arr if x < pivot]\n"
            "    middle = [x for x in arr if x == pivot]\n"
            "    right = [x for x in arr if x > pivot]\n"
            "    return quicksort(left) + middle + quicksort(right)\n\n"
            "numbers = [38, 27, 43, 3, 9, 82]\n"
            "print('Sorted:', quicksort(numbers))"
        )
        cmd = "python quicksort.py"
        output = "Sorted: [3, 9, 27, 38, 43, 82]\nProcess finished with exit code 0"
        editor_narr = (
            "Trước hết... chúng ta cùng quan sát quá trình cài đặt thuật toán QuickSort trên màn hình trình soạn thảo. "
            "Tại dòng số 4, chúng ta xác định phần tử pivot nằm ngay tại vị trí trung tâm mảng để phân chia dữ liệu. "
            "Tiếp theo ở các dòng từ 5 đến 7, kỹ thuật list comprehension được áp dụng để chia mảng thành ba phân vùng: nhỏ hơn, bằng và lớn hơn điểm chốt pivot. "
            "Hàm sau đó gọi đệ quy ở dòng số 8 để hoàn thiện việc sắp xếp tuần tự."
        )
        term_narr = (
            "Bây giờ... chúng ta cùng chuyển sang cửa sổ terminal và thực thi chương trình với lệnh python quicksort.py. "
            "Các bạn hãy nhìn vào kết quả in ra: mảng số nguyên ban đầu đã được sắp xếp tăng dần hoàn hảo với độ phức tạp tối ưu O(n log n)!"
        )
        highlights = [4, 5, 8]
        start_typing = 3
    elif "api" in combined or "fastapi" in combined or "flask" in combined:
        filename = "main.py"
        language = "python"
        code = (
            "from fastapi import FastAPI\n\n"
            "app = FastAPI(title='AI Video Studio')\n\n"
            "@app.get('/status')\n"
            "def check_status():\n"
            "    return {'status': 'healthy', 'gpu_accelerated': True}\n\n"
            "if __name__ == '__main__':\n"
            "    import uvicorn\n"
            "    uvicorn.run(app, host='0.0.0.0', port=8000)"
        )
        cmd = "uvicorn main:app --reload"
        output = "INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)\nINFO:     Application startup complete."
        editor_narr = (
            "Đầu tiên... chúng ta cùng quan sát cấu trúc mã nguồn API trên VS Code. "
            "Tại dòng số 3, chúng ta khởi tạo instance ứng dụng FastAPI tiêu chuẩn. "
            "Tiếp theo ở dòng số 6, chúng ta định nghĩa một endpoint get kiểm tra trạng thái dịch vụ và trả về dữ liệu định dạng JSON."
        )
        term_narr = (
            "Bây giờ... chúng ta cùng mở terminal và khởi động server bằng lệnh uvicorn main:app. "
            "Kết quả terminal hiển thị ứng dụng đã sẵn sàng phục vụ tại cổng 8000 với hiệu năng cao và độ trễ cực thấp!"
        )
        highlights = [3, 6, 7]
        start_typing = 4
    else:
        filename = "demo_array.py"
        language = "python"
        code = (
            "import numpy as np\n\n"
            "# 1. Khởi tạo mảng số nguyên\n"
            "arr = np.array([10, 20, 30, 40, 50])\n"
            "print('Mảng ban đầu:', arr)\n\n"
            "# 2. Phép toán vector hóa siêu tốc\n"
            "result = arr * 2\n"
            "print('Kết quả nhân đôi:', result)"
        )
        cmd = "python demo_array.py"
        output = "Mảng ban đầu: [10 20 30 40 50]\nKết quả nhân đôi: [ 20  40  60  80 100]\nProcess finished with exit code 0"
        editor_narr = (
            "Đầu tiên... các bạn hãy quan sát đoạn mã nguồn trên màn hình VS Code. "
            "Tại dòng số 4, chúng ta sử dụng thư viện NumPy để khởi tạo một mảng số nguyên đồng nhất kiểu dữ liệu. "
            "Tiếp theo ở dòng số 8, thay vì dùng vòng lặp for truyền thống, chúng ta nhân đôi toàn bộ phần tử bằng phép toán vector hóa siêu tốc."
        )
        term_narr = (
            "Bây giờ... chúng ta cùng mở terminal và chạy thử nghiệm chương trình với lệnh python demo_array.py. "
            "Các bạn hãy quan sát kết quả trả về ngay bên dưới: mảng mới đã được tính toán đồng loạt và in ra màn hình chính xác tuyệt đối. "
            "Cách tiếp cận này giúp tối ưu hóa bộ nhớ đệm và tăng tốc độ xử lý dữ liệu lên gấp hàng chục lần!"
        )
        highlights = [4, 8]
        start_typing = 4

    return {
        "filename": filename,
        "language": language,
        "code": code,
        "terminal_command": cmd,
        "terminal_output": output,
        "highlight_lines": highlights,
        "start_typing_from_line": start_typing,
        "editor_narration": editor_narr,
        "terminal_narration": term_narr,
        "narration": f"{editor_narr} {term_narr}".strip()
    }


def generate_rich_offline_script(slides_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bộ tạo kịch bản sư phạm súc tích, tự nhiên và chuyên nghiệp khi Offline."""
    scripts = []
    total = len(slides_data)

    for s in slides_data:
        idx = s["slide_index"]
        title = s.get("title", f"Nội dung số {idx}").strip()
        has_demo = is_code_slide(s)
        code_demo_data = None

        if has_demo:
            code_demo_data = synthesize_offline_code_demo(s)
            script_text = (
                f"Tiếp theo... chúng ta cùng chuyển sang phần thực hành trọng tâm: {title}. "
                f"Các bạn hãy quan sát các bước cài đặt và chạy thử nghiệm chương trình trực tiếp trên màn hình ngay sau đây nhé!"
            )
        else:
            paragraphs = []
            if idx == 1:
                paragraphs.append(f"Chào mừng tất cả các bạn... đã đến với bài học hôm nay! Trong bài giảng này, chúng ta sẽ cùng nhau tìm hiểu một chủ đề rất quan trọng: {title}.")
            elif idx == total:
                paragraphs.append(f"Tổng kết lại nội dung về {title}... chúng ta đã cùng nhau làm rõ các kiến thức cốt lõi nhất.")
            else:
                paragraphs.append(f"Bây giờ, chúng ta sẽ cùng phân tích sâu hơn về {title}.")

            bullets = s.get("bullet_points", [])
            for b in bullets:
                cleaned = re.sub(r'^[\d\.\-\•\*\#\_\✓\⚡\◈\Σ\s]+', '', b).strip()
                if len(cleaned) > 5:
                    paragraphs.append(f"Điểm đáng chú ý ở đây là: {cleaned}... Điều này đóng vai trò quyết định đến hiệu quả vận hành của toàn bộ hệ thống.")

            if idx == total:
                paragraphs.append("Hi vọng bài học đã mang lại nhiều kiến thức bổ ích. Cảm ơn các bạn đã chú ý lắng nghe và chúc các bạn học tập thật tốt!")
            else:
                paragraphs.append("Các bạn hãy ghi nhớ điểm mấu chốt này... trước khi chúng ta tiếp tục sang slide kế tiếp nhé!")

            script_text = " ".join(paragraphs)

        item = {
            "slide_index": idx,
            "title": title,
            "has_code_demo": has_demo,
            "script": script_text
        }
        if has_demo and code_demo_data:
            item["code_demo"] = code_demo_data

        scripts.append(item)

    return scripts


def post_process_code_demos(scripts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Đảm bảo mọi slide có code demo đều có đầy đủ editor_narration và terminal_narration chuẩn xác."""
    for item in scripts:
        if item.get("has_code_demo") and item.get("code_demo"):
            cd = item["code_demo"]
            ed = cd.get("editor_narration", "").strip()
            tm = cd.get("terminal_narration", "").strip()
            full_narr = cd.get("narration", "").strip()

            if not ed or not tm:
                e_split, t_split = split_demo_narration_phases(full_narr or ed or tm)
                ed = ed or e_split
                tm = tm or t_split

            cd["editor_narration"] = ed
            cd["terminal_narration"] = tm
            cd["narration"] = f"{ed} {tm}".strip()
    return scripts


def run_script_generator(input_data: List[Dict[str, Any]] = None, gemini_api_key: str = None) -> List[Dict[str, Any]]:
    """Hàm thực thi chính cho Bước 2: Tạo Kịch Bản Sư Phạm"""
    if input_data is None:
        extracted_file = config.WORKSPACE_DIR / "extracted_data.json"
        if not extracted_file.exists():
            raise FileNotFoundError(f"Chưa có file {extracted_file}. Vui lòng chạy Bước 1 trước.")
        with open(extracted_file, "r", encoding="utf-8") as f:
            input_data = json.load(f)

    api_key = gemini_api_key or config.GEMINI_API_KEY
    scripts = None

    if api_key:
        try:
            scripts = generate_script_gemini(input_data, api_key)
        except Exception as e:
            print(f"[!] Gemini API Error: {e}. Fallback to Offline script engine.")

    if scripts is None:
        scripts = generate_rich_offline_script(input_data)

    scripts = post_process_code_demos(scripts)

    output_script_file = config.WORKSPACE_DIR / "script.json"
    with open(output_script_file, "w", encoding="utf-8") as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)

    return scripts

run_step2 = run_script_generator