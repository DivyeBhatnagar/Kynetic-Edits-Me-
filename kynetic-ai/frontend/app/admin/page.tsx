"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/stores/auth";

// ── API types ─────────────────────────────────────────────────────────────

type KillSwitchTargetType = "instance" | "host" | "account";
type SecurityEventSeverity = "info" | "warning" | "critical";

interface SecurityEvent {
  id: string;
  event_type: string;
  severity: SecurityEventSeverity;
  resource_type: string | null;
  resource_id: string | null;
  user_id: string | null;
  ip_address: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

interface SecurityEventList {
  items: SecurityEvent[];
  total: number;
  page: number;
  page_size: number;
}

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiCall<T>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers as Record<string, string>),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Severity badge ─────────────────────────────────────────────────────────

const SEV_STYLES: Record<SecurityEventSeverity, string> = {
  info:     "bg-blue-500/10 text-blue-300 border-blue-500/20",
  warning:  "bg-amber-500/10 text-amber-300 border-amber-500/20",
  critical: "bg-red-500/10 text-red-300 border-red-500/20",
};

function SeverityBadge({ severity }: { severity: SecurityEventSeverity }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${SEV_STYLES[severity]}`}>
      {severity.toUpperCase()}
    </span>
  );
}

// ── Kill Switch Panel ──────────────────────────────────────────────────────

function KillSwitchPanel({ token }: { token: string }) {
  const [targetType, setTargetType] = useState<KillSwitchTargetType>("instance");
  const [targetId, setTargetId] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetId.trim()) return;
    if (!confirm(`⚠️ Are you absolutely sure? This will immediately suspend ${targetType}: ${targetId}`)) return;

    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const res = await apiCall<{ id: string; broadcast_result: unknown }>(
        "/admin/kill-switch",
        token,
        {
          method: "POST",
          body: JSON.stringify({ target_type: targetType, target_id: targetId, reason }),
        }
      );
      setResult(`Kill switch triggered. Event ID: ${res.id}`);
      setTargetId("");
      setReason("");
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-red-950/20 border border-red-800/30 rounded-2xl p-6">
      <div className="flex items-center gap-3 mb-5">
        <div className="w-10 h-10 rounded-xl bg-red-900/40 flex items-center justify-center">
          <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
          </svg>
        </div>
        <div>
          <h2 className="text-lg font-bold text-red-300">Kill Switch</h2>
          <p className="text-xs text-red-500">Immediately suspend any instance, host, or account</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Target type */}
        <div>
          <label className="text-xs text-slate-500 uppercase tracking-wider block mb-2">Target Type</label>
          <div className="flex gap-2">
            {(["instance", "host", "account"] as KillSwitchTargetType[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTargetType(t)}
                className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors capitalize ${
                  targetType === t
                    ? "bg-red-600/60 text-red-200 border border-red-500/40"
                    : "bg-slate-800/50 text-slate-400 border border-slate-700/50 hover:text-white"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Target ID */}
        <div>
          <label className="text-xs text-slate-500 uppercase tracking-wider block mb-2">
            {targetType === "account" ? "User ID (UUID)" : `${targetType.charAt(0).toUpperCase() + targetType.slice(1)} ID (UUID)`}
          </label>
          <input
            type="text"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            placeholder={`Enter ${targetType} UUID…`}
            className="w-full bg-slate-800/60 border border-slate-700/50 text-white placeholder-slate-600 rounded-xl px-4 py-3 text-sm font-mono focus:outline-none focus:border-red-500/50"
            required
          />
        </div>

        {/* Reason */}
        <div>
          <label className="text-xs text-slate-500 uppercase tracking-wider block mb-2">Reason (required for audit log)</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Describe why this kill switch is being triggered…"
            rows={3}
            className="w-full bg-slate-800/60 border border-slate-700/50 text-white placeholder-slate-600 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-red-500/50 resize-none"
          />
        </div>

        {result && (
          <div className="bg-emerald-900/20 border border-emerald-700/30 rounded-xl p-3 text-emerald-300 text-sm">
            ✅ {result}
          </div>
        )}
        {error && (
          <div className="bg-red-900/20 border border-red-700/30 rounded-xl p-3 text-red-300 text-sm">
            ❌ {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !targetId.trim()}
          className="w-full bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white font-semibold py-3 rounded-xl transition-colors flex items-center justify-center gap-2"
        >
          {loading ? (
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
            </svg>
          )}
          Trigger Kill Switch
        </button>
      </form>
    </div>
  );
}

// ── Security Events Feed ───────────────────────────────────────────────────

function SecurityEventsFeed({ token }: { token: string }) {
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [severityFilter, setSeverityFilter] = useState<SecurityEventSeverity | "all">("all");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ page: String(page), page_size: "20" });
      if (severityFilter !== "all") qs.set("severity", severityFilter);
      const data = await apiCall<SecurityEventList>(`/admin/security-events?${qs}`, token);
      setEvents(data.items);
      setTotal(data.total);
    } catch {
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [token, page, severityFilter]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-lg font-bold text-white">Security Events</h2>
          <p className="text-xs text-slate-500">{total} total events</p>
        </div>
        <div className="flex gap-2">
          {(["all", "critical", "warning", "info"] as const).map((s) => (
            <button
              key={s}
              onClick={() => { setSeverityFilter(s); setPage(1); }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize ${
                severityFilter === s
                  ? "bg-violet-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:text-white"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="bg-slate-800/50 rounded-xl h-16 animate-pulse" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="text-center py-12 text-slate-600">
          <p>No security events found.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {events.map((ev) => (
            <div
              key={ev.id}
              className={`rounded-xl border p-4 transition-colors ${
                ev.severity === "critical"
                  ? "bg-red-950/20 border-red-800/20"
                  : ev.severity === "warning"
                  ? "bg-amber-950/20 border-amber-800/20"
                  : "bg-slate-800/30 border-slate-700/30"
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <SeverityBadge severity={ev.severity} />
                  <div className="min-w-0">
                    <p className="text-sm text-white font-medium truncate">
                      {ev.event_type.replace(/_/g, " ")}
                    </p>
                    <p className="text-xs text-slate-500 font-mono">
                      {ev.resource_type && ev.resource_id
                        ? `${ev.resource_type}: ${ev.resource_id.substring(0, 12)}…`
                        : ev.user_id
                        ? `user: ${ev.user_id.substring(0, 12)}…`
                        : "—"
                      }
                      {ev.ip_address && ` · ${ev.ip_address}`}
                    </p>
                  </div>
                </div>
                <time className="text-xs text-slate-600 whitespace-nowrap flex-shrink-0">
                  {new Date(ev.created_at).toLocaleTimeString()}
                </time>
              </div>
              {ev.details && Object.keys(ev.details).length > 0 && (
                <pre className="mt-2 text-xs text-slate-500 bg-slate-900/50 rounded-lg p-2 overflow-x-auto">
                  {JSON.stringify(ev.details, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {Math.ceil(total / 20) > 1 && (
        <div className="flex justify-center gap-2 mt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 bg-slate-800 rounded-lg text-xs text-slate-300 disabled:opacity-40"
          >
            ← Prev
          </button>
          <span className="px-3 py-1.5 text-slate-500 text-xs">
            {page} / {Math.ceil(total / 20)}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(Math.ceil(total / 20), p + 1))}
            disabled={page === Math.ceil(total / 20)}
            className="px-3 py-1.5 bg-slate-800 rounded-lg text-xs text-slate-300 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const { token } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (!token) router.push("/login");
  }, [token, router]);

  if (!token) return null;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white">
      {/* Header */}
      <div className="border-b border-slate-800/50 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-red-900/40 flex items-center justify-center">
              <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Security Admin</h1>
              <p className="text-xs text-slate-500">Kill switch · Security event log</p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Security stats bar */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: "Kill Switch", icon: "🔴", desc: "Instant suspension of any resource" },
            { label: "Image Scanning", icon: "🔍", desc: "Trivy CVE scan before every launch" },
            { label: "Rate Limiting", icon: "🛡️", desc: "Redis token-bucket on all routes" },
          ].map((stat) => (
            <div key={stat.label} className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-4">
              <div className="text-2xl mb-2">{stat.icon}</div>
              <div className="text-sm font-semibold text-white">{stat.label}</div>
              <div className="text-xs text-slate-500 mt-1">{stat.desc}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <KillSwitchPanel token={token} />
          <SecurityEventsFeed token={token} />
        </div>
      </div>
    </div>
  );
}
