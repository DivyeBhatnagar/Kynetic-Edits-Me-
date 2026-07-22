"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/lib/stores/auth";

// ── Types ──────────────────────────────────────────────────────────────────

type TrustTierLevel = "unverified" | "tier1" | "tier2" | "tier3";

interface TrustTier {
  user_id: string;
  tier: TrustTierLevel;
  max_instance_vcpus: number | null;
  max_gpu_vram_gb: number | null;
  max_gpu_hours_month: number | null;
  max_spend_usd_month: number | null;
  is_wallet_frozen: boolean;
  updated_at: string;
}

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Tier config ────────────────────────────────────────────────────────────

const TIER_CONFIG: Record<TrustTierLevel, {
  label: string;
  color: string;
  gradient: string;
  icon: string;
  description: string;
  next?: string;
}> = {
  unverified: {
    label: "Unverified",
    color: "text-slate-400",
    gradient: "from-slate-700 to-slate-800",
    icon: "🔒",
    description: "New account — limited to CPU-only workloads with low spend caps.",
    next: "Verify your phone number to unlock GPU access",
  },
  tier1: {
    label: "Phone Verified",
    color: "text-blue-300",
    gradient: "from-blue-900 to-slate-800",
    icon: "📱",
    description: "Phone-verified — access to entry-level GPU instances and higher spend caps.",
    next: "Upload a government ID to unlock high-end GPUs and enterprise compute",
  },
  tier2: {
    label: "ID Verified",
    color: "text-violet-300",
    gradient: "from-violet-900 to-slate-800",
    icon: "🪪",
    description: "Government ID verified — full GPU access up to 48 GB VRAM.",
    next: "Contact support for Tier 3 (enterprise) access",
  },
  tier3: {
    label: "Enterprise",
    color: "text-amber-300",
    gradient: "from-amber-900 to-slate-800",
    icon: "⭐",
    description: "Enterprise tier — no caps. Highest priority support.",
  },
};

// ── Limit row ──────────────────────────────────────────────────────────────

function LimitRow({ label, value, unit = "" }: { label: string; value: number | null; unit?: string }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-slate-800/50 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <span className="text-sm font-semibold text-white font-mono">
        {value === null ? (
          <span className="text-emerald-400">Unlimited</span>
        ) : (
          `${value}${unit}`
        )}
      </span>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────

export default function TrustTierPage() {
  const { token, user } = useAuthStore();
  const router = useRouter();
  const [tier, setTier] = useState<TrustTier | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [idDocResult, setIdDocResult] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !user) { router.push("/login"); return; }

    const load = async () => {
      try {
        const res = await fetch(`${API}/users/${user.id}/trust-tier`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          setTier(await res.json());
        }
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [token, user, router]);

  const submitIdDocument = async () => {
    if (!token) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/identity/verify/id-document`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          document_type: "national_id",
          claim_document_uploaded: true,
        }),
      });
      const data = await res.json();
      setIdDocResult(data.message ?? "Submitted successfully");
    } catch (e: unknown) {
      setIdDocResult((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const cfg = TIER_CONFIG[tier?.tier ?? "unverified"];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white">
      {/* Header */}
      <div className="border-b border-slate-800/50 bg-slate-950/80 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-3">
          <Link href="/profile" className="text-slate-500 hover:text-slate-300 transition-colors text-sm">
            ← Profile
          </Link>
          <span className="text-slate-700">/</span>
          <span className="text-slate-300 text-sm">Trust Tier</span>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Tier card */}
        <div className={`bg-gradient-to-br ${cfg.gradient} border border-white/10 rounded-3xl p-8 mb-8 relative overflow-hidden`}>
          <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
          <div className="relative">
            <div className="text-5xl mb-4">{cfg.icon}</div>
            <div className={`text-3xl font-bold ${cfg.color} mb-2`}>{cfg.label}</div>
            <p className="text-slate-300 text-sm max-w-md">{cfg.description}</p>

            {tier?.is_wallet_frozen && (
              <div className="mt-4 inline-flex items-center gap-2 bg-red-900/30 border border-red-700/30 rounded-xl px-4 py-2">
                <span className="text-red-400 text-sm font-medium">⚠️ Wallet Frozen — Contact Support</span>
              </div>
            )}
          </div>
        </div>

        {/* Tier progression */}
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-6 mb-6">
          <h2 className="text-base font-semibold text-white mb-4">Verification Progress</h2>
          <div className="flex items-center gap-0">
            {(["unverified", "tier1", "tier2", "tier3"] as TrustTierLevel[]).map((t, idx) => {
              const isActive = t === tier?.tier;
              const isPast = ["unverified", "tier1", "tier2", "tier3"].indexOf(t) < ["unverified", "tier1", "tier2", "tier3"].indexOf(tier?.tier ?? "unverified");
              return (
                <div key={t} className="flex items-center flex-1">
                  <div className="flex flex-col items-center flex-1">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm border-2 ${
                      isActive
                        ? "bg-violet-600 border-violet-400 text-white"
                        : isPast
                        ? "bg-emerald-700 border-emerald-500 text-white"
                        : "bg-slate-800 border-slate-600 text-slate-500"
                    }`}>
                      {isPast ? "✓" : idx + 1}
                    </div>
                    <span className={`text-xs mt-1.5 text-center ${isActive ? "text-violet-300 font-medium" : isPast ? "text-emerald-400" : "text-slate-600"}`}>
                      {TIER_CONFIG[t].label}
                    </span>
                  </div>
                  {idx < 3 && (
                    <div className={`h-0.5 flex-1 -mt-4 ${isPast ? "bg-emerald-600" : "bg-slate-700"}`} />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Current limits */}
          <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-6">
            <h2 className="text-base font-semibold text-white mb-4">Your Current Limits</h2>
            <LimitRow label="Max vCPUs per instance" value={tier?.max_instance_vcpus ?? 2} />
            <LimitRow label="Max GPU VRAM" value={tier?.max_gpu_vram_gb ?? null} unit=" GB" />
            <LimitRow label="GPU-hours / month" value={tier?.max_gpu_hours_month ?? 10} unit=" hrs" />
            <LimitRow label="Spend cap / month" value={tier?.max_spend_usd_month ?? 50} unit=" USD" />
          </div>

          {/* Upgrade actions */}
          <div className="space-y-4">
            {tier?.tier === "unverified" && (
              <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-6">
                <h2 className="text-base font-semibold text-white mb-2">Verify Phone Number</h2>
                <p className="text-sm text-slate-400 mb-4">Unlock GPU access and higher compute limits by verifying your phone number.</p>
                <Link
                  href="/profile/phone-verify"
                  className="block w-full text-center bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium py-3 rounded-xl transition-colors"
                >
                  Verify Phone →
                </Link>
              </div>
            )}

            {(tier?.tier === "unverified" || tier?.tier === "tier1") && (
              <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-6">
                <h2 className="text-base font-semibold text-white mb-2">Government ID Verification</h2>
                <p className="text-sm text-slate-400 mb-4">
                  Unlock high-end GPU instances (up to 48 GB VRAM) and enterprise spend limits.
                  Review takes 24–48 hours.
                </p>
                {idDocResult ? (
                  <div className="bg-emerald-900/20 border border-emerald-700/30 rounded-xl p-3 text-emerald-300 text-sm">
                    ✅ {idDocResult}
                  </div>
                ) : (
                  <button
                    onClick={submitIdDocument}
                    disabled={submitting}
                    className="w-full bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm font-medium py-3 rounded-xl transition-colors flex items-center justify-center gap-2"
                  >
                    {submitting ? (
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                      </svg>
                    ) : null}
                    Submit ID for Verification
                  </button>
                )}
              </div>
            )}

            {tier?.tier === "tier2" && (
              <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-6">
                <h2 className="text-base font-semibold text-white mb-2">Enterprise Access</h2>
                <p className="text-sm text-slate-400 mb-4">Need unlimited compute for your organization? Contact us for enterprise tier access.</p>
                <Link
                  href="mailto:enterprise@kynetic.ai"
                  className="block w-full text-center bg-amber-700 hover:bg-amber-600 text-white text-sm font-medium py-3 rounded-xl transition-colors"
                >
                  Contact Enterprise Team →
                </Link>
              </div>
            )}

            {tier?.tier === "tier3" && (
              <div className="bg-emerald-900/20 border border-emerald-700/30 rounded-2xl p-6">
                <div className="text-3xl mb-2">⭐</div>
                <h2 className="text-base font-semibold text-emerald-300 mb-2">You're at the top tier</h2>
                <p className="text-sm text-slate-400">No caps, priority support, dedicated infrastructure team.</p>
              </div>
            )}
          </div>
        </div>

        {/* Tier comparison table */}
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-6 mt-6">
          <h2 className="text-base font-semibold text-white mb-5">Tier Comparison</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700/50">
                  <th className="text-left text-slate-500 font-medium py-2 pr-6">Feature</th>
                  {(["unverified", "tier1", "tier2", "tier3"] as TrustTierLevel[]).map((t) => (
                    <th key={t} className={`text-center font-medium py-2 px-4 ${t === tier?.tier ? "text-violet-300" : "text-slate-400"}`}>
                      {TIER_CONFIG[t].label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { label: "Max vCPUs", values: ["2", "8", "32", "∞"] },
                  { label: "GPU Access", values: ["❌", "8 GB", "48 GB", "∞"] },
                  { label: "GPU-hours/mo", values: ["10", "50", "500", "∞"] },
                  { label: "Spend/mo", values: ["$50", "$200", "$2,000", "∞"] },
                  { label: "Priority support", values: ["❌", "Email", "Priority", "Dedicated"] },
                ].map((row) => (
                  <tr key={row.label} className="border-b border-slate-800/50 last:border-0">
                    <td className="py-3 pr-6 text-slate-400">{row.label}</td>
                    {row.values.map((v, idx) => {
                      const t = ["unverified", "tier1", "tier2", "tier3"][idx] as TrustTierLevel;
                      return (
                        <td key={idx} className={`py-3 px-4 text-center font-mono ${t === tier?.tier ? "text-violet-300 font-semibold" : "text-slate-400"}`}>
                          {v}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
