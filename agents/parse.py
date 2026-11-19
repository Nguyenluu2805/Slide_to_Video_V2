"""
agents/parse.py - Module trích xuất và xuất hình ảnh slide thật cho V2
Ưu tiên 1: PowerPoint COM (Windows)
Ưu tiên 2: LibreOffice headless
Tuyệt đối không vẽ card PIL giả.
"""

import os
import sys
import json
import shutil
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from pptx import Presentation

import config

logger = logging.getLogger("agents.parse")


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
    if not img_path.exists():
        return {}

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
            "Chỉ trả về JSON thuần túy."
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


def parse_presentation(pptx_path: Path, output_slides_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Phân tích file presentation .pptx và xuất hình ảnh slide thật.
    Trả về danh sách đối tượng slide tuân thủ Single Source of Truth schema V2.
    Thêm validation cảnh báo cho slide trống hoặc thiếu nội dung.
    """
    if not pptx_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file presentation: {pptx_path}")

    target_slides_dir = output_slides_dir or config.SLIDES_DIR
    target_slides_dir.mkdir(parents=True, exist_ok=True)

    # Xuất ảnh slide thật
    images_map = export_presentation_slides(pptx_path, target_slides_dir)

    prs = Presentation(str(pptx_path.resolve()))
    slides_data = []

    for idx, slide in enumerate(prs.slides, start=1):
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
            title = f"Slide {idx}"

        # 2. Trích xuất Speaker Notes
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            extracted_notes = slide.notes_slide.notes_text_frame.text.strip()
            if "Click to add notes" not in extracted_notes:
                notes = extracted_notes

        # 3. Validation: Kiểm tra slide rỗng / thiếu nội dung
        has_bullets = len(bullets) > 0
        has_notes = len(notes) > 0
        is_generic_title = title == f"Slide {idx}"

        img_path = images_map.get(idx)
        if not has_bullets and not has_notes and is_generic_title and img_path and img_path.exists():
            ocr_data = ocr_slide_with_vision(img_path)
            if ocr_data.get("title"):
                title = ocr_data["title"]
                is_generic_title = False
            if ocr_data.get("bullets"):
                bullets = ocr_data["bullets"]
                has_bullets = True
            if has_bullets or not is_generic_title:
                warn = f"Slide {idx} được trích xuất nội dung từ ảnh đồ họa bằng Gemini Vision OCR"
                warnings.append(warn)
                logger.info(warn)

        if not has_bullets and not has_notes and is_generic_title:
            warn = f"Slide {idx} hoàn toàn trống (không có title, bullets, notes)"
            warnings.append(warn)
            logger.warning(warn)
        elif not has_notes:
            warn = f"Slide {idx} không có speaker notes"
            warnings.append(warn)
            logger.info(warn)

        img_rel_path = str(img_path.relative_to(config.PROJECT_ROOT)) if img_path else f"output/slides/slide_{idx:03d}.png"

        slide_entry = {
            "slide": {
                "id": idx,
                "title": title,
                "bullets": bullets,
                "notes": notes,
                "image": img_rel_path,
                "warnings": warnings
            },
            "scene": {
                "slide_id": idx,
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
