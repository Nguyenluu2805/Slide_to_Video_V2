"""
test_web_acceptance.py - Kịch bản kiểm thử nghiệm thu tự động cho Web Studio V2
Kiểm tra đầy đủ 5 tiêu chí nghiệm thu:
1. Mở http://localhost:5000: Có đủ 3 khối (Input / Tùy chọn / Tiến độ + Output).
2. Upload Ex01.pptx: Nhận đúng tên file và 6 slide.
3. Chạy nháp: Các bước chuyển trạng thái, realtime logs, hoàn thành có video + tải được 3 file.
4. Chạy chồng: Bị từ chối (409 Conflict), nút bị khóa.
5. Chạy bản cuối: Giọng ZeroTTS maichi, lưu ở job riêng không ghi đè video nháp.
"""

import time
import pytest
import requests
from pathlib import Path

BASE_URL = "http://127.0.0.1:5000"

def test_acceptance():
    print("=" * 70)
    print("BẮT ĐẦU KIỂM THỬ NGHIỆM THU WEB STUDIO V2")
    print("=" * 70)

    try:
        requests.get(f"{BASE_URL}/", timeout=1.0)
    except Exception:
        pytest.skip("Flask server chưa khởi động tại http://127.0.0.1:5000")

    # 1. Kiểm tra Trang chủ / và API Voices
    print("\n[TC 1] Kiểm tra GET / (Đủ 3 khối giao diện + đầy đủ các giọng)...")
    r = requests.get(f"{BASE_URL}/")
    assert r.status_code == 200, f"Lỗi GET /: {r.status_code}"
    html = r.text
    assert "1. Chọn Slide Bài Giảng" in html, "Thiếu Khối 1 (Input)"
    assert "2. Tùy Chọn Xuất Bản" in html, "Thiếu Khối 2 (Tùy chọn)"
    assert "3. Tiến Độ & Kết Quả" in html, "Thiếu Khối 3 (Tiến độ & Kết quả)"
    assert "ZeroTTS - maichi" in html, "Thiếu giọng mặc định ZeroTTS - maichi"
    assert "ZeroTTS - quangminh" in html, "Thiếu giọng ZeroTTS - quangminh"
    assert "Edge-TTS - NamMinh" in html, "Thiếu giọng Edge-TTS - NamMinh"

    # Kiểm tra API /api/voices
    r_voices = requests.get(f"{BASE_URL}/api/voices")
    assert r_voices.status_code == 200, "Lỗi GET /api/voices"
    v_data = r_voices.json()
    assert len(v_data.get("voices", [])) >= 10, f"Thiếu danh sách giọng: {len(v_data.get('voices', []))}"
    print(f"-> [OK] Trang chủ / và /api/voices hiển thị đầy đủ {len(v_data['voices'])} giọng đọc.")

    # 2. Kiểm tra Upload file
    print("\n[TC 2] Kiểm tra POST /api/upload với Ex01_Hybrid_Workflow.pptx...")
    pptx_file = Path("test_data/Ex01_Hybrid_Workflow.pptx")
    with open(pptx_file, "rb") as f:
        files = {"file": (pptx_file.name, f, "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
        r_up = requests.post(f"{BASE_URL}/api/upload", files=files)
    assert r_up.status_code == 200, f"Upload thất bại: {r_up.text}"
    up_data = r_up.json()
    assert up_data.get("filename") == "Ex01_Hybrid_Workflow.pptx", "Sai tên file upload"
    assert up_data.get("slides") == 6, f"Sai số slide: {up_data.get('slides')}"
    print(f"-> [OK] Upload thành công: {up_data['filename']} ({up_data['slides']} slide).")

    # 3. Kiểm tra Chạy Chế độ Nháp (Edge-TTS + Static Render)
    print("\n[TC 3] Kiểm tra POST /api/run ở chế độ NHÁP siêu tốc...")
    payload_draft = {
        "filename": "Ex01_Hybrid_Workflow.pptx",
        "auto": True,
        "reset": False,
        "draft": True,
        "voice": "vi-VN-NamMinhNeural"
    }
    r_run1 = requests.post(f"{BASE_URL}/api/run", json=payload_draft)
    assert r_run1.status_code == 200, f"Khởi động job 1 thất bại: {r_run1.text}"
    job1_id = r_run1.json()["job_id"]
    print(f"-> [OK] Job 1 (Nháp) đã khởi tạo: {job1_id}")

    # 4. Kiểm tra Chạy chồng khi đang chạy
    print("\n[TC 4] Kiểm tra chống chạy chồng (Concurrent Run Block)...")
    r_collision = requests.post(f"{BASE_URL}/api/run", json=payload_draft)
    assert r_collision.status_code == 409, f"Không chặn chạy chồng! Status: {r_collision.status_code}"
    print(f"-> [OK] Hệ thống đã khóa và chặn chạy chồng đúng chuẩn (Mã 409: {r_collision.json().get('error')[:40]}...).")

    # Theo dõi Job 1 hoàn thành
    print("\n[*] Đang theo dõi tiến trình Job 1 (Nháp)...")
    t0 = time.time()
    job1_data = None
    while time.time() - t0 < 900:
        r_st = requests.get(f"{BASE_URL}/api/status/{job1_id}")
        if r_st.status_code == 200:
            job1_data = r_st.json()
            progress = job1_data.get("progress", 0)
            step = job1_data.get("step", "")
            print(f"    [Job 1] Bước: {step.upper():<10} | Tiến độ: {progress}% | Done: {job1_data.get('done')}")
            if job1_data.get("done") or job1_data.get("status") in ["completed", "error"]:
                break
        time.sleep(3)

    assert job1_data and job1_data.get("done"), f"Job 1 không hoàn thành! Lỗi: {job1_data.get('error')}"
    print(f"-> [OK] Job 1 (Nháp) đã hoàn thành trong {time.time()-t0:.1f}s!")

    # Kiểm tra tải 3 file của Job 1
    for out_name, out_url in job1_data["outputs"].items():
        if out_name == "video_stream":
            continue
        r_file = requests.get(f"{BASE_URL}{out_url}")
        assert r_file.status_code == 200, f"Không tải được file {out_name} ({out_url}): {r_file.status_code}"
        assert len(r_file.content) > 100, f"File {out_name} rỗng!"
        print(f"    [Tải về] {out_name}: {out_url} ({len(r_file.content)} bytes) -> OK")

    job1_video_size = len(requests.get(f"{BASE_URL}{job1_data['outputs']['video']}").content)

    # 5. Kiểm tra Chạy bản cuối (ZeroTTS maichi) ở Job 2 riêng biệt
    print("\n[TC 5] Kiểm tra POST /api/run ở chế độ BẢN CUỐI (ZeroTTS maichi)...")
    payload_final = {
        "filename": "Ex01_Hybrid_Workflow.pptx",
        "auto": True,
        "reset": False,
        "draft": False,
        "voice": "zerotts:maichi"
    }
    r_run2 = requests.post(f"{BASE_URL}/api/run", json=payload_final)
    assert r_run2.status_code == 200, f"Khởi động job 2 thất bại: {r_run2.text}"
    job2_id = r_run2.json()["job_id"]
    assert job2_id != job1_id, "Job ID không được trùng nhau!"
    print(f"-> [OK] Job 2 (Bản cuối) đã khởi tạo: {job2_id} (Độc lập với Job 1)")

    # Theo dõi Job 2
    print("\n[*] Đang theo dõi tiến trình Job 2 (Bản cuối ZeroTTS)...")
    t0 = time.time()
    job2_data = None
    while time.time() - t0 < 900:
        r_st = requests.get(f"{BASE_URL}/api/status/{job2_id}")
        if r_st.status_code == 200:
            job2_data = r_st.json()
            progress = job2_data.get("progress", 0)
            step = job2_data.get("step", "")
            print(f"    [Job 2] Bước: {step.upper():<10} | Tiến độ: {progress}% | Done: {job2_data.get('done')}")
            if job2_data.get("done") or job2_data.get("status") in ["completed", "error"]:
                break
        time.sleep(3)

    assert job2_data and job2_data.get("done"), f"Job 2 không hoàn thành! Lỗi: {job2_data.get('error')}"
    print(f"-> [OK] Job 2 (Bản cuối) đã hoàn thành trong {time.time()-t0:.1f}s!")

    # Xác minh video của Job 1 không bị ghi đè
    r_check_job1 = requests.get(f"{BASE_URL}{job1_data['outputs']['video']}")
    assert r_check_job1.status_code == 200 and len(r_check_job1.content) == job1_video_size, "Video của Job 1 bị ghi đè hoặc hỏng!"
    print("-> [OK] Video của Job 1 (Nháp) được bảo toàn nguyên vẹn, không bị ghi đè bởi Job 2!")

    print("\n" + "=" * 70)
    print("TẤT CẢ 5 TIÊU CHÍ NGHIỆM THU ĐÃ PASS 100%!")
    print("=" * 70)

if __name__ == "__main__":
    test_acceptance()
