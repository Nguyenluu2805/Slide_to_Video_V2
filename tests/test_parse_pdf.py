"""
tests/test_parse_pdf.py - Bộ kiểm thử tự động cho tính năng nhận diện & trích xuất PDF
Kiểm tra cấu trúc schema, kích thước ảnh 1920x1080, trích xuất text/bullets, từ chối định dạng sai.
"""

import sys
import pytest
from pathlib import Path
from PIL import Image

# Thêm thư mục gốc dự án vào sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agents.parse import parse_pdf, parse_presentation


def ensure_test_pdf() -> Path:
    """Đảm bảo file test_data/Ex01_Hybrid_Workflow.pdf sẵn sàng để kiểm thử."""
    pdf_path = config.PROJECT_ROOT / "test_data" / "Ex01_Hybrid_Workflow.pdf"
    if pdf_path.exists() and pdf_path.stat().st_size > 1000:
        return pdf_path

    pptx_path = config.PROJECT_ROOT / "test_data" / "Ex01_Hybrid_Workflow.pptx"
    assert pptx_path.exists(), "Thiếu file PPTX gốc để tạo PDF test!"

    # Thử convert qua PowerPoint COM
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        ppt_app = win32com.client.Dispatch("PowerPoint.Application")
        pres = ppt_app.Presentations.Open(str(pptx_path.resolve()), ReadOnly=1, Untitled=0, WithWindow=0)
        pres.SaveAs(str(pdf_path.resolve()), 32)  # ppSaveAsPDF = 32
        pres.Close()
        ppt_app.Quit()
        pythoncom.CoUninitialize()
    except Exception as e:
        pytest.skip(f"Không thể tạo PDF test từ PPTX trên môi trường này: {e}")

    return pdf_path


def test_parse_pdf_structure_and_dimensions():
    """
    Test 1: Parse PDF Ex01 -> 6 trang, ảnh 1920x1080, title không rỗng,
    bullets không rỗng, notes == '', uses_notes == False.
    """
    pdf_path = ensure_test_pdf()
    slides = parse_pdf(pdf_path, output_slides_dir=config.SLIDES_DIR)

    assert len(slides) == 6, f"Mong đợi 6 trang PDF, nhận được {len(slides)}"

    for s in slides:
        sl = s["slide"]
        sc = s["scene"]

        # 1. Kiểm tra ID và Title
        assert sl["id"] > 0, f"Slide ID không hợp lệ: {sl['id']}"
        assert bool(sl["title"].strip()), f"Slide {sl['id']} có title rỗng!"

        # 2. Kiểm tra Bullets
        assert len(sl["bullets"]) > 0, f"Slide {sl['id']} không có bullets!"

        # 3. Kiểm tra Notes và uses_notes theo chuẩn PDF
        assert sl["notes"] == "", f"Slide {sl['id']} không được có speaker notes!"
        assert sc["grounding"]["uses_notes"] is False, f"Slide {sl['id']} uses_notes phải là False!"
        assert sl.get("source") in ["pdf_text", "pdf_ocr"], f"Nguồn không hợp lệ: {sl.get('source')}"

        # 4. Kiểm tra ảnh slide thật 1920x1080
        img_path = config.PROJECT_ROOT / sl["image"]
        assert img_path.exists(), f"Không tìm thấy ảnh slide tại: {img_path}"
        with Image.open(img_path) as im:
            assert im.size == (1920, 1080), f"Ảnh slide kích thước sai: {im.size}, mong đợi (1920, 1080)"


def test_parse_pdf_content_matches_keywords():
    """
    Test 2: Assert chữ trích được khớp với slide gốc, ít nhất 1 bullet/trang
    chứa từ khóa cốt lõi của slide đó.
    """
    pdf_path = ensure_test_pdf()
    slides = parse_pdf(pdf_path, output_slides_dir=config.SLIDES_DIR)

    # Trang 1: Phải có Ex01 hoặc Hybrid
    s1_text = slides[0]["slide"]["title"] + " " + " ".join(slides[0]["slide"]["bullets"])
    assert any(k in s1_text for k in ["Ex01", "Hybrid", "AI Agents"]), "Trang 1 thiếu từ khóa cốt lõi!"

    # Trang 2: Phải có Pure Agentic hoặc Infinite Tool Loops
    s2_text = slides[1]["slide"]["title"] + " " + " ".join(slides[1]["slide"]["bullets"])
    assert any(k in s2_text for k in ["Pure Agentic", "Infinite Tool Loops", "Token"]), "Trang 2 thiếu từ khóa cốt lõi!"

    # Trang 4: Phải có Deterministic Backbone hoặc LangGraph hoặc State Machine
    s4_text = slides[3]["slide"]["title"] + " " + " ".join(slides[3]["slide"]["bullets"])
    assert any(k in s4_text for k in ["State Machine", "LangGraph", "Deterministic"]), "Trang 4 thiếu từ khóa cốt lõi!"

    # Trang 5: Phải có Human-In-The-Loop
    s5_text = slides[4]["slide"]["title"] + " " + " ".join(slides[4]["slide"]["bullets"])
    assert "Human-In-The-Loop" in s5_text, "Trang 5 thiếu từ khóa Human-In-The-Loop!"

    # Trang 6: Phải có Production hoặc Checkpoint hoặc Best Practices
    s6_text = slides[5]["slide"]["title"] + " " + " ".join(slides[5]["slide"]["bullets"])
    assert any(k in s6_text for k in ["Production", "Checkpoint", "Best Practices"]), "Trang 6 thiếu từ khóa cốt lõi!"


def test_reject_invalid_extension_and_empty_pdf():
    """
    Test 3: Assert file đuôi lạ (.docx) bị từ chối rõ ràng và file PDF rỗng / không có chữ
    thì báo lỗi rõ ràng thay vì crash khó hiểu.
    """
    # 1. Từ chối file đuôi lạ trong node_parse
    from agents.graph import node_parse
    fake_docx = config.PROJECT_ROOT / "test_data" / "fake_document.docx"
    res = node_parse({
        "pptx_path": str(fake_docx.resolve()),
        "auto_mode": True,
        "reset_mode": False,
        "draft_mode": True,
        "provider": "edge-tts",
        "timings": {}
    })
    assert res.get("current_node") == "error", "File đuôi .docx phải báo lỗi tại node parse!"
    assert "Chỉ nhận .pptx và .pdf" in res.get("error", "")

    # 2. Xử lý file PDF không tồn tại
    non_existent_pdf = config.PROJECT_ROOT / "test_data" / "not_found.pdf"
    with pytest.raises(FileNotFoundError):
        parse_pdf(non_existent_pdf)

    # 3. Xử lý file PDF 0 bytes / hỏng
    corrupt_pdf_path = config.PROJECT_ROOT / "test_data" / "_corrupt_test.pdf"
    corrupt_pdf_path.write_bytes(b"")
    try:
        with pytest.raises(RuntimeError) as excinfo:
            parse_pdf(corrupt_pdf_path)
        assert "Không thể mở file PDF" in str(excinfo.value)
    finally:
        corrupt_pdf_path.unlink(missing_ok=True)

    # 4. Xử lý file PDF có trang nhưng hoàn toàn không có chữ / ảnh
    import fitz
    blank_pdf_path = config.PROJECT_ROOT / "test_data" / "_blank_test.pdf"
    blank_doc = fitz.open()
    blank_doc.new_page(width=960, height=540)  # Trang trắng trơn
    blank_doc.save(str(blank_pdf_path.resolve()))
    blank_doc.close()

    try:
        with pytest.raises(RuntimeError) as excinfo:
            parse_pdf(blank_pdf_path)
        assert "không có nội dung chữ" in str(excinfo.value)
    finally:
        blank_pdf_path.unlink(missing_ok=True)
