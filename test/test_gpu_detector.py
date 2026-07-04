from datetime import datetime

from app.gpu import detector as detector_module
from app.gpu.detector import GPUDetector, GPUStats


def test_gpu_stats_timestamp_uses_project_utc_helper():
    """GPU 统计时间戳应使用项目统一 UTC helper。"""
    stats = GPUStats(
        gpu_index=0,
        utilization_percent=0,
        memory_used_mb=0,
        memory_free_mb=0,
        memory_total_mb=0,
        temperature_celsius=0,
        power_watts=0,
    )

    assert isinstance(stats.timestamp, datetime)


def test_node_info_logs_version_probe_failures(monkeypatch, caplog):
    """CUDA/驱动版本读取失败时应可观测，并继续返回节点信息。"""
    class FakeNvml:
        def nvmlSystemGetCudaDriverVersion(self):
            raise RuntimeError("cuda unavailable")

        def nvmlSystemGetDriverVersion(self):
            raise RuntimeError("driver unavailable")

    detector = GPUDetector()
    detector.initialized = True

    monkeypatch.setattr(detector, "detect_gpus", lambda: [])
    monkeypatch.setattr(detector_module, "pynvml", FakeNvml())

    with caplog.at_level("DEBUG", logger="app.gpu.detector"):
        node_info = detector.get_node_info(hostname="test-node")

    assert node_info.hostname == "test-node"
    assert node_info.cuda_version == "N/A"
    assert node_info.driver_version == "N/A"
    messages = [record.message for record in caplog.records]
    assert any("Failed to read CUDA driver version" in message for message in messages)
    assert any("Failed to read NVIDIA driver version" in message for message in messages)
