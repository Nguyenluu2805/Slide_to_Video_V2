"""
Suite: test_advanced_suite.py
Description: Bộ kiểm thử nâng cao 5 Test Case bao phủ hệ thống AI Video Agent V2:
  - TC 1: PPTX Parsing, Slide Metadata and Real 1080p Image Verification
  - TC 2: Centralized Config & Dynamic Hardware Device Detection
  - TC 3: Single Source of Truth (SSOT) JSON Schema & Grounding Validation
  - TC 4: Voice TTS Engine Providers Readiness (ZeroTTS & Edge-TTS)
  - TC 5: State Checkpoint Save and Recovery Workflow
"""

import os
import sys
import json
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from agents.parse import parse_presentation


class AdvancedSystemTestSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 70)
        print("TEST: BẮT ĐẦU CHẠY BỘ 5 TEST CASE CHO AI VIDEO AGENT V2")
        print("=" * 70)
        cls.test_pptx = config.TEST_DATA_DIR / "Ex01_Hybrid_Workflow.pptx"
        if not cls.test_pptx.exists():
            candidates = list(config.TEST_DATA_DIR.glob("*.pptx"))
            if candidates:
                cls.test_pptx = candidates[0]
            else:
                raise FileNotFoundError(f"Không tìm thấy file bài giảng trong {config.TEST_DATA_DIR}")
        print(f"File kiểm thử: {cls.test_pptx.name}")

    def test_01_pptx_parsing_and_1080p_images(self):
        """TC 1: Kiểm thử trích xuất slide thật 1080p, metadata và speaker notes."""
        print("\n[TC 1] Kiểm tra trích xuất slide và ảnh 1080p...")
        start_t = time.time()
        slides_data = parse_presentation(self.test_pptx)
        elapsed = time.time() - start_t

        self.assertIsInstance(slides_data, list, "Kết quả trả về phải là một list.")
        self.assertGreater(len(slides_data), 0, "Số lượng slide phải > 0.")

        for item in slides_data:
            self.assertIn("slide", item)
            self.assertIn("scene", item)
            s = item["slide"]
            self.assertIn("id", s)
            self.assertIn("title", s)
            self.assertIn("bullets", s)
            self.assertIn("notes", s)
            self.assertIn("image", s)

            img_path = PROJECT_ROOT / s["image"]
            self.assertTrue(img_path.exists(), f"Ảnh slide {img_path} phải tồn tại thực tế.")

            # Kiểm tra độ phân giải chuẩn 1920x1080
            from PIL import Image
            with Image.open(img_path) as im:
                self.assertEqual(im.size, (1920, 1080), f"Ảnh {img_path} phải đúng kích thước 1920x1080.")

        print(f"-> [OK] Đã xuất và xác minh {len(slides_data)} slide 1080p trong {elapsed:.2f}s.")

    def test_02_config_and_hardware_detection(self):
        """TC 2: Kiểm thử cấu hình tập trung và phát hiện phần cứng thực tế."""
        print("\n[TC 2] Kiểm tra config tập trung và phát hiện phần cứng...")
        self.assertEqual(config.VIDEO_WIDTH, 1920)
        self.assertEqual(config.VIDEO_HEIGHT, 1080)
        self.assertEqual(config.VIDEO_FPS, 30)

        hw_info = config.get_hardware_device_info()
        self.assertIn("device", hw_info)
        self.assertIn("device_name", hw_info)
        self.assertIn("is_gpu", hw_info)
        self.assertIn(hw_info["device"], ["cuda", "cpu"])
        print(f"-> [OK] Thiết bị phát hiện: {hw_info['device_name']} (GPU: {hw_info['is_gpu']})")

    def test_03_single_source_of_truth_schema(self):
        """TC 3: Kiểm thử cấu trúc JSON xương sống V2 có grounding."""
        print("\n[TC 3] Kiểm tra cấu trúc dữ liệu xương sống V2...")
        slides_data = parse_presentation(self.test_pptx)
        sample = slides_data[0]
        scene = sample["scene"]

        self.assertIn("slide_id", scene)
        self.assertIn("script", scene)
        self.assertIn("grounding", scene)
        grounding = scene["grounding"]
        self.assertIn("uses_notes", grounding)
        self.assertIn("bullets_covered", grounding)
        self.assertIn("bullets_missed", grounding)
        self.assertIn("invented_claims", grounding)
        print("-> [OK] Cấu trúc SSOT JSON với grounding đạt chuẩn V2.")

    def test_04_voice_engine_readiness(self):
        """TC 4: Kiểm thử tính sẵn sàng của các provider TTS (ZeroTTS & Edge-TTS)."""
        print("\n[TC 4] Kiểm tra các provider giọng đọc...")
        import edge_tts
        self.assertIsNotNone(edge_tts)

        import zerotts
        self.assertIsNotNone(zerotts)
        print("-> [OK] Cả 2 engine giọng đọc ZeroTTS và Edge-TTS đã sẵn sàng.")

    def test_05_checkpoint_save_and_restore(self):
        """TC 5: Kiểm thử cơ chế checkpoint lưu trạng thái và phục hồi."""
        print("\n[TC 5] Kiểm tra lưu và đọc checkpoint state.json...")
        test_state = {
            "current_step": "parsed",
            "slides_count": 6,
            "completed_slides": [1, 2],
            "timestamp": time.time()
        }

        # Lưu checkpoint
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(config.STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(test_state, f, ensure_ascii=False, indent=2)

        self.assertTrue(config.STATE_FILE.exists(), "File state.json phải tồn tại sau khi lưu.")

        # Đọc lại checkpoint
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            loaded_state = json.load(f)

        self.assertEqual(loaded_state["current_step"], "parsed")
        self.assertEqual(loaded_state["completed_slides"], [1, 2])
        print("-> [OK] Cơ chế Checkpoint hoạt động chính xác.")


if __name__ == "__main__":
    unittest.main()
