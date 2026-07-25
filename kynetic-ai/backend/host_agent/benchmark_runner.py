"""
Host Agent — Benchmark Suite.

Three benchmark types matching the backend's BenchmarkType enum:
1. llm_inference   — tokens/sec using PyTorch transformer micro-model
2. image_gen       — steps/sec using a fixed denoising diffusion loop
3. flops           — matrix-multiply TFLOPS throughput

Design principles:
- All benchmarks use PyTorch (consistent across GPU/CPU/MPS backends).
- Benchmarks are deterministic: fixed seeds, fixed problem sizes.
- Results are signed before submission (Phase 5 adds HMAC signing;
  Phase 2 attaches a simple checksum for integrity).
- Benchmark scores are normalized to be comparable across machines.
"""

import hashlib
import json
import platform
import time
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class BenchmarkResult:
    benchmark_type: str          # 'llm_inference' | 'image_gen' | 'flops'
    score: float                 # Primary normalised score
    raw_metrics: dict            # Full benchmark output
    checksum: str                # SHA-256 of raw_metrics JSON (Phase 2 integrity)

    def to_api_dict(self) -> dict:
        return {
            "benchmark_type": self.benchmark_type,
            "score": round(self.score, 4),
            "raw_metrics": self.raw_metrics,
        }


def _get_device():
    """Return the best available PyTorch device."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    except ImportError:
        return None


def _checksum(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Benchmark 1 — LLM Inference (tokens/sec)
# ---------------------------------------------------------------------------
def run_llm_inference_benchmark(duration_seconds: float = 10.0) -> BenchmarkResult:
    """
    Micro-benchmark simulating LLM inference via causal language model
    forward passes on a fixed small transformer.

    Score: tokens/second (higher is better)
    Uses a fixed-size GPT-2-style model for comparability.
    """
    try:
        import torch
        import torch.nn as nn

        device = _get_device()
        if device is None:
            raise RuntimeError("PyTorch not available")

        # Fixed-seed for reproducibility
        torch.manual_seed(42)

        # Fixed small GPT-like model (comparable to GPT-2 small in inference characteristics)
        SEQ_LEN = 512
        BATCH_SIZE = 4
        D_MODEL = 768
        N_HEADS = 12
        N_LAYERS = 4
        VOCAB_SIZE = 50257

        class MiniGPT(nn.Module):
            def __init__(self):
                super().__init__()
                self.embed = nn.Embedding(VOCAB_SIZE, D_MODEL)
                self.layers = nn.ModuleList([
                    nn.TransformerEncoderLayer(
                        d_model=D_MODEL, nhead=N_HEADS, dim_feedforward=D_MODEL * 4,
                        dropout=0.0, batch_first=True
                    )
                    for _ in range(N_LAYERS)
                ])
                self.lm_head = nn.Linear(D_MODEL, VOCAB_SIZE, bias=False)

            def forward(self, x):
                h = self.embed(x)
                for layer in self.layers:
                    h = layer(h)
                return self.lm_head(h)

        model = MiniGPT().to(device)
        model.eval()

        input_ids = torch.randint(0, VOCAB_SIZE, (BATCH_SIZE, SEQ_LEN), device=device)

        # Warm-up pass
        with torch.no_grad():
            _ = model(input_ids)
        if device.type == "cuda":
            torch.cuda.synchronize()

        # Timed benchmark
        start = time.perf_counter()
        iterations = 0
        total_tokens = 0

        while time.perf_counter() - start < duration_seconds:
            with torch.no_grad():
                _ = model(input_ids)
            if device.type == "cuda":
                torch.cuda.synchronize()
            iterations += 1
            total_tokens += BATCH_SIZE * SEQ_LEN

        elapsed = time.perf_counter() - start
        tokens_per_sec = total_tokens / elapsed

        raw_metrics = {
            "tokens_per_sec": round(tokens_per_sec, 2),
            "iterations": iterations,
            "total_tokens": total_tokens,
            "elapsed_seconds": round(elapsed, 3),
            "seq_len": SEQ_LEN,
            "batch_size": BATCH_SIZE,
            "device": str(device),
        }

        logger.info("llm_inference_benchmark_complete", tokens_per_sec=round(tokens_per_sec, 2))
        return BenchmarkResult(
            benchmark_type="llm_inference",
            score=tokens_per_sec,
            raw_metrics=raw_metrics,
            checksum=_checksum(raw_metrics),
        )

    except Exception as exc:
        logger.error("llm_inference_benchmark_failed", error=str(exc))
        # Return a zero score rather than crashing the whole benchmark run
        return BenchmarkResult(
            benchmark_type="llm_inference",
            score=0.0,
            raw_metrics={"error": str(exc)},
            checksum="",
        )


# ---------------------------------------------------------------------------
# Benchmark 2 — Image Generation (steps/sec)
# ---------------------------------------------------------------------------
def run_image_gen_benchmark(n_steps: int = 20, duration_seconds: float = 10.0) -> BenchmarkResult:
    """
    Micro-benchmark simulating diffusion model denoising steps.

    Score: denoising steps/second (higher is better).
    Uses a fixed U-Net-like architecture to simulate SD inference load
    without requiring the full Stable Diffusion model weights.
    """
    try:
        import torch
        import torch.nn as nn

        device = _get_device()
        if device is None:
            raise RuntimeError("PyTorch not available")

        torch.manual_seed(42)

        # Fixed U-Net-like conv block (approximates SD's spatial attention compute pattern)
        IMAGE_SIZE = 64   # Latent resolution
        CHANNELS = 4

        class MiniUNet(nn.Module):
            def __init__(self):
                super().__init__()
                self.down1 = nn.Conv2d(CHANNELS, 128, 3, padding=1)
                self.down2 = nn.Conv2d(128, 256, 3, padding=1, stride=2)
                self.attn = nn.MultiheadAttention(256, num_heads=8, batch_first=True)
                self.up = nn.ConvTranspose2d(256, 128, 3, padding=1, stride=2, output_padding=1)
                self.out = nn.Conv2d(128, CHANNELS, 3, padding=1)
                self.act = nn.SiLU()

            def forward(self, x):
                h1 = self.act(self.down1(x))
                h2 = self.act(self.down2(h1))
                B, C, H, W = h2.shape
                h2_flat = h2.view(B, C, H * W).permute(0, 2, 1)
                h2_attn, _ = self.attn(h2_flat, h2_flat, h2_flat)
                h2 = h2_attn.permute(0, 2, 1).view(B, C, H, W)
                h = self.act(self.up(h2))
                return self.out(h)

        model = MiniUNet().to(device)
        model.eval()
        latent = torch.randn(1, CHANNELS, IMAGE_SIZE, IMAGE_SIZE, device=device)

        # Warm-up
        with torch.no_grad():
            for _ in range(3):
                _ = model(latent)
        if device.type == "cuda":
            torch.cuda.synchronize()

        # Timed run: simulate n_steps denoising steps per "image"
        start = time.perf_counter()
        images_generated = 0
        total_steps = 0

        while time.perf_counter() - start < duration_seconds:
            for _ in range(n_steps):
                with torch.no_grad():
                    latent = model(latent)
            if device.type == "cuda":
                torch.cuda.synchronize()
            images_generated += 1
            total_steps += n_steps

        elapsed = time.perf_counter() - start
        steps_per_sec = total_steps / elapsed

        raw_metrics = {
            "steps_per_sec": round(steps_per_sec, 4),
            "images_generated": images_generated,
            "total_steps": total_steps,
            "n_steps_per_image": n_steps,
            "elapsed_seconds": round(elapsed, 3),
            "device": str(device),
        }

        logger.info("image_gen_benchmark_complete", steps_per_sec=round(steps_per_sec, 4))
        return BenchmarkResult(
            benchmark_type="image_gen",
            score=steps_per_sec,
            raw_metrics=raw_metrics,
            checksum=_checksum(raw_metrics),
        )

    except Exception as exc:
        logger.error("image_gen_benchmark_failed", error=str(exc))
        return BenchmarkResult(
            benchmark_type="image_gen",
            score=0.0,
            raw_metrics={"error": str(exc)},
            checksum="",
        )


# ---------------------------------------------------------------------------
# Benchmark 3 — Raw FLOPs (TFLOPS)
# ---------------------------------------------------------------------------
def run_flops_benchmark(matrix_size: int = 4096, duration_seconds: float = 10.0) -> BenchmarkResult:
    """
    Raw matrix-multiply throughput benchmark.

    Score: TFLOPS (tera floating-point operations per second, higher is better).
    Uses fp16 on CUDA for maximum GPU throughput, fp32 on CPU/MPS.
    """
    try:
        import torch

        device = _get_device()
        if device is None:
            raise RuntimeError("PyTorch not available")

        torch.manual_seed(42)
        dtype = torch.float16 if device.type == "cuda" else torch.float32

        M = matrix_size
        A = torch.randn(M, M, dtype=dtype, device=device)
        B = torch.randn(M, M, dtype=dtype, device=device)

        # Warm-up
        for _ in range(3):
            _ = torch.matmul(A, B)
        if device.type == "cuda":
            torch.cuda.synchronize()

        # Timed run
        start = time.perf_counter()
        iterations = 0

        while time.perf_counter() - start < duration_seconds:
            _ = torch.matmul(A, B)
            if device.type == "cuda":
                torch.cuda.synchronize()
            iterations += 1

        elapsed = time.perf_counter() - start
        # FLOPs per matmul: 2 * M^3 (multiply-add)
        flops_per_iter = 2 * (M ** 3)
        total_flops = flops_per_iter * iterations
        tflops = total_flops / elapsed / 1e12

        raw_metrics = {
            "tflops": round(tflops, 4),
            "iterations": iterations,
            "matrix_size": M,
            "dtype": str(dtype),
            "elapsed_seconds": round(elapsed, 3),
            "device": str(device),
        }

        logger.info("flops_benchmark_complete", tflops=round(tflops, 4))
        return BenchmarkResult(
            benchmark_type="flops",
            score=tflops,
            raw_metrics=raw_metrics,
            checksum=_checksum(raw_metrics),
        )

    except Exception as exc:
        logger.error("flops_benchmark_failed", error=str(exc))
        return BenchmarkResult(
            benchmark_type="flops",
            score=0.0,
            raw_metrics={"error": str(exc)},
            checksum="",
        )


# ---------------------------------------------------------------------------
# Benchmark 4 — Disk I/O (read/write MB/s) & Score Tolerance Verification
# ---------------------------------------------------------------------------
def run_disk_io_benchmark(duration_seconds: float = 3.0) -> BenchmarkResult:
    """Micro-benchmark measuring disk read/write throughput (MB/s)."""
    import os
    import tempfile
    try:
        data = os.urandom(10 * 1024 * 1024)  # 10 MB chunk
        start = time.perf_counter()
        written = 0
        with tempfile.NamedTemporaryFile("wb", delete=False) as tmp:
            tmp_name = tmp.name
            while time.perf_counter() - start < (duration_seconds / 2):
                tmp.write(data)
                written += len(data)

        write_elapsed = time.perf_counter() - start
        write_mbps = (written / 1024 / 1024) / max(write_elapsed, 0.001)

        start = time.perf_counter()
        read_bytes = 0
        with open(tmp_name, "rb") as f:
            while time.perf_counter() - start < (duration_seconds / 2):
                chunk = f.read(10 * 1024 * 1024)
                if not chunk:
                    f.seek(0)
                    continue
                read_bytes += len(chunk)

        if os.path.exists(tmp_name):
            os.unlink(tmp_name)

        read_elapsed = time.perf_counter() - start
        read_mbps = (read_bytes / 1024 / 1024) / max(read_elapsed, 0.001)

        raw = {
            "write_mbps": round(write_mbps, 2),
            "read_mbps": round(read_mbps, 2),
            "total_written_mb": round(written / 1024 / 1024, 2),
            "total_read_mb": round(read_bytes / 1024 / 1024, 2),
        }
        score = (write_mbps + read_mbps) / 2.0
        return BenchmarkResult(
            benchmark_type="disk_io",
            score=score,
            raw_metrics=raw,
            checksum=_checksum(raw),
        )
    except Exception as exc:
        logger.error("disk_io_benchmark_failed", error=str(exc))
        return BenchmarkResult(
            benchmark_type="disk_io",
            score=0.0,
            raw_metrics={"error": str(exc)},
            checksum="",
        )


def verify_score_tolerance(current_score: float, baseline_score: float, max_drop_pct: float = 15.0) -> bool:
    """
    Validates if current benchmark score is within allowable tolerance of baseline.
    Returns False if performance has degraded by more than max_drop_pct (e.g. thermal throttling).
    """
    if baseline_score <= 0:
        return True
    drop_pct = ((baseline_score - current_score) / baseline_score) * 100.0
    if drop_pct > max_drop_pct:
        logger.warning("benchmark.tolerance_degraded", baseline=baseline_score, current=current_score, drop_pct=round(drop_pct, 2))
        return False
    return True


# ---------------------------------------------------------------------------
# Run all benchmarks
# ---------------------------------------------------------------------------
def run_all_benchmarks(duration_per_benchmark: float = 10.0) -> list[BenchmarkResult]:
    """
    Run all four benchmarks sequentially and return results.
    Called by the Host Agent after registration and on re-benchmark triggers.
    """
    logger.info("benchmark_suite_starting", duration_per_benchmark=duration_per_benchmark)
    results = [
        run_llm_inference_benchmark(duration_seconds=duration_per_benchmark),
        run_image_gen_benchmark(duration_seconds=duration_per_benchmark),
        run_flops_benchmark(duration_seconds=duration_per_benchmark),
        run_disk_io_benchmark(duration_seconds=min(duration_per_benchmark, 3.0)),
    ]
    logger.info(
        "benchmark_suite_complete",
        scores={r.benchmark_type: round(r.score, 4) for r in results},
    )
    return results
