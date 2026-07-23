"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ListingBrief,
  ListingSearchParams,
  ListingSearchResponse,
  ResourceType,
  marketplaceApi,
} from "@/lib/api";

// ── Filter sidebar ─────────────────────────────────────────────────────────

const RESOURCE_TYPES: { value: ResourceType | ""; label: string; icon: string }[] = [
  { value: "", label: "All Types", icon: "⚡" },
  { value: "gpu", label: "GPU", icon: "🎮" },
  { value: "cpu", label: "CPU", icon: "🧠" },
  { value: "ram", label: "RAM", icon: "💾" },
  { value: "nvme", label: "NVMe Storage", icon: "💿" },
  { value: "workstation_bundle", label: "Full Workstation", icon: "🖥️" },
];

const REGIONS = ["Any region", "us-east-1", "us-west-2", "eu-west-1", "ap-south-1", "in-south-1"];

function FilterSidebar({
  params,
  onChange,
}: {
  params: ListingSearchParams;
  onChange: (p: Partial<ListingSearchParams>) => void;
}) {
  return (
    <aside
      style={{
        width: 260,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        gap: 20,
      }}
    >
      <div className="glass" style={{ padding: 20 }}>
        <h3
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 13,
            fontWeight: 600,
            color: "var(--text-secondary)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            marginBottom: 14,
          }}
        >
          Resource Type
        </h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {RESOURCE_TYPES.map((rt) => {
            const active = (params.resource_type ?? "") === rt.value;
            return (
              <button
                key={rt.value}
                onClick={() =>
                  onChange({ resource_type: rt.value as ResourceType | undefined })
                }
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "9px 12px",
                  borderRadius: 8,
                  border: active
                    ? "1px solid hsl(258 90% 66% / 0.4)"
                    : "1px solid transparent",
                  background: active
                    ? "hsl(258 90% 66% / 0.1)"
                    : "transparent",
                  color: active ? "hsl(258 90% 76%)" : "var(--text-secondary)",
                  fontSize: 13,
                  fontWeight: active ? 600 : 400,
                  cursor: "pointer",
                  textAlign: "left",
                  transition: "all 0.15s ease",
                  width: "100%",
                }}
              >
                <span>{rt.icon}</span>
                {rt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Price range */}
      <div className="glass" style={{ padding: 20 }}>
        <h3
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 13,
            fontWeight: 600,
            color: "var(--text-secondary)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            marginBottom: 14,
          }}
        >
          Price / Hour (USD)
        </h3>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            className="input"
            type="number"
            placeholder="Min"
            min={0}
            value={params.min_price_usd ?? ""}
            onChange={(e) =>
              onChange({ min_price_usd: e.target.value ? +e.target.value : undefined })
            }
            style={{ flex: 1 }}
          />
          <input
            className="input"
            type="number"
            placeholder="Max"
            min={0}
            value={params.max_price_usd ?? ""}
            onChange={(e) =>
              onChange({ max_price_usd: e.target.value ? +e.target.value : undefined })
            }
            style={{ flex: 1 }}
          />
        </div>
      </div>

      {/* Region */}
      <div className="glass" style={{ padding: 20 }}>
        <h3
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 13,
            fontWeight: 600,
            color: "var(--text-secondary)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            marginBottom: 14,
          }}
        >
          Region
        </h3>
        <select
          className="input"
          value={params.region ?? ""}
          onChange={(e) =>
            onChange({ region: e.target.value || undefined })
          }
          style={{ cursor: "pointer" }}
        >
          {REGIONS.map((r) => (
            <option key={r} value={r === "Any region" ? "" : r}
              style={{ background: "hsl(224 20% 13%)" }}>
              {r}
            </option>
          ))}
        </select>
      </div>

      {/* Available only toggle */}
      <div className="glass" style={{ padding: 16, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 13, fontWeight: 500 }}>Available only</span>
        <button
          onClick={() => onChange({ available_only: !(params.available_only ?? true) })}
          style={{
            width: 44,
            height: 24,
            borderRadius: 12,
            border: "none",
            background: (params.available_only ?? true)
              ? "linear-gradient(135deg, hsl(258 90% 60%), hsl(258 90% 50%))"
              : "var(--bg-elevated)",
            cursor: "pointer",
            position: "relative",
            transition: "background 0.2s ease",
          }}
        >
          <span
            style={{
              position: "absolute",
              top: 3,
              left: (params.available_only ?? true) ? 22 : 3,
              width: 18,
              height: 18,
              borderRadius: "50%",
              background: "#fff",
              transition: "left 0.2s ease",
              boxShadow: "0 1px 4px hsl(0 0% 0% / 0.3)",
            }}
          />
        </button>
      </div>
    </aside>
  );
}

// ── Listing card ───────────────────────────────────────────────────────────

function ListingCard({ listing }: { listing: ListingBrief }) {
  const usd = parseFloat(listing.price_per_hour_usd);
  const inr = parseFloat(listing.price_per_hour_inr);

  return (
    <Link
      href={`/marketplace/${listing.id}`}
      style={{ textDecoration: "none" }}
    >
      <div
        className="glass glass-hover"
        style={{
          padding: 22,
          display: "flex",
          flexDirection: "column",
          gap: 14,
          cursor: "pointer",
          height: "100%",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
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
            <h3
              style={{
                fontFamily: "var(--font-display)",
                fontSize: 15,
                fontWeight: 600,
                color: "var(--text-primary)",
                lineHeight: 1.3,
              }}
            >
              {listing.title ?? listing.gpu_model ?? "Compute Node"}
            </h3>
          </div>
        </div>

        {/* Specs */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {listing.gpu_model && (
            <SpecChip icon="🎮" label={listing.gpu_model} />
          )}
          {listing.cpu_cores && (
            <SpecChip icon="🧠" label={`${listing.cpu_cores} cores`} />
          )}
          {listing.ram_gb && (
            <SpecChip icon="💾" label={`${listing.ram_gb} GB RAM`} />
          )}
          {listing.region && (
            <SpecChip icon="📍" label={listing.region} />
          )}
        </div>

        {/* Divider */}
        <div style={{ height: 1, background: "var(--border-subtle)" }} />

        {/* Pricing */}
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
          <div>
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontSize: 22,
                fontWeight: 700,
                background: "linear-gradient(135deg, hsl(258 90% 76%), hsl(195 100% 70%))",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              ${usd.toFixed(2)}
              <span style={{ fontSize: 13, fontWeight: 400, WebkitTextFillColor: "var(--text-secondary)" }}>
                {" "}/hr
              </span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
              ≈ ₹{inr.toFixed(0)}/hr
            </div>
          </div>
          <div
            style={{
              padding: "6px 14px",
              borderRadius: 8,
              background: "hsl(258 90% 66% / 0.15)",
              border: "1px solid hsl(258 90% 66% / 0.3)",
              color: "hsl(258 90% 76%)",
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            View Details →
          </div>
        </div>
      </div>
    </Link>
  );
}

function SpecChip({ icon, label }: { icon: string; label: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "4px 10px",
        borderRadius: 6,
        background: "var(--bg-elevated)",
        border: "1px solid var(--border-subtle)",
        fontSize: 12,
        color: "var(--text-secondary)",
      }}
    >
      {icon} {label}
    </span>
  );
}

// ── Loading skeleton ───────────────────────────────────────────────────────

function ListingCardSkeleton() {
  return (
    <div className="glass" style={{ padding: 22, height: 220 }}>
      <div className="skeleton" style={{ height: 20, width: "60%", marginBottom: 12 }} />
      <div className="skeleton" style={{ height: 16, width: "80%", marginBottom: 8 }} />
      <div className="skeleton" style={{ height: 16, width: "50%", marginBottom: 24 }} />
      <div className="skeleton" style={{ height: 1, marginBottom: 16 }} />
      <div className="skeleton" style={{ height: 28, width: "40%" }} />
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

const DEFAULT_PARAMS: ListingSearchParams = {
  available_only: true,
  page: 1,
  page_size: 20,
};

export default function MarketplacePage() {
  const [params, setParams] = useState<ListingSearchParams>(DEFAULT_PARAMS);
  const [result, setResult] = useState<ListingSearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchListings = useCallback(async (p: ListingSearchParams) => {
    setLoading(true);
    setError(null);
    try {
      const data = await marketplaceApi.search(p);
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load listings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchListings(params);
  }, [params, fetchListings]);

  const updateParams = (delta: Partial<ListingSearchParams>) => {
    setParams((prev) => ({ ...prev, ...delta, page: 1 }));
  };

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "40px 24px" }}>
      {/* Page header */}
      <div className="fade-in" style={{ marginBottom: 36, textAlign: "center" }}>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 40,
            fontWeight: 700,
            lineHeight: 1.1,
            marginBottom: 12,
          }}
        >
          <span className="gradient-text">Compute</span> Marketplace
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 16, maxWidth: 520, margin: "0 auto" }}>
          Rent verified GPU, CPU, RAM, and NVMe compute — by the second.
        </p>
        {result && (
          <p style={{ marginTop: 8, fontSize: 13, color: "var(--text-muted)" }}>
            {result.total} listing{result.total !== 1 ? "s" : ""} found
          </p>
        )}
      </div>

      {/* Search bar */}
      <div className="fade-in fade-in-delay-1" style={{ marginBottom: 32 }}>
        <input
          className="input"
          placeholder="Search by GPU model, e.g. RTX 4090..."
          style={{ maxWidth: 520, margin: "0 auto", display: "block" }}
          onChange={(e) => updateParams({ gpu_model: e.target.value || undefined })}
        />
      </div>

      {/* Main layout */}
      <div className="fade-in fade-in-delay-2" style={{ display: "flex", gap: 28, alignItems: "flex-start" }}>
        <FilterSidebar params={params} onChange={updateParams} />

        {/* Listing grid */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {error && (
            <div
              className="glass"
              style={{
                padding: 20,
                borderColor: "hsl(0 72% 51% / 0.4)",
                color: "var(--status-offline)",
                textAlign: "center",
              }}
            >
              ⚠️ {error}
            </div>
          )}

          {loading && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
                gap: 18,
              }}
            >
              {Array.from({ length: 6 }).map((_, i) => (
                <ListingCardSkeleton key={i} />
              ))}
            </div>
          )}

          {!loading && !error && result && result.items.length === 0 && (
            <div style={{ textAlign: "center", padding: "60px 20px", maxWidth: 600, margin: "0 auto" }}>
              <div style={{ fontSize: 54, marginBottom: 20 }}>🔍</div>
              <h3
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: 22,
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  marginBottom: 8,
                }}
              >
                {params.gpu_model
                  ? `No "${params.gpu_model}" currently available.`
                  : "No listings currently available."}
              </h3>
              <p style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 32 }}>
                We couldn't find any matching active compute nodes in Kynetic's local supply network.
              </p>

              <div
                style={{
                  background: "rgba(255, 255, 255, 0.02)",
                  border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: 16,
                  padding: "24px 30px",
                  backdropFilter: "blur(12px)",
                  textAlign: "left",
                }}
              >
                <h4
                  style={{
                    fontFamily: "var(--font-display)",
                    fontSize: 13,
                    fontWeight: 600,
                    color: "hsl(258, 90%, 76%)",
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                    marginBottom: 16,
                  }}
                >
                  Recommended Alternatives
                </h4>
                
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  {[
                    { name: "RunPod", url: "https://www.runpod.io/" },
                    { name: "Vast.ai", url: "https://vast.ai/" },
                    { name: "Lambda", url: "https://lambdalabs.com/" },
                    { name: "Crusoe", url: "https://www.crusoecloud.com/" },
                  ].map((provider) => (
                    <a
                      key={provider.name}
                      href={provider.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "12px 16px",
                        background: "rgba(255, 255, 255, 0.04)",
                        border: "1px solid rgba(255, 255, 255, 0.08)",
                        borderRadius: 10,
                        color: "var(--text-primary)",
                        textDecoration: "none",
                        fontSize: 14,
                        fontWeight: 600,
                        transition: "all 0.2s ease",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = "rgba(255, 255, 255, 0.08)";
                        e.currentTarget.style.borderColor = "hsl(258, 90%, 66% / 0.5)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = "rgba(255, 255, 255, 0.04)";
                        e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.08)";
                      }}
                    >
                      <span>{provider.name}</span>
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>↗</span>
                    </a>
                  ))}
                </div>
              </div>
            </div>
          )}

          {!loading && !error && result && result.items.length > 0 && (
            <>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
                  gap: 18,
                }}
              >
                {result.items.map((listing) => (
                  <ListingCard key={listing.id} listing={listing} />
                ))}
              </div>

              {/* Pagination */}
              {result.total_pages > 1 && (
                <div
                  style={{
                    marginTop: 32,
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <button
                    className="btn-ghost"
                    disabled={params.page === 1}
                    onClick={() => setParams((p) => ({ ...p, page: (p.page ?? 1) - 1 }))}
                  >
                    ← Prev
                  </button>
                  <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                    Page {result.page} / {result.total_pages}
                  </span>
                  <button
                    className="btn-ghost"
                    disabled={params.page === result.total_pages}
                    onClick={() => setParams((p) => ({ ...p, page: (p.page ?? 1) + 1 }))}
                  >
                    Next →
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
