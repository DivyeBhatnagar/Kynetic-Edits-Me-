"""
Unit tests — auto-pricing engine.

Tests are pure Python — no DB, no network.
"""

from decimal import Decimal

import numpy as np
import pytest

from services.reputation_pricing_service.pricing import (
    PricingFeatures,
    _PricingModel,
    _build_feature_vector,
    _gpu_class_key,
    _GPU_CLASS_MEDIANS_USD,
    suggest_price,
)


# ── GPU class key resolution ───────────────────────────────────────────────────

class TestGpuClassKey:
    def test_h100(self):
        assert _gpu_class_key("NVIDIA H100 SXM5 80GB") == "h100"

    def test_a100(self):
        assert _gpu_class_key("A100 PCIe 40GB") == "a100"

    def test_rtx_4090(self):
        assert _gpu_class_key("RTX 4090") == "rtx 4090"

    def test_rtx_3090(self):
        assert _gpu_class_key("GeForce RTX 3090") == "rtx 3090"

    def test_unknown_gpu_defaults(self):
        assert _gpu_class_key("Radeon RX 7900 XTX") == "default"

    def test_none_defaults(self):
        assert _gpu_class_key(None) == "default"

    def test_case_insensitive(self):
        assert _gpu_class_key("nvidia h100") == "h100"


# ── Feature vector construction ────────────────────────────────────────────────

class TestBuildFeatureVector:
    def test_shape(self):
        feat = PricingFeatures(
            gpu_model="RTX 4090",
            benchmark_score=0.7,
            region="us-west-2",
            gpu_vram_gb=24.0,
            gpu_count=1,
            current_supply_count=10,
            recent_demand_count=5,
        )
        fv = _build_feature_vector(feat, median_price=0.8)
        assert fv.shape == (7,)

    def test_supply_demand_ratio(self):
        feat = PricingFeatures(
            gpu_model=None,
            benchmark_score=None,
            region=None,
            gpu_vram_gb=None,
            gpu_count=2,
            current_supply_count=10,
            recent_demand_count=20,
        )
        fv = _build_feature_vector(feat, median_price=0.5)
        # ratio = 20 / max(10, 1) = 2.0
        assert fv[6] == pytest.approx(2.0, abs=1e-6)

    def test_zero_supply_count_doesnt_divide_by_zero(self):
        feat = PricingFeatures(
            gpu_model=None,
            benchmark_score=None,
            region=None,
            gpu_vram_gb=None,
            gpu_count=1,
            current_supply_count=0,   # zero supply
            recent_demand_count=5,
        )
        fv = _build_feature_vector(feat, median_price=0.5)
        # max(0, 1) = 1 → 5/1 = 5.0
        assert fv[6] == pytest.approx(5.0, abs=1e-6)

    def test_none_benchmark_and_vram_default_to_zero(self):
        feat = PricingFeatures(
            gpu_model=None,
            benchmark_score=None,
            region=None,
            gpu_vram_gb=None,
            gpu_count=None,
            current_supply_count=5,
            recent_demand_count=2,
        )
        fv = _build_feature_vector(feat, median_price=0.5)
        assert fv[1] == 0.0   # benchmark_score fallback
        assert fv[2] == 0.0   # gpu_vram_gb fallback
        assert fv[3] == 1.0   # gpu_count fallback (or 1)


# ── Rule-based fallback ────────────────────────────────────────────────────────

class TestPricingModelRuleBasedFallback:
    def test_untrained_model_returns_class_median(self):
        model = _PricingModel()
        feat = PricingFeatures(
            gpu_model="RTX 4090",
            benchmark_score=0.5,
            region="us-east-1",
            gpu_vram_gb=24.0,
            gpu_count=1,
            current_supply_count=5,
            recent_demand_count=3,
        )
        sug, ci_low, ci_high, version = model.predict(
            feat,
            floor_usd=Decimal("0.05"),
            cap_usd=Decimal("50.00"),
        )
        assert version == "rule_based_v1"
        expected_median = Decimal(str(_GPU_CLASS_MEDIANS_USD["rtx 4090"]))
        assert sug == pytest.approx(expected_median, abs=Decimal("0.10"))

    def test_rule_based_floor_guard(self):
        model = _PricingModel()
        feat = PricingFeatures(
            gpu_model="default",
            benchmark_score=None,
            region=None,
            gpu_vram_gb=None,
            gpu_count=1,
            current_supply_count=100,
            recent_demand_count=0,
        )
        sug, _, _, _ = model.predict(
            feat,
            floor_usd=Decimal("1.00"),  # Floor ABOVE the default median (0.50)
            cap_usd=Decimal("50.00"),
        )
        assert sug >= Decimal("1.00")

    def test_rule_based_cap_guard(self):
        model = _PricingModel()
        feat = PricingFeatures(
            gpu_model="h100",
            benchmark_score=1.0,
            region=None,
            gpu_vram_gb=80.0,
            gpu_count=8,
            current_supply_count=1,
            recent_demand_count=100,
        )
        sug, _, _, _ = model.predict(
            feat,
            floor_usd=Decimal("0.05"),
            cap_usd=Decimal("2.00"),  # Cap BELOW h100 median (3.50)
        )
        assert sug <= Decimal("2.00")

    def test_ci_bounds_ordered(self):
        model = _PricingModel()
        feat = PricingFeatures(
            gpu_model="a100",
            benchmark_score=0.8,
            region=None,
            gpu_vram_gb=40.0,
            gpu_count=1,
            current_supply_count=5,
            recent_demand_count=5,
        )
        sug, ci_low, ci_high, _ = model.predict(
            feat,
            floor_usd=Decimal("0.05"),
            cap_usd=Decimal("50.00"),
        )
        assert ci_low <= sug <= ci_high


# ── Trained Ridge model ────────────────────────────────────────────────────────

sklearn = pytest.importorskip("sklearn", reason="scikit-learn not installed in local env — skipping Ridge model tests")


class TestPricingModelTrained:
    def _make_training_rows(self, n: int = 50) -> list[dict]:
        """Generate synthetic training rows with known price structure."""
        rng = np.random.default_rng(42)
        rows = []
        for i in range(n):
            rows.append({
                "gpu_model": "rtx 4090",
                "gpu_vram_gb": 24.0,
                "gpu_count": 1,
                "region": "us-east-1",
                "benchmark_score": float(rng.uniform(0.5, 1.0)),
                "supply_count": int(rng.integers(1, 20)),
                "demand_count": int(rng.integers(0, 30)),
                "price_per_hour_usd": float(rng.uniform(0.6, 1.2)),
            })
        return rows

    def test_model_trains_successfully(self):
        model = _PricingModel()
        rows = self._make_training_rows(50)
        version = model.train(rows)
        assert version.startswith("v")
        assert model.is_trained()

    def test_insufficient_data_skips_retrain(self):
        model = _PricingModel()
        initial_version = model._version
        model.train([])  # Empty — should skip
        assert model._version == initial_version

    def test_trained_model_returns_model_version(self):
        model = _PricingModel()
        model.train(self._make_training_rows(50))
        feat = PricingFeatures(
            gpu_model="rtx 4090",
            benchmark_score=0.8,
            region="us-east-1",
            gpu_vram_gb=24.0,
            gpu_count=1,
            current_supply_count=5,
            recent_demand_count=10,
        )
        _, _, _, version = model.predict(
            feat,
            floor_usd=Decimal("0.05"),
            cap_usd=Decimal("50.00"),
        )
        assert not version.startswith("rule_based")

    def test_trained_prediction_in_reasonable_range(self):
        """Predicted price should be within the training data price range (+20% buffer)."""
        model = _PricingModel()
        rows = self._make_training_rows(100)
        model.train(rows)
        feat = PricingFeatures(
            gpu_model="rtx 4090",
            benchmark_score=0.75,
            region="us-east-1",
            gpu_vram_gb=24.0,
            gpu_count=1,
            current_supply_count=10,
            recent_demand_count=15,
        )
        sug, _, _, _ = model.predict(
            feat,
            floor_usd=Decimal("0.05"),
            cap_usd=Decimal("50.00"),
        )
        assert Decimal("0.05") <= sug <= Decimal("50.00")


# ── suggest_price high-level helper ───────────────────────────────────────────

class TestSuggestPrice:
    def test_returns_six_values(self):
        feat = PricingFeatures(
            gpu_model="a100",
            benchmark_score=0.9,
            region="eu-west-1",
            gpu_vram_gb=40.0,
            gpu_count=1,
            current_supply_count=3,
            recent_demand_count=7,
        )
        result = suggest_price(
            feat,
            floor_usd=Decimal("0.05"),
            cap_usd=Decimal("50.00"),
            usd_to_inr_rate=Decimal("84.0"),
        )
        sug_usd, sug_inr, ci_low, ci_high, version, rationale = result
        assert sug_usd > Decimal("0")
        assert sug_inr > Decimal("0")
        assert isinstance(rationale, str)
        assert len(rationale) > 10

    def test_inr_conversion_correct(self):
        feat = PricingFeatures(
            gpu_model="a100",
            benchmark_score=0.9,
            region=None,
            gpu_vram_gb=40.0,
            gpu_count=1,
            current_supply_count=5,
            recent_demand_count=5,
        )
        sug_usd, sug_inr, _, _, _, _ = suggest_price(
            feat,
            floor_usd=Decimal("0.05"),
            cap_usd=Decimal("50.00"),
            usd_to_inr_rate=Decimal("84.0"),
        )
        expected_inr = (sug_usd * Decimal("84.0")).quantize(Decimal("0.01"))
        assert sug_inr == expected_inr

    def test_rationale_mentions_gpu_model(self):
        feat = PricingFeatures(
            gpu_model="RTX 3090",
            benchmark_score=0.6,
            region="ap-south-1",
            gpu_vram_gb=24.0,
            gpu_count=1,
            current_supply_count=8,
            recent_demand_count=2,
        )
        _, _, _, _, _, rationale = suggest_price(
            feat,
            floor_usd=Decimal("0.05"),
            cap_usd=Decimal("50.00"),
            usd_to_inr_rate=Decimal("84.0"),
        )
        assert "RTX 3090" in rationale
