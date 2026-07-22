"""Tests for hardware detection and benchmark runner (no GPU required)."""

import platform
import sys
from unittest.mock import MagicMock, patch


# ── Hardware Detection ─────────────────────────────────────────────────────

def test_hardware_manifest_to_api_dict_gpu():
    from host_agent.hardware_detect import GPUInfo, HardwareManifest

    manifest = HardwareManifest(
        cpu_model="Intel Core i9",
        cpu_cores=16,
        cpu_threads=32,
        ram_gb=64.0,
        disk_gb=2000.0,
        disk_type="nvme",
        gpus=[GPUInfo(model="NVIDIA GeForce RTX 4090", vram_gb=24.0, driver_version="535")],
        os_type="linux",
    )
    d = manifest.to_api_dict()
    assert d["gpu_model"] == "NVIDIA GeForce RTX 4090"
    assert d["gpu_count"] == 1
    assert d["gpu_vram_gb"] == 24.0
    assert d["cpu_cores"] == 16
    assert d["ram_gb"] == 64.0


def test_hardware_manifest_to_api_dict_no_gpu():
    from host_agent.hardware_detect import HardwareManifest

    manifest = HardwareManifest(
        cpu_model="AMD EPYC",
        cpu_cores=64,
        cpu_threads=128,
        ram_gb=256.0,
        disk_gb=4000.0,
        disk_type="nvme",
        gpus=[],
        os_type="linux",
    )
    d = manifest.to_api_dict()
    assert d["gpu_model"] is None
    assert d["gpu_count"] == 0
    assert d["gpu_vram_gb"] is None


def test_collect_hardware_manifest_runs_without_gpu():
    """collect_hardware_manifest should succeed on a machine with no GPU drivers."""
    with patch("host_agent.hardware_detect._detect_gpus_pynvml", return_value=[]), \
         patch("host_agent.hardware_detect._detect_gpus_gputil", return_value=[]), \
         patch("host_agent.hardware_detect._detect_gpus_mps", return_value=[]):
        from host_agent.hardware_detect import collect_hardware_manifest
        manifest = collect_hardware_manifest()

    assert manifest.cpu_cores >= 1
    assert manifest.ram_gb > 0
    assert manifest.gpu_count == 0


def test_collect_hardware_manifest_pynvml_detection():
    """When pynvml reports a GPU, it should appear in the manifest."""
    from host_agent.hardware_detect import GPUInfo

    mock_gpu = GPUInfo(model="NVIDIA GeForce RTX 4090", vram_gb=24.0, driver_version="535")

    with patch("host_agent.hardware_detect._detect_gpus_pynvml", return_value=[mock_gpu]):
        from host_agent.hardware_detect import collect_hardware_manifest
        manifest = collect_hardware_manifest()

    assert manifest.gpu_count == 1
    assert manifest.primary_gpu.model == "NVIDIA GeForce RTX 4090"
    assert manifest.primary_gpu.vram_gb == 24.0


# ── Benchmark Runner ───────────────────────────────────────────────────────

def test_flops_benchmark_runs_on_cpu():
    """FLOPs benchmark should succeed on CPU (no GPU required)."""
    from host_agent.benchmark_runner import run_flops_benchmark

    # Use a tiny matrix to keep the test fast
    result = run_flops_benchmark(matrix_size=64, duration_seconds=0.5)
    assert result.benchmark_type == "flops"
    assert result.score > 0
    assert "tflops" in result.raw_metrics
    assert result.checksum != ""


def test_llm_inference_benchmark_runs_on_cpu():
    """LLM inference benchmark should succeed on CPU."""
    from host_agent.benchmark_runner import run_llm_inference_benchmark

    # Small model, short run
    try:
        result = run_llm_inference_benchmark(duration_seconds=1.0)
        assert result.benchmark_type == "llm_inference"
        assert result.score > 0
    except ImportError:
        pytest.skip("PyTorch not installed — skipping LLM benchmark test")


def test_benchmark_result_checksum_is_deterministic():
    """Same raw_metrics should always produce same checksum."""
    import hashlib
    import json
    from host_agent.benchmark_runner import _checksum

    data = {"tflops": 82.4, "iterations": 1000, "device": "cpu"}
    c1 = _checksum(data)
    c2 = _checksum(data)
    assert c1 == c2
    assert len(c1) == 64   # SHA-256 hex digest is always 64 chars


def test_benchmark_error_returns_zero_score():
    """If benchmark fails (no PyTorch), score=0.0 and no exception is raised."""
    with patch("host_agent.benchmark_runner._get_device", return_value=None):
        from host_agent import benchmark_runner
        # Reload to pick up the mock
        result = benchmark_runner.run_flops_benchmark(matrix_size=64, duration_seconds=0.1)
        assert result.score == 0.0
        assert "error" in result.raw_metrics


def test_run_all_benchmarks_returns_three_results():
    """run_all_benchmarks always returns exactly 3 results (one per type)."""
    from host_agent.benchmark_runner import BenchmarkResult

    mock_results = [
        BenchmarkResult("llm_inference", 4200.0, {}, "abc"),
        BenchmarkResult("image_gen", 12.3, {}, "def"),
        BenchmarkResult("flops", 82.4, {}, "ghi"),
    ]
    with patch("host_agent.benchmark_runner.run_llm_inference_benchmark", return_value=mock_results[0]), \
         patch("host_agent.benchmark_runner.run_image_gen_benchmark", return_value=mock_results[1]), \
         patch("host_agent.benchmark_runner.run_flops_benchmark", return_value=mock_results[2]):
        from host_agent.benchmark_runner import run_all_benchmarks
        results = run_all_benchmarks()

    assert len(results) == 3
    types = {r.benchmark_type for r in results}
    assert types == {"llm_inference", "image_gen", "flops"}
