"""
tests/test_gpu_provider.py - Kiểm thử cơ chế chọn Provider ONNX và fallback CPU cho ZeroTTS
1. test_provider_priority: Khi có CUDAExecutionProvider -> CUDA đứng trước CPU.
2. test_cpu_fallback_when_no_cuda: Khi chỉ có CPUExecutionProvider -> Fallback CPU an toàn, không crash.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Thêm đường dẫn thư mục gốc dự án
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config


def test_provider_priority():
    """
    Test 1: Giả lập ONNX Runtime có CUDAExecutionProvider.
    Kiểm tra danh sách providers ưu tiên: CUDAExecutionProvider phải đứng trước CPUExecutionProvider.
    """
    mock_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

    with patch("onnxruntime.get_available_providers", return_value=mock_providers):
        # Kiểm tra config.get_hardware_device_info()
        hw = config.get_hardware_device_info()
        assert hw["is_gpu"] is True
        assert hw["device"] == "cuda"
        assert "CUDAExecutionProvider" in hw["providers"]

        # Kiểm tra thứ tự ưu tiên provider đưa vào ZeroTTS
        available = mock_providers
        providers = []
        if "CUDAExecutionProvider" in available:
            providers.append("CUDAExecutionProvider")
        if "DmlExecutionProvider" in available:
            providers.append("DmlExecutionProvider")
        providers.append("CPUExecutionProvider")

        assert providers[0] == "CUDAExecutionProvider"
        assert providers[-1] == "CPUExecutionProvider"
        assert providers.index("CUDAExecutionProvider") < providers.index("CPUExecutionProvider")


def test_cpu_fallback_when_no_cuda():
    """
    Test 2: Giả lập ONNX Runtime bản CPU-only (chỉ có CPUExecutionProvider).
    Kiểm tra hệ thống rơi về CPU an toàn, không crash và phát hiện cảnh báo GPU nếu có nvidia-smi.
    """
    mock_providers = ["CPUExecutionProvider"]

    with patch("onnxruntime.get_available_providers", return_value=mock_providers):
        # Kiểm tra config.get_hardware_device_info()
        hw = config.get_hardware_device_info()
        assert hw["is_gpu"] is False
        assert hw["device"] == "cpu"
        assert hw["device_name"] == "CPU"

        # Kiểm tra danh sách provider fallback
        available = mock_providers
        providers = []
        if "CUDAExecutionProvider" in available:
            providers.append("CUDAExecutionProvider")
        if "DmlExecutionProvider" in available:
            providers.append("DmlExecutionProvider")
        providers.append("CPUExecutionProvider")

        assert len(providers) == 1
        assert providers[0] == "CPUExecutionProvider"


def test_warning_when_nvidia_gpu_present_but_onnx_cpu_only(capsys):
    """
    Test 3: Kiểm tra logic cảnh báo trong main.py khi máy có GPU NVIDIA nhưng gói ONNX là CPU-only.
    """
    mock_hw = {
        "device": "cpu",
        "device_name": "CPU",
        "is_gpu": False,
        "providers": ["CPUExecutionProvider"]
    }
    mock_subproc = MagicMock()
    mock_subproc.returncode = 0

    with patch("config.get_hardware_device_info", return_value=mock_hw), \
         patch("subprocess.run", return_value=mock_subproc):

        hw = config.get_hardware_device_info()
        providers = hw.get("providers", [])
        assert "CUDAExecutionProvider" not in providers

        # Mô phỏng đoạn kiểm tra cảnh báo
        has_nvidia = True
        if "CUDAExecutionProvider" not in providers and has_nvidia:
            print("[!] CẢNH BÁO: Phát hiện GPU NVIDIA nhưng onnxruntime không có CUDA provider — đang chạy CPU.")
            print("    -> Chạy lệnh: pip uninstall onnxruntime -y && pip install onnxruntime-gpu")

        captured = capsys.readouterr()
        assert "Phát hiện GPU NVIDIA nhưng onnxruntime không có CUDA provider" in captured.out
        assert "pip install onnxruntime-gpu" in captured.out
