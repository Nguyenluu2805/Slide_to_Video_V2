"""
agents/parse.py - Module trích xuất và xuất hình ảnh slide thật cho V2 (Hỗ trợ PPTX và PDF)
Ưu tiên 1: PowerPoint COM (Windows)
Ưu tiên 2: LibreOffice headless
PDF: PyMuPDF (fitz) - Render canvas 1920x1080 chuẩn không méo + trích xuất văn bản blocks
Tuyệt đối không vẽ card PIL giả.
"""

import os
import sys
import re
import json
import shutil
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from pptx import Presentation

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

import config

logger = logging.getLogger("agents.parse")


def parse_page_range(range_str: Optional[str], total_pages: int) -> List[int]:
    """
    Phân tích chuỗi phạm vi trang (Ví dụ: '1-3', '2', '1,3,5') thành danh sách chỉ số 0-based.
    Nếu range_str là None hoặc rỗng, trả về toàn bộ [0, 1, ..., total_pages - 1].
    """
    if not range_str or not str(range_str).strip():
        return list(range(total_pages))

    indices = []
    parts = str(range_str).strip().split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            s_str, e_str = part.split('-', 1)
            try:
                start = int(s_str.strip())
                end = int(e_str.strip())
                for p in range(start, end + 1):
                    if 1 <= p <= total_pages:
                        idx = p - 1
                        if idx not in indices:
                            indices.append(idx)
            except ValueError:
                pass
        else:
            try:
                p = int(part)
                if 1 <= p <= total_pages:
                    idx = p - 1
                    if idx not in indices:
                        indices.append(idx)
            except ValueError:
                pass

    return indices if indices else list(range(total_pages))


def is_page_number_or_noise(line: str) -> bool:
    """Nhận diện dòng là số trang đơn lẻ hoặc ký tự nhiễu."""
    line_clean = line.strip()
    if not line_clean:
        return True
    # Khớp các dạng: "1", "1/6", "Trang 1", "Trang 1/6", "Page 1 of 6", "- 1 -", "1 | 6"
    if re.match(r'^(?:[-–—\s]*)?(?:trang|page)?\s*\d+\s*(?:[/|\-–—\\]|\bof\b|\btrên\b)?\s*\d*(?:[-–—\s]*)?$', line_clean, re.IGNORECASE):
        return True
    return False


def split_long_bullet(text: str, max_chars: int = 120) -> List[str]:
    """Tách bullet dài > 120 ký tự theo dấu câu thành các bullet ngắn, không cắt giữa từ."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    # 1. Thử tách theo dấu kết câu: . ! ? ;
    parts = re.split(r'(?<=[.!?;\n])\s+', text)
    if len(parts) > 1:
        result = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if len(p) > max_chars:
                result.extend(split_long_bullet(p, max_chars))
            else:
                result.append(p)
        return result

    # 2. Thử tách theo dấu phẩy / hai chấm: , :
    parts = re.split(r'(?<=[,:])\s+', text)
    if len(parts) > 1:
        result = []
        curr = ""
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if not curr:
                curr = p
            elif len(curr) + len(p) + 2 <= max_chars:
                curr += ", " + p
            else:
                result.append(curr)
                curr = p
        if curr:
            result.append(curr)
        return result

    # 3. Tách theo từ nếu không có dấu câu
    words = text.split()
    result = []
    curr = []
    curr_len = 0
    for w in words:
        if curr_len + len(w) + (1 if curr else 0) <= max_chars:
            curr.append(w)
            curr_len += len(w) + (1 if len(curr) > 1 else 0)
        else:
            if curr:
                result.append(" ".join(curr))
            curr = [w]
            curr_len = len(w)
    if curr:
        result.append(" ".join(curr))
    return result


def render_pdf_page_to_1080p(page, out_img_path: Path) -> Path:
    """
    Render một trang PDF lên canvas 1920x1080 chuẩn không stretch, không méo chữ:
    - Nếu là 16:9 ngang: vừa khít 1920x1080.
    - Nếu là khổ khác (A4 dọc, 4:3,...): scale giữ nguyên tỉ lệ gốc, căn giữa,
      phần thừa lấp nền trắng (không crop chữ, không stretch méo).
    """
    from PIL import Image
    import io

    rect = page.rect
    w, h = rect.width, rect.height
    if w <= 0 or h <= 0:
        raise ValueError(f"Kích thước trang PDF không hợp lệ: {w}x{h}")

    target_w = config.VIDEO_WIDTH   # 1920
    target_h = config.VIDEO_HEIGHT  # 1080

    scale = min(target_w / w, target_h / h)
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, alpha=False)

    img = Image.open(io.BytesIO(pix.tobytes("png")))
    canvas = Image.new("RGB", (target_w, target_h), (255, 255, 255))

    paste_x = (target_w - img.width) // 2
    paste_y = (target_h - img.height) // 2
    canvas.paste(img, (paste_x, paste_y))

    out_img_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(out_img_path.resolve()), "PNG")
    return out_img_path


def parse_pdf(
    pdf_path: Path,
    output_slides_dir: Optional[Path] = None,
    page_range: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Phân tích file tài liệu/bài giảng PDF và xuất hình ảnh 1080p chuẩn canvas:
    - Sử dụng PyMuPDF (fitz) làm thư viện chính (render ảnh + trích chữ).
    - Canvas 1920x1080: Giữ nguyên tỉ lệ, không stretch, không crop chữ (A4/dọc thì căn giữa, lấp nền trắng).
    - Trích xuất chữ: blocks đọc từ trên xuống dưới, trái qua phải.
      + title = dòng chữ đầu tiên có nội dung.
      + bullets = các dòng còn lại (dòng > 120 ký tự thì tách theo dấu câu).
      + notes = "", uses_notes = False.
      + Lọc bỏ số trang đơn lẻ (1, Trang 1/6, Page 1 of 6,...).
    - Scan PDF / ảnh không chữ (< 20 ký tự): dùng ocr_slide_with_vision(img_path) -> source="pdf_ocr".
    - Schema trả về tương thích 100% với Single Source of Truth schema V2.
    """
    if fitz is None:
        raise ImportError(
            "Thư viện PyMuPDF chưa được cài đặt!\n"
            "Vui lòng cài đặt bằng lệnh: pip install 'PyMuPDF>=1.24'"
        )

    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file PDF tại: {pdf_path}")

    target_slides_dir = output_slides_dir or config.SLIDES_DIR
    target_slides_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = fitz.open(str(pdf_path.resolve()))
    except Exception as e:
        raise RuntimeError(f"Không thể mở file PDF {pdf_path.name}: {e}")

    total_pages = len(doc)
    logger.info(f"Mở file PDF: {pdf_path.name} ({total_pages} trang)")
    print(f"[*] Mở file PDF: {pdf_path.name} (Tổng cộng: {total_pages} trang)")

    if total_pages == 0:
        doc.close()
        raise ValueError(f"File PDF rỗng (0 trang): {pdf_path.name}")

    if total_pages > 50:
        msg = f"CẢNH BÁO: File PDF có {total_pages} trang (> 50 trang). Video bài giảng xuất ra sẽ rất dài!"
        print(f"[!] {msg}")
        logger.warning(msg)

    selected_indices = parse_page_range(page_range, total_pages)
    if not selected_indices:
        selected_indices = list(range(total_pages))

    slides_data = []
    has_any_content = False

    for out_idx, page_idx in enumerate(selected_indices, start=1):
        page = doc[page_idx]
        out_img = target_slides_dir / f"slide_{out_idx:03d}.png"

        # 1. Render trang PDF lên canvas 1920x1080 (không stretch, không méo)
        render_pdf_page_to_1080p(page, out_img)

        # 2. Trích xuất text blocks từ PDF
        title = ""
        bullets = []
        warnings = []
        source = "pdf_text"

        blocks = page.get_text("blocks")
        # Lọc blocks văn bản (block_type == 0) và sắp xếp theo thứ tự đọc (y0, x0)
        text_blocks = [b for b in blocks if len(b) >= 7 and b[6] == 0 and b[4].strip()]
        text_blocks.sort(key=lambda b: (round(b[1], 1), round(b[0], 1)))

        raw_lines = []
        for b in text_blocks:
            # Tách các mục con nếu có dấu bullet hoặc số thứ tự đầu dòng
            sub_items = re.split(r'\n(?=[•\-\*\+\u2022\u25cf\u25cb\u25aa]|\d+\.\s+)', b[4])
            for it in sub_items:
                # Gộp các dòng bị ngắt giữa chừng trong cùng một paragraph thành dòng liền mạch
                it_clean = re.sub(r'\s+', ' ', it).strip()
                if not it_clean:
                    continue
                # Bỏ số trang đơn lẻ & ký tự nhiễu
                if is_page_number_or_noise(it_clean):
                    continue
                # Làm sạch ký tự đầu dòng nếu có bullet symbol
                it_cleaned = re.sub(r'^[•\-\*\+\u2022\u25cf\u25cb\u25aa\s]+\s*', '', it_clean)
                if it_cleaned and not is_page_number_or_noise(it_cleaned):
                    raw_lines.append(it_cleaned)

        total_extracted_chars = sum(len(ln) for ln in raw_lines)

        # 3. Xử lý trường hợp PDF scan / ít chữ (< 20 ký tự) -> Tái dùng Gemini Vision OCR
        if total_extracted_chars < 20:
            logger.info(f"Trang {out_idx} (Page {page_idx+1}) trích xuất được ít hơn 20 ký tự ({total_extracted_chars} ký tự). Gọi Vision OCR...")
            ocr_data = ocr_slide_with_vision(out_img)
            if ocr_data.get("title") or ocr_data.get("bullets"):
                title = (ocr_data.get("title") or "").strip()
                ocr_bullets = ocr_data.get("bullets", [])
                if isinstance(ocr_bullets, list):
                    bullets = [str(b).strip() for b in ocr_bullets if str(b).strip()]
                elif isinstance(ocr_bullets, str):
                    bullets = [ocr_bullets.strip()]
                source = "pdf_ocr"
                warnings.append(f"Trang {out_idx} được trích xuất nội dung từ ảnh bằng Gemini Vision OCR (pdf_ocr)")
            else:
                warn = f"Trang {out_idx} không có nội dung chữ hoặc hình ảnh không thể nhận diện"
                warnings.append(warn)
                logger.warning(warn)
        else:
            # Dòng đầu tiên là tiêu đề (title)
            title = raw_lines[0]
            # Các dòng còn lại là bullets
            for ln in raw_lines[1:]:
                # Tách dòng dài > 120 ký tự
                if len(ln) > 120:
                    split_bullets = split_long_bullet(ln, max_chars=120)
                    for sb in split_bullets:
                        if sb and sb not in bullets:
                            bullets.append(sb)
                else:
                    if ln not in bullets:
                        bullets.append(ln)

        if not title:
            if bullets:
                title = bullets[0]
                bullets = bullets[1:]
            else:
                title = f"Trang {out_idx}"

        if (title and title != f"Trang {out_idx}") or bullets:
            has_any_content = True

        img_rel_path = str(out_img.relative_to(config.PROJECT_ROOT))

        slide_entry = {
            "slide": {
                "id": out_idx,
                "title": title,
                "bullets": bullets,
                "notes": "",
                "image": img_rel_path,
                "warnings": warnings,
                "source": source
            },
            "scene": {
                "slide_id": out_idx,
                "script": "",
                "word_count": 0,
                "duration_sec": 0.0,
                "grounding": {
                    "uses_notes": False,
                    "bullets_covered": [],
                    "bullets_missed": [],
                    "invented_claims": []
                },
                "audio_file": "",
                "visual": img_rel_path,
                "state": "parsed"
            }
        }
        slides_data.append(slide_entry)

    doc.close()

    # Kiểm tra: nếu TẤT CẢ các trang đều rỗng thì dừng và báo lỗi rõ
    if not has_any_content and len(slides_data) > 0:
        raise RuntimeError(
            f"File PDF không có nội dung chữ: {pdf_path.name}. "
            "Tất cả các trang đều rỗng hoặc không trích xuất được văn bản / OCR."
        )

    logger.info(f"Đã phân tích xong {len(slides_data)} trang từ PDF: {pdf_path.name}")
    print(f"[+] Trích xuất hoàn tất {len(slides_data)} trang từ file PDF {pdf_path.name}.")
    return slides_data


def export_slides_powerpoint_com(pptx_path: Path, output_dir: Path) -> Dict[int, Path]:
    """Ưu tiên 1: Xuất slide thật bằng Microsoft PowerPoint COM trên Windows."""
    images_map = {}
    try:
        import win32com.client
        import pythoncom

        pythoncom.CoInitialize()
        ppt_app = win32com.client.Dispatch("PowerPoint.Application")
        abs_pptx = str(pptx_path.resolve())

        # Mở presentation ở chế độ ẩn / ReadOnly
        presentation = ppt_app.Presentations.Open(abs_pptx, ReadOnly=1, Untitled=0, WithWindow=0)
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, slide in enumerate(presentation.Slides, start=1):
            out_img = output_dir / f"slide_{i:03d}.png"
            slide.Export(str(out_img.resolve()), "PNG", config.VIDEO_WIDTH, config.VIDEO_HEIGHT)
            if out_img.exists() and out_img.stat().st_size > 0:
                images_map[i] = out_img

        presentation.Close()
        ppt_app.Quit()
        pythoncom.CoUninitialize()
        logger.info(f"PowerPoint COM: Đã xuất {len(images_map)} slide thành công.")
        return images_map
    except Exception as e:
        logger.warning(f"PowerPoint COM không khả dụng hoặc gặp lỗi: {e}")
        return {}


def find_libreoffice_bin() -> Optional[str]:
    """Tìm đường dẫn thực thi LibreOffice soffice."""
    bin_cmd = shutil.which("soffice") or shutil.which("libreoffice")
    if bin_cmd:
        return bin_cmd

    # Tìm các đường dẫn mặc định phổ biến trên Windows
    common_paths = [
        Path("C:/Program Files/LibreOffice/program/soffice.exe"),
        Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
    ]
    for p in common_paths:
        if p.exists():
            return str(p)
    return None


def export_slides_libreoffice(pptx_path: Path, output_dir: Path) -> Dict[int, Path]:
    """Ưu tiên 2: Xuất slide bằng LibreOffice headless convert-to pdf rồi chuyển sang PNG."""
    soffice = find_libreoffice_bin()
    if not soffice:
        logger.warning("Không tìm thấy LibreOffice (soffice) trên hệ thống.")
        return {}

    images_map = {}
    tmp_pdf_dir = output_dir / "_tmp_pdf"
    tmp_pdf_dir.mkdir(parents=True, exist_ok=True)

    try:
        abs_pptx = str(pptx_path.resolve())
        cmd = [
            soffice, "--headless", "--convert-to", "pdf",
            "--outdir", str(tmp_pdf_dir.resolve()), abs_pptx
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        pdf_file = tmp_pdf_dir / f"{pptx_path.stem}.pdf"
        if res.returncode != 0 or not pdf_file.exists():
            logger.warning(f"LibreOffice convert-to PDF thất bại: {res.stderr}")
            return {}

        # Dùng pdftoppm nếu có, hoặc ffmpeg để chuyển PDF thành PNG 1920x1080
        pdftoppm = shutil.which("pdftoppm")
        if pdftoppm:
            prefix = str((output_dir / "slide").resolve())
            cmd_ppm = [pdftoppm, "-png", "-r", "150", str(pdf_file.resolve()), prefix]
            subprocess.run(cmd_ppm, check=True)
            # Chuẩn hóa tên file slide-1.png -> slide_001.png
            for gen_f in sorted(output_dir.glob("slide-*.png")):
                try:
                    num_str = gen_f.stem.replace("slide-", "")
                    num = int(num_str)
                    target = output_dir / f"slide_{num:03d}.png"
                    gen_f.rename(target)
                    images_map[num] = target
                except Exception:
                    pass
        else:
            # Dùng ffmpeg xuất từng trang PDF sang PNG
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", str(pdf_file.resolve()),
                "-s", f"{config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}",
                str((output_dir / "slide_%03d.png").resolve())
            ]
            subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
            for gen_f in sorted(output_dir.glob("slide_*.png")):
                try:
                    num = int(gen_f.stem.replace("slide_", ""))
                    images_map[num] = gen_f
                except Exception:
                    pass

        return images_map
    except Exception as e:
        logger.warning(f"Lỗi khi xuất slide bằng LibreOffice: {e}")
        return {}
    finally:
        shutil.rmtree(tmp_pdf_dir, ignore_errors=True)


def export_presentation_slides(pptx_path: Path, output_dir: Path) -> Dict[int, Path]:
    """
    Thực hiện xuất hình ảnh slide thật theo thứ tự ưu tiên:
    1. PowerPoint COM
    2. LibreOffice Headless
    Nếu cả 2 đều không có hoặc lỗi: DỪNG VÀ BÁO LỖI RÕ, không vẽ card giả!
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Thử PowerPoint COM
    logger.info("Đang xuất ảnh slide bằng PowerPoint COM...")
    images_map = export_slides_powerpoint_com(pptx_path, output_dir)
    if images_map:
        return images_map

    # 2. Thử LibreOffice headless
    logger.info("PowerPoint COM không khả dụng, đang thử LibreOffice headless...")
    images_map = export_slides_libreoffice(pptx_path, output_dir)
    if images_map:
        return images_map

    # Cả 2 đều thất bại -> Dừng và báo lỗi rõ ràng theo yêu cầu spec V2
    raise RuntimeError(
        "KHÔNG THỂ XUẤT ẢNH SLIDE THẬT!\n"
        "Vui lòng cài đặt Microsoft PowerPoint (được khuyến nghị trên Windows) "
        "hoặc LibreOffice để xuất ảnh slide chất lượng cao 1920x1080. "
        "Hệ thống V2 không cho phép dùng card PIL giả."
    )


def ocr_slide_with_vision(img_path: Path) -> Dict[str, Any]:
    """Sử dụng Gemini Vision để nhận diện nội dung trên slide đồ họa phẳng."""
    import base64
    import requests
    from PIL import Image

    if not img_path.exists():
        return {}

    # Kiểm tra nhanh: nếu ảnh hoàn toàn đơn sắc (toàn trắng/đen), không tốn token gọi OCR
    try:
        with Image.open(img_path) as im:
            extrema = im.convert("L").getextrema()
            if extrema[0] == extrema[1]:
                return {"title": "", "bullets": []}
    except Exception:
        pass

    try:
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        models = [
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-3-flash-preview",
            "gemini-2.5-flash-lite"
        ]
        api_key = config.GEMINI_API_KEY
        if not api_key:
            return {}

        prompt = (
            "Trích xuất chính xác thông tin từ ảnh slide này dưới dạng JSON:\n"
            "{\n"
            "  \"title\": \"Tiêu đề chính của slide\",\n"
            "  \"bullets\": [\"Nội dung hoặc gạch đầu dòng 1\", \"Nội dung 2\"]\n"
            "}\n"
            "Nếu ảnh slide trống, không có nội dung chữ hoặc hình vẽ, trả về: {\"title\": \"\", \"bullets\": []}.\n"
            "Chỉ trả về JSON thuần túy, tuyệt đối không bịa đặt."
        )

        for m in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/png", "data": b64}}
                    ]
                }],
                "generationConfig": {"responseMimeType": "application/json"}
            }
            resp = requests.post(url, json=payload, timeout=25)
            if resp.status_code == 200:
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(raw)
    except Exception as e:
        logger.warning(f"Lỗi khi chạy Vision OCR cho slide {img_path.name}: {e}")
    return {}


def parse_presentation(
    pptx_path: Path,
    output_slides_dir: Optional[Path] = None,
    page_range: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Phân tích file presentation .pptx và xuất hình ảnh slide thật.
    Trả về danh sách đối tượng slide tuân thủ Single Source of Truth schema V2.
    Hỗ trợ page_range (Ví dụ: '1-2') để chạy kiểm tra nhanh một số slide.
    Thêm validation cảnh báo cho slide trống hoặc thiếu nội dung.
    """
    if not pptx_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file presentation: {pptx_path}")

    target_slides_dir = output_slides_dir or config.SLIDES_DIR
    target_slides_dir.mkdir(parents=True, exist_ok=True)

    # Xuất ảnh slide thật
    images_map = export_presentation_slides(pptx_path, target_slides_dir)

    prs = Presentation(str(pptx_path.resolve()))
    total_slides = len(prs.slides)
    selected_indices = parse_page_range(page_range, total_slides)
    slides_data = []

    for out_idx, orig_slide_idx in enumerate(selected_indices, start=1):
        slide = prs.slides[orig_slide_idx]
        orig_slide_num = orig_slide_idx + 1

        title = ""
        bullets = []
        notes = ""
        warnings = []

        # 1. Trích xuất Text & Tables
        for shape in slide.shapes:
            if shape.has_text_frame:
                tf = shape.text_frame
                for paragraph in tf.paragraphs:
                    line_text = paragraph.text.strip()
                    if not line_text:
                        continue

                    # Xác định shape tiêu đề
                    is_title_shape = False
                    try:
                        if shape == slide.shapes.title:
                            is_title_shape = True
                        elif getattr(shape, "is_placeholder", False):
                            if shape.placeholder_format.idx in [0, 1] and not title:
                                is_title_shape = True
                    except Exception:
                        pass

                    if is_title_shape:
                        if not title:
                            title = line_text
                        else:
                            title += " - " + line_text
                    else:
                        if line_text not in bullets:
                            bullets.append(line_text)

            if shape.has_table:
                for row in shape.table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        bullets.append(f"Bảng dữ liệu: {row_text}")

        # Nếu chưa tìm thấy title từ shape title, dùng dòng đầu tiên của bullets
        if not title and bullets:
            title = bullets[0]
            bullets = bullets[1:]
        elif not title:
            title = f"Slide {out_idx}"

        # 2. Trích xuất Speaker Notes
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            extracted_notes = slide.notes_slide.notes_text_frame.text.strip()
            if "Click to add notes" not in extracted_notes:
                notes = extracted_notes

        # 3. Validation: Kiểm tra slide rỗng / thiếu nội dung
        has_bullets = len(bullets) > 0
        has_notes = len(notes) > 0
        is_generic_title = title == f"Slide {out_idx}"

        img_path = images_map.get(orig_slide_num)
        if not has_bullets and not has_notes and is_generic_title and img_path and img_path.exists():
            ocr_data = ocr_slide_with_vision(img_path)
            if ocr_data.get("title"):
                title = ocr_data["title"]
                is_generic_title = False
            if ocr_data.get("bullets"):
                bullets = ocr_data["bullets"]
                has_bullets = True
            if has_bullets or not is_generic_title:
                warn = f"Slide {out_idx} được trích xuất nội dung từ ảnh đồ họa bằng Gemini Vision OCR"
                warnings.append(warn)
                logger.info(warn)

        if not has_bullets and not has_notes and is_generic_title:
            warn = f"Slide {out_idx} hoàn toàn trống (không có title, bullets, notes)"
            warnings.append(warn)
            logger.warning(warn)
        elif not has_notes:
            warn = f"Slide {out_idx} không có speaker notes"
            warnings.append(warn)
            logger.info(warn)

        img_rel_path = str(img_path.relative_to(config.PROJECT_ROOT)) if img_path else f"output/slides/slide_{out_idx:03d}.png"

        slide_entry = {
            "slide": {
                "id": out_idx,
                "title": title,
                "bullets": bullets,
                "notes": notes,
                "image": img_rel_path,
                "warnings": warnings,
                "source": "pptx"
            },
            "scene": {
                "slide_id": out_idx,
                "script": "",
                "word_count": 0,
                "duration_sec": 0.0,
                "grounding": {
                    "uses_notes": bool(notes),
                    "bullets_covered": [],
                    "bullets_missed": [],
                    "invented_claims": []
                },
                "audio_file": "",
                "visual": img_rel_path,
                "state": "parsed"
            }
        }
        slides_data.append(slide_entry)

    logger.info(f"Đã phân tích xong {len(slides_data)} slides từ {pptx_path.name}")
    return slides_data
