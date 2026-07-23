"""
Idle-time prediction + expected income projection — Phase 8.

Design:
  - Utilization is estimated from the last 30d of heartbeats:
      utilization = (total heartbeats marked "active") / (total heartbeats received)
  - Income projection = current_price × utilization × 24h × 30d
  - Electricity cost = power_draw_watts / 1000 × util_hours × kwh_rate
  - Net income = income - electricity_cost

  For MVP, this is a simple historical average (no ML model).
  The interface is designed to swap in a proper time-series model (Prophet / ARIMA)
  without changing the Celery task or route.
"""

from __future__ import annotations

from decimal import Decimal


def predict_idle_time(
    heartbeats: list[dict],
    current_price_usd: Decimal,
    usd_to_inr_rate: Decimal,
    electricity_kwh_rate_usd: Decimal,
    power_draw_watts: float | None = None,
) -> dict:
    """
    Compute idle prediction and income projection from heartbeat history.

    Args:
        heartbeats: list of dicts with at least {"status": "idle" | "active" | ...}
        current_price_usd: the listing's current price per hour
        usd_to_inr_rate: FX rate
        electricity_kwh_rate_usd: $/kWh
        power_draw_watts: GPU TDP (from hardware spec); None if unknown

    Returns a dict matching IdlePredictionResponse fields.
    """
    total = len(heartbeats)
    if total == 0:
        # No data — conservative defaults
        util_frac = 0.0
    else:
        active_count = sum(
            1 for h in heartbeats
            if (h.get("status") or "").lower() == "active"
        )
        util_frac = active_count / total

    util_frac = max(0.0, min(1.0, util_frac))
    idle_frac = 1.0 - util_frac
    idle_hours_per_day = round(idle_frac * 24.0, 2)

    # Monthly income = price × util_fraction × 24h × 30d
    monthly_hours = Decimal("720")  # 24 × 30
    income_usd = (current_price_usd * Decimal(str(util_frac)) * monthly_hours).quantize(
        Decimal("0.0001")
    )
    income_inr = (income_usd * usd_to_inr_rate).quantize(Decimal("0.01"))

    # Electricity cost
    elec_cost_usd: Decimal | None = None
    net_income_usd: Decimal | None = None

    if power_draw_watts is not None and power_draw_watts > 0:
        util_hours_monthly = Decimal(str(util_frac * 720.0))
        kwh_used = Decimal(str(power_draw_watts)) / Decimal("1000") * util_hours_monthly
        elec_cost_usd = (kwh_used * electricity_kwh_rate_usd).quantize(Decimal("0.0001"))
        net_income_usd = (income_usd - elec_cost_usd).quantize(Decimal("0.0001"))

    return {
        "predicted_idle_hours_per_day": idle_hours_per_day,
        "predicted_utilization_fraction": round(util_frac, 4),
        "income_projection_monthly_usd": income_usd,
        "income_projection_monthly_inr": income_inr,
        "electricity_cost_monthly_usd": elec_cost_usd,
        "net_income_monthly_usd": net_income_usd,
        "price_per_hour_usd_used": current_price_usd,
        "heartbeats_sampled": total,
    }
