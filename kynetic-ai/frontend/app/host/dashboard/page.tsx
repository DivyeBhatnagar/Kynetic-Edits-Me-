"use client";

/**
 * Host Dashboard — Phase 8
 *
 * Displays for a GPU host owner:
 *   • Reputation score (composite + six components + 7-day trend sparkline)
 *   • Revenue analytics (7d / 30d USD + INR)
 *   • Health snapshot (GPU/CPU temp, power draw, uptime %)
 *   • Idle time prediction + monthly income projection
 *   • Auto-pricing suggestion from the ML model
 *
 * Design: dark glassmorphism, vivid accent gradients, animated score rings.
 */

import { useEffect, useState } from "react";
import {
  dashboardApi,
  type HostDashboard,
  type ReputationComponents,
} from "@/lib/api";

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(n: string | number | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  return Number(n).toFixed(decimals);
}

function pct(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function scoreColor(score: number | null): string {
  if (score == null) return "#6b7280";
  if (score >= 0.8) return "#22d3ee";
  if (score >= 0.6) return "#a3e635";
  if (score >= 0.4) return "#fbbf24";
  return "#f87171";
}

function scoreLabel(score: number | null): string {
  if (score == null) return "No data";
  if (score >= 0.8) return "Excellent";
  if (score >= 0.6) return "Good";
  if (score >= 0.4) return "Fair";
  return "Poor";
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function ScoreRing({ score, label, size = 96 }: { score: number | null; label: string; size?: number }) {
  const radius = (size - 12) / 2;
  const circ = 2 * Math.PI * radius;
  const filled = score != null ? circ * score : 0;
  const color = scoreColor(score);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#1f2937" strokeWidth={10} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={10}
          strokeDasharray={`${filled} ${circ - filled}`}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.8s ease" }}
        />
      </svg>
      <div style={{ textAlign: "center", lineHeight: 1.2 }}>
        <div style={{ fontSize: 22, fontWeight: 700, color }}>{score != null ? `${(score * 100).toFixed(0)}` : "—"}</div>
        <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 2 }}>{label}</div>
      </div>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (!values.length) return <span style={{ color: "#6b7280", fontSize: 12 }}>No trend data</span>;
  const W = 180;
  const H = 40;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.01);
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * W;
      const y = H - ((v - min) / range) * (H - 8) - 4;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg width={W} height={H}>
      <polyline points={pts} fill="none" stroke="#22d3ee" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {values.map((v, i) => {
        const x = (i / (values.length - 1)) * W;
        const y = H - ((v - min) / range) * (H - 8) - 4;
        return <circle key={i} cx={x} cy={y} r={3} fill="#22d3ee" />;
      })}
    </svg>
  );
}

function ComponentBar({
  label,
  score,
}: {
  label: string;
  score: number | null;
}) {
  const color = scoreColor(score);
  const pctVal = score != null ? Math.round(score * 100) : 0;

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 13, color: "#d1d5db" }}>{label}</span>
        <span style={{ fontSize: 13, fontWeight: 600, color }}>
          {score != null ? `${pctVal}` : "—"}
        </span>
      </div>
      <div style={{ height: 6, background: "#1f2937", borderRadius: 4, overflow: "hidden" }}>
        <div
          style={{
            height: "100%",
            width: `${pctVal}%`,
            background: color,
            borderRadius: 4,
            transition: "width 0.8s ease",
          }}
        />
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 16,
        padding: "20px 24px",
        backdropFilter: "blur(12px)",
      }}
    >
      <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color: accent ?? "#f9fafb" }}>{value}</div>
      {sub && <div style={{ fontSize: 13, color: "#9ca3af", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function HostDashboardPage() {
  // In a real app, hostId and token come from auth context / URL params.
  // For demo, we read from query params.
  const [hostId, setHostId] = useState<string | null>(null);
  const [token, setToken] = useState<string>("");
  const [dashboard, setDashboard] = useState<HostDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inputHostId, setInputHostId] = useState("");
  const [inputToken, setInputToken] = useState("");

  async function load(hid: string, tok: string) {
    setLoading(true);
    setError(null);
    try {
      const data = await dashboardApi.get(hid, tok);
      setDashboard(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }

  const rep = dashboard?.reputation;
  const rev = dashboard?.revenue;
  const health = dashboard?.health;
  const idle = dashboard?.idle_prediction;
  const pricing = dashboard?.pricing_suggestion;

  const components: { key: keyof ReputationComponents; label: string }[] = [
    { key: "uptime_score", label: "Uptime (30d)" },
    { key: "latency_score", label: "Provisioning Latency" },
    { key: "network_score", label: "Network Throughput" },
    { key: "job_success_rate", label: "Job Success Rate" },
    { key: "benchmark_score_normalised", label: "Benchmark (GPU Class)" },
    { key: "response_time_score", label: "Agent Response Time" },
  ];

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(135deg, #0a0a0f 0%, #0d1117 50%, #0a0f1a 100%)",
        fontFamily: "'Inter', 'SF Pro Display', system-ui, sans-serif",
        color: "#f9fafb",
        padding: "40px 24px",
      }}
    >
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        <div style={{ marginBottom: 40 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: 10,
                background: "linear-gradient(135deg, #22d3ee, #818cf8)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 20,
              }}
            >
              🖥️
            </div>
            <h1 style={{ fontSize: 28, fontWeight: 700, margin: 0 }}>Host Dashboard</h1>
          </div>
          <p style={{ color: "#6b7280", margin: 0, fontSize: 15 }}>
            Revenue · Health · Reputation · Auto-Pricing · Idle Prediction
          </p>
        </div>

        {/* ── Load form ───────────────────────────────────────────────────── */}
        {!dashboard && (
          <div
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 20,
              padding: 32,
              maxWidth: 520,
              backdropFilter: "blur(16px)",
              marginBottom: 40,
            }}
          >
            <h2 style={{ margin: "0 0 20px", fontSize: 18, fontWeight: 600 }}>Load Dashboard</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <input
                id="host-id-input"
                type="text"
                placeholder="Host UUID"
                value={inputHostId}
                onChange={(e) => setInputHostId(e.target.value)}
                style={{
                  background: "rgba(255,255,255,0.06)",
                  border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: 10,
                  padding: "12px 16px",
                  color: "#f9fafb",
                  fontSize: 14,
                  outline: "none",
                }}
              />
              <input
                id="jwt-token-input"
                type="password"
                placeholder="JWT Token"
                value={inputToken}
                onChange={(e) => setInputToken(e.target.value)}
                style={{
                  background: "rgba(255,255,255,0.06)",
                  border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: 10,
                  padding: "12px 16px",
                  color: "#f9fafb",
                  fontSize: 14,
                  outline: "none",
                }}
              />
              <button
                id="load-dashboard-btn"
                onClick={() => {
                  setHostId(inputHostId);
                  setToken(inputToken);
                  load(inputHostId, inputToken);
                }}
                disabled={!inputHostId || !inputToken || loading}
                style={{
                  padding: "14px 24px",
                  background: "linear-gradient(135deg, #22d3ee, #818cf8)",
                  border: "none",
                  borderRadius: 10,
                  color: "#fff",
                  fontWeight: 700,
                  fontSize: 15,
                  cursor: loading ? "not-allowed" : "pointer",
                  opacity: loading ? 0.7 : 1,
                  transition: "opacity 0.2s",
                }}
              >
                {loading ? "Loading…" : "Load Dashboard"}
              </button>
              {error && (
                <div style={{ color: "#f87171", fontSize: 14, padding: "10px 14px", background: "rgba(248,113,113,0.1)", borderRadius: 8 }}>
                  {error}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Dashboard ───────────────────────────────────────────────────── */}
        {dashboard && (
          <>
            {/* ── Row 1: Reputation ───────────────────────────────────────── */}
            <div
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: 24,
                padding: 32,
                marginBottom: 24,
                backdropFilter: "blur(20px)",
              }}
            >
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "#9ca3af", margin: "0 0 24px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Reputation Score
              </h2>
              <div style={{ display: "flex", gap: 40, flexWrap: "wrap", alignItems: "flex-start" }}>
                {/* Composite ring + label */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
                  <ScoreRing score={rep?.composite_score ?? null} label="Composite" size={120} />
                  <div
                    style={{
                      padding: "4px 14px",
                      borderRadius: 20,
                      background: `${scoreColor(rep?.composite_score ?? null)}22`,
                      border: `1px solid ${scoreColor(rep?.composite_score ?? null)}55`,
                      fontSize: 12,
                      fontWeight: 600,
                      color: scoreColor(rep?.composite_score ?? null),
                    }}
                  >
                    {scoreLabel(rep?.composite_score ?? null)}
                  </div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>
                    {rep?.jobs_evaluated ?? 0} jobs evaluated
                  </div>
                </div>

                {/* Component bars */}
                <div style={{ flex: 1, minWidth: 260 }}>
                  {components.map(({ key, label }) => (
                    <ComponentBar
                      key={key}
                      label={label}
                      score={rep?.components[key] ?? null}
                    />
                  ))}
                </div>

                {/* Trend sparkline */}
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ fontSize: 13, color: "#6b7280", fontWeight: 500 }}>7-Day Trend</div>
                  <Sparkline values={rep?.trend ?? []} />
                  {rep?.trend && rep.trend.length > 0 && (
                    <div style={{ fontSize: 12, color: "#9ca3af" }}>
                      {rep.trend[rep.trend.length - 1] > rep.trend[0]
                        ? "↑ Improving"
                        : rep.trend[rep.trend.length - 1] < rep.trend[0]
                        ? "↓ Declining"
                        : "→ Stable"}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* ── Row 2: Revenue ───────────────────────────────────────────── */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginBottom: 24 }}>
              <StatCard
                label="Revenue (7d)"
                value={`$${fmt(rev?.total_revenue_usd_7d, 2)}`}
                sub={`₹${fmt(rev?.total_revenue_inr_7d, 0)}`}
                accent="#22d3ee"
              />
              <StatCard
                label="Revenue (30d)"
                value={`$${fmt(rev?.total_revenue_usd_30d, 2)}`}
                sub={`₹${fmt(rev?.total_revenue_inr_30d, 0)}`}
                accent="#a3e635"
              />
              <StatCard
                label="Jobs Completed"
                value={String(rev?.total_jobs_completed ?? "—")}
                sub="Last 30 days"
              />
              <StatCard
                label="Avg Job Duration"
                value={rev?.avg_job_duration_hours ? `${fmt(rev.avg_job_duration_hours, 1)}h` : "—"}
                sub="Per completed job"
              />
            </div>

            {/* ── Row 3: Health + Idle ─────────────────────────────────────── */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
              {/* Health */}
              <div
                style={{
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.07)",
                  borderRadius: 20,
                  padding: 28,
                  backdropFilter: "blur(20px)",
                }}
              >
                <h3 style={{ fontSize: 14, color: "#9ca3af", margin: "0 0 20px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  System Health
                </h3>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                  {[
                    { label: "Uptime (30d)", value: `${health?.uptime_pct_30d != null ? fmt(health.uptime_pct_30d, 1) : "—"}%` },
                    { label: "Last Heartbeat", value: health?.last_heartbeat_at ? new Date(health.last_heartbeat_at).toLocaleTimeString() : "—" },
                    { label: "GPU Temp", value: health?.gpu_temp_celsius != null ? `${fmt(health.gpu_temp_celsius, 1)}°C` : "—", hot: (health?.gpu_temp_celsius ?? 0) > 80 },
                    { label: "CPU Temp", value: health?.cpu_temp_celsius != null ? `${fmt(health.cpu_temp_celsius, 1)}°C` : "—", hot: (health?.cpu_temp_celsius ?? 0) > 75 },
                    { label: "Power Draw", value: health?.power_draw_watts != null ? `${fmt(health.power_draw_watts, 0)}W` : "—" },
                  ].map(({ label, value, hot }) => (
                    <div key={label}>
                      <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: hot ? "#fbbf24" : "#f9fafb" }}>{value}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Idle Prediction */}
              <div
                style={{
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.07)",
                  borderRadius: 20,
                  padding: 28,
                  backdropFilter: "blur(20px)",
                }}
              >
                <h3 style={{ fontSize: 14, color: "#9ca3af", margin: "0 0 20px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Income Forecast (30d)
                </h3>
                {idle ? (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                    {[
                      { label: "Gross Revenue", value: `$${fmt(idle.income_projection_monthly_usd)}` },
                      { label: "Net Income", value: idle.net_income_monthly_usd ? `$${fmt(idle.net_income_monthly_usd)}` : "—", accent: "#22d3ee" },
                      { label: "Electricity Cost", value: idle.electricity_cost_monthly_usd ? `$${fmt(idle.electricity_cost_monthly_usd)}` : "—" },
                      { label: "Utilisation", value: pct(idle.predicted_utilization_fraction), accent: "#a3e635" },
                      { label: "Idle Hours/Day", value: `${fmt(idle.predicted_idle_hours_per_day, 1)}h` },
                      { label: "Revenue (INR)", value: `₹${fmt(idle.income_projection_monthly_inr, 0)}` },
                    ].map(({ label, value, accent }) => (
                      <div key={label}>
                        <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>{label}</div>
                        <div style={{ fontSize: 18, fontWeight: 700, color: accent ?? "#f9fafb" }}>{value}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ color: "#6b7280", fontSize: 14 }}>No forecast available yet</div>
                )}
              </div>
            </div>

            {/* ── Row 4: Auto-Pricing ──────────────────────────────────────── */}
            {pricing && (
              <div
                style={{
                  background: "linear-gradient(135deg, rgba(34,211,238,0.06), rgba(129,140,248,0.06))",
                  border: "1px solid rgba(34,211,238,0.2)",
                  borderRadius: 20,
                  padding: 28,
                  backdropFilter: "blur(20px)",
                  marginBottom: 24,
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 20 }}>
                  <div>
                    <h3 style={{ fontSize: 14, color: "#9ca3af", margin: "0 0 8px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      Auto-Pricing Suggestion
                    </h3>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                      <span style={{ fontSize: 40, fontWeight: 800, color: "#22d3ee" }}>
                        ${fmt(pricing.suggested_price_usd, 4)}
                      </span>
                      <span style={{ fontSize: 18, color: "#9ca3af" }}>/ hr</span>
                      <span style={{ fontSize: 18, color: "#818cf8" }}>≈ ₹{fmt(pricing.suggested_price_inr, 2)}</span>
                    </div>
                    {pricing.confidence_interval_low_usd && pricing.confidence_interval_high_usd && (
                      <div style={{ fontSize: 13, color: "#6b7280", marginTop: 6 }}>
                        90% CI: ${fmt(pricing.confidence_interval_low_usd, 4)} – ${fmt(pricing.confidence_interval_high_usd, 4)}
                      </div>
                    )}
                  </div>
                  <div style={{ maxWidth: 420 }}>
                    <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 6, fontWeight: 600, textTransform: "uppercase" }}>
                      Model rationale
                    </div>
                    <div style={{ fontSize: 14, color: "#d1d5db", lineHeight: 1.6 }}>{pricing.rationale}</div>
                    <div style={{ marginTop: 10, fontSize: 12, color: "#4b5563" }}>Model: {pricing.model_version}</div>
                  </div>
                </div>
              </div>
            )}

            {/* Reload button */}
            <div style={{ textAlign: "center", marginTop: 32 }}>
              <button
                id="reload-dashboard-btn"
                onClick={() => load(hostId!, token)}
                style={{
                  padding: "12px 28px",
                  background: "rgba(255,255,255,0.06)",
                  border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: 10,
                  color: "#d1d5db",
                  fontSize: 14,
                  cursor: "pointer",
                  fontFamily: "inherit",
                }}
              >
                ↻ Refresh
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
