"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ListingDetail, marketplaceApi } from "@/lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

// ── Benchmark chart ────────────────────────────────────────────────────────

function BenchmarkChart({ scores }: { scores: Record<string, number> }) {
  const data = Object.entries(scores).map(([key, value]) => ({
    name: key
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase()),
    value: Math.round(value * 100) / 100,
  }));

  const COLORS = [
    "hsl(258 90% 66%)",
    "hsl(195 100% 50%)",
    "hsl(280 80% 60%)",
    "hsl(160 60% 50%)",
  ];

  return (
    <div>
      <h3
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 600,
          marginBottom: 16,
          color: "var(--text-secondary)",
          textTransform: "uppercase" as const,
          letterSpacing: "0.06em",
          fontSize: 12,
        }}
      >
        Benchmark Scores
      </h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
          <XAxis
            dataKey="name"
            tick={{ fill: "hsl(220 10% 55%)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "hsl(220 10% 55%)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "hsl(224 20% 13%)",
              border: "1px solid hsl(224 20% 25%)",
              borderRadius: 8,
              color: "hsl(220 15% 95%)",
              fontSize: 12,
            }}
            cursor={{ fill: "hsl(258 90% 66% / 0.08)" }}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Spec row ───────────────────────────────────────────────────────────────

function SpecRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "10px 0",
        borderBottom: "1px solid var(--border-subtle)",
        fontSize: 14,
      }}
    >
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>{value}</span>
    </div>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────────

function DetailSkeleton() {
  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "40px 24px" }}>
      <div className="skeleton" style={{ height: 28, width: 180, marginBottom: 32 }} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: 28 }}>
        <div className="glass" style={{ padding: 32 }}>
          <div className="skeleton" style={{ height: 32, width: "60%", marginBottom: 16 }} />
          <div className="skeleton" style={{ height: 18, width: "40%", marginBottom: 32 }} />
          <div className="skeleton" style={{ height: 180 }} />
        </div>
        <div className="glass" style={{ padding: 28 }}>
          <div className="skeleton" style={{ height: 48, width: "50%", marginBottom: 20 }} />
          <div className="skeleton" style={{ height: 48, borderRadius: 10 }} />
        </div>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function ListingDetailPage({ id }: { id: string }) {
  const [listing, setListing] = useState<ListingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    marketplaceApi
      .getById(id)
      .then(setListing)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <DetailSkeleton />;

  if (error || !listing) {
    return (
      <div style={{ maxWidth: 600, margin: "80px auto", padding: "0 24px", textAlign: "center" }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>😵</div>
        <h2 style={{ fontFamily: "var(--font-display)", marginBottom: 8 }}>Listing not found</h2>
        <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>{error}</p>
        <Link href="/marketplace" className="btn-primary">← Back to Marketplace</Link>
      </div>
    );
  }

  const usd = parseFloat(listing.price_per_hour_usd);
  const inr = parseFloat(listing.price_per_hour_inr);
  const psUsd = parseFloat(listing.price_per_second_usd);

  const specs: [string, string][] = [
    ...(listing.gpu_model ? [["GPU", listing.gpu_model] as [string, string]] : []),
    ...(listing.gpu_count ? [["GPU Count", String(listing.gpu_count)] as [string, string]] : []),
    ...(listing.gpu_vram_gb ? [["VRAM", `${listing.gpu_vram_gb} GB`] as [string, string]] : []),
    ...(listing.cpu_cores ? [["CPU Cores", String(listing.cpu_cores)] as [string, string]] : []),
    ...(listing.ram_gb ? [["RAM", `${listing.ram_gb} GB`] as [string, string]] : []),
    ...(listing.storage_gb
      ? [
          [
            "Storage",
            `${listing.storage_gb} GB${listing.storage_type ? ` ${listing.storage_type.toUpperCase()}` : ""}`,
          ] as [string, string],
        ]
      : []),
    ...(listing.region ? [["Region", listing.region] as [string, string]] : []),
    [
      "Resource Type",
      listing.resource_type.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    ],
    ["Listed", new Date(listing.created_at).toLocaleDateString()],
  ];

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "40px 24px" }}>
      {/* Breadcrumb */}
      <div className="fade-in" style={{ marginBottom: 28, display: "flex", alignItems: "center", gap: 8 }}>
        <Link href="/marketplace" style={{ color: "var(--text-muted)", fontSize: 14, textDecoration: "none" }}>
          Marketplace
        </Link>
        <span style={{ color: "var(--text-muted)" }}>›</span>
        <span style={{ color: "var(--text-secondary)", fontSize: 14 }}>
          {listing.title ?? listing.gpu_model ?? "Listing"}
        </span>
      </div>

      {/* Main grid */}
      <div
        className="fade-in fade-in-delay-1"
        style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: 24, alignItems: "start" }}
      >
        {/* Left: specs + benchmark */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Header card */}
          <div className="glass" style={{ padding: 32 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <span
                className={`badge badge-${listing.resource_type === "gpu" ? "gpu" : "cpu"}`}
              >
                {listing.resource_type.replace("_", " ").toUpperCase()}
              </span>
              {listing.is_available ? (
                <span className="badge badge-available">
                  <span
                    className="pulse-dot"
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: "var(--status-available)",
                      display: "inline-block",
                    }}
                  />
                  Available
                </span>
              ) : (
                <span className="badge badge-offline">Offline</span>
              )}
            </div>

            <h1
              style={{
                fontFamily: "var(--font-display)",
                fontSize: 28,
                fontWeight: 700,
                marginBottom: 8,
              }}
            >
              {listing.title ?? listing.gpu_model ?? "Compute Node"}
            </h1>

            {listing.description && (
              <p style={{ color: "var(--text-secondary)", fontSize: 15, lineHeight: 1.6 }}>
                {listing.description}
              </p>
            )}
          </div>

          {/* Specs table */}
          <div className="glass" style={{ padding: 28 }}>
            <h2
              style={{
                fontFamily: "var(--font-display)",
                fontSize: 12,
                fontWeight: 600,
                color: "var(--text-secondary)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                marginBottom: 8,
              }}
            >
              Hardware Specs
            </h2>
            <div>
              {specs.map(([label, value]) => (
                <SpecRow key={label} label={label} value={value} />
              ))}
            </div>
          </div>

          {/* Benchmark chart */}
          {listing.benchmark_scores && Object.keys(listing.benchmark_scores).length > 0 && (
            <div className="glass" style={{ padding: 28 }}>
              <BenchmarkChart scores={listing.benchmark_scores} />
            </div>
          )}
        </div>

        {/* Right: pricing + CTA */}
        <div style={{ position: "sticky", top: 88 }}>
          <div className="glass" style={{ padding: 28 }}>
            {/* Price */}
            <div style={{ marginBottom: 20 }}>
              <div
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: 36,
                  fontWeight: 700,
                  background: "linear-gradient(135deg, hsl(258 90% 76%), hsl(195 100% 70%))",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  lineHeight: 1.1,
                }}
              >
                ${usd.toFixed(2)}
                <span style={{ fontSize: 18, fontWeight: 400, WebkitTextFillColor: "var(--text-secondary)" }}>
                  {" "}/hr
                </span>
              </div>
              <div style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
                ≈ ₹{inr.toFixed(0)}/hr · ${psUsd.toFixed(6)}/sec
              </div>
            </div>

            {/* Billing note */}
            <div
              style={{
                padding: "12px 14px",
                borderRadius: 8,
                background: "hsl(258 90% 66% / 0.08)",
                border: "1px solid hsl(258 90% 66% / 0.2)",
                marginBottom: 20,
                fontSize: 12,
                color: "var(--text-secondary)",
                lineHeight: 1.6,
              }}
            >
              💡 Billed per second. No minimum rental. Stop any time.
            </div>

            {/* Rent CTA */}
            <button
              className="btn-primary"
              style={{ width: "100%", padding: "14px 0", fontSize: 15 }}
              onClick={() => alert("Provisioning coming in Phase 4! Top up your wallet to get ready.")}
            >
              ⚡ Rent This Node
            </button>

            <div style={{ marginTop: 12, textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
              You need a funded wallet to rent compute.{" "}
              <Link href="/wallet" style={{ color: "hsl(258 90% 76%)" }}>
                Top up →
              </Link>
            </div>

            {/* Divider */}
            <div style={{ height: 1, background: "var(--border-subtle)", margin: "20px 0" }} />

            {/* Trust indicators */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                ["✅", "Verified host hardware"],
                ["🔒", "mTLS encrypted connection"],
                ["⏱️", "Per-second billing"],
                ["🛡️", "Isolated container environment"],
              ].map(([icon, text]) => (
                <div key={text} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: "var(--text-secondary)" }}>
                  <span>{icon}</span>
                  {text}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
