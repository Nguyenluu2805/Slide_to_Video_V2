"""
create_sample_presentation.py - Tạo file bài giảng mẫu cho AI Video Agent V2
Môn học: Kiến trúc Hybrid Workflow trong AI Agents
Không chứa RVC, không chứa tính năng giả.
"""

import sys
import io
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def create_demo_pptx(output_path: Path):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide_layout = prs.slide_layouts[6]  # Blank layout

    # Slide 1: Title Slide
    slide1 = prs.slides.add_slide(slide_layout)
    bg1 = slide1.shapes.add_shape(1, 0, 0, Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = RGBColor(15, 23, 42)
    bg1.line.color.rgb = RGBColor(15, 23, 42)

    txBox1 = slide1.shapes.add_textbox(Inches(1.5), Inches(2.2), Inches(10.333), Inches(3.0))
    tf1 = txBox1.text_frame
    tf1.word_wrap = True

    p = tf1.paragraphs[0]
    p.text = "KIẾN TRÚC HYBRID WORKFLOW TRONG AI AGENTS"
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = RGBColor(56, 189, 248)
    p.alignment = PP_ALIGN.CENTER

    p2 = tf1.add_paragraph()
    p2.text = "Kết hợp sức mạnh Deterministic Code và LLM Agentic Nodes"
    p2.font.size = Pt(22)
    p2.font.color.rgb = RGBColor(226, 232, 240)
    p2.alignment = PP_ALIGN.CENTER

    notes1 = slide1.notes_slide.notes_text_frame
    notes1.text = (
        "Chào mừng các bạn đến với chuyên đề Kiến trúc Hybrid Workflow. "
        "Hôm nay chúng ta sẽ tìm hiểu vì sao sự kết hợp giữa mã nguồn quy tắc xác định "
        "và các nút AI Agent linh hoạt là tiêu chuẩn bắt buộc cho các hệ thống phần mềm doanh nghiệp."
    )

    # Slide 2: Vấn đề của Pure Agentic
    slide2 = prs.slides.add_slide(slide_layout)
    bg2 = slide2.shapes.add_shape(1, 0, 0, Inches(13.333), Inches(7.5))
    bg2.fill.solid()
    bg2.fill.fore_color.rgb = RGBColor(15, 23, 42)
    bg2.line.color.rgb = RGBColor(15, 23, 42)

    title2 = slide2.shapes.add_textbox(Inches(1.0), Inches(0.8), Inches(11.333), Inches(1.0))
    p = title2.text_frame.paragraphs[0]
    p.text = "Vấn Đề Của Pure Agentic: Thiếu Kiểm Soát"
    p.font.size = Pt(34)
    p.font.bold = True
    p.font.color.rgb = RGBColor(56, 189, 248)

    content2 = slide2.shapes.add_textbox(Inches(1.2), Inches(2.0), Inches(10.8), Inches(4.5))
    tf2 = content2.text_frame
    tf2.word_wrap = True

    points2 = [
        "Vòng lặp vô tận (Infinite Tool Loops) khi Agent gặp lỗi ngoại lệ hoặc thiếu dữ liệu.",
        "Chi phí token leo thang chóng mặt và không thể dự đoán trước ngân sách.",
        "Thiếu tính nhất quán trong các quy trình nghiệp vụ yêu cầu độ chính xác tuyệt đối.",
        "Khó khăn trong việc kiểm thử và tái hiện lỗi khi phát sinh sự cố tại production."
    ]
    for i, pt in enumerate(points2):
        p = tf2.paragraphs[0] if i == 0 else tf2.add_paragraph()
        p.text = f"•  {pt}"
        p.font.size = Pt(20)
        p.font.color.rgb = RGBColor(241, 245, 249)
        p.space_after = Pt(14)

    notes2 = slide2.notes_slide.notes_text_frame
    notes2.text = (
        "Khi để AI tự do quyết định toàn bộ luồng xử lý, hệ thống rất dễ rơi vào trạng thái mất kiểm soát. "
        "Các vòng lặp công cụ vô tận không chỉ tiêu tốn ngân sách mà còn gây ra trải nghiệm tồi tệ cho người dùng."
    )

    # Slide 3: Giải pháp Hybrid Workflow
    slide3 = prs.slides.add_slide(slide_layout)
    bg3 = slide3.shapes.add_shape(1, 0, 0, Inches(13.333), Inches(7.5))
    bg3.fill.solid()
    bg3.fill.fore_color.rgb = RGBColor(15, 23, 42)
    bg3.line.color.rgb = RGBColor(15, 23, 42)

    title3 = slide3.shapes.add_textbox(Inches(1.0), Inches(0.8), Inches(11.333), Inches(1.0))
    p = title3.text_frame.paragraphs[0]
    p.text = "Giải Pháp: Xương Sống State Machine & Human-in-the-Loop"
    p.font.size = Pt(34)
    p.font.bold = True
    p.font.color.rgb = RGBColor(56, 189, 248)

    content3 = slide3.shapes.add_textbox(Inches(1.2), Inches(2.0), Inches(10.8), Inches(4.5))
    tf3 = content3.text_frame
    tf3.word_wrap = True

    points3 = [
        "Sử dụng State Machine (LangGraph) định hình khung xương điều phối chặt chẽ.",
        "Chỉ gọi LLM tại các nút xử lý ngôn ngữ cần tính sáng tạo và diễn giải ngữ cảnh.",
        "Human Review bắt buộc tại các điểm kiểm định quan trọng trước khi hành động.",
        "Lưu Checkpoint trạng thái liên tục giúp phục hồi tức thì sau sự cố mạng."
    ]
    for i, pt in enumerate(points3):
        p = tf3.paragraphs[0] if i == 0 else tf3.add_paragraph()
        p.text = f"•  {pt}"
        p.font.size = Pt(20)
        p.font.color.rgb = RGBColor(241, 245, 249)
        p.space_after = Pt(14)

    notes3 = slide3.notes_slide.notes_text_frame
    notes3.text = (
        "Mô hình Hybrid mang lại sự cân bằng hoàn hảo. Chúng ta có cấu trúc xác định để đảm bảo độ tin cậy, "
        "kết hợp tính linh hoạt của mô hình AI và sự giám sát của con người tại các điểm trọng yếu."
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))
    print(f"[OK] Đã tạo file bài giảng mẫu V2 tại: {output_path}")


if __name__ == "__main__":
    out_file = Path("test_data/sample_hybrid.pptx")
    create_demo_pptx(out_file)
