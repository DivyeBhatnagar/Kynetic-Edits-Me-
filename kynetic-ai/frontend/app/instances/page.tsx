"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { instancesApi, Instance, InstanceStatus } from "@/lib/api";
import { useAuthStore } from "@/lib/stores/auth";

// ── Status badge ──────────────────────────────────────────────────────────

const STATUS_STYLES: Record<InstanceStatus, { bg: string; dot: string; label: string }> = {
  pending:      { bg: "bg-yellow-500/10 text-yellow-300 border-yellow-500/20", dot: "bg-yellow-400 animate-pulse", label: "Pending" },
  provisioning: { bg: "bg-blue-500/10 text-blue-300 border-blue-500/20", dot: "bg-blue-400 animate-pulse", label: "Provisioning" },
  running:      { bg: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20", dot: "bg-emerald-400", label: "Running" },
  stopping:     { bg: "bg-orange-500/10 text-orange-300 border-orange-500/20", dot: "bg-orange-400 animate-pulse", label: "Stopping" },
  stopped:      { bg: "bg-slate-500/10 text-slate-400 border-slate-500/20", dot: "bg-slate-500", label: "Stopped" },
  terminated:   { bg: "bg-red-500/10 text-red-400 border-red-500/20", dot: "bg-red-500", label: "Terminated" },
  failed:       { bg: "bg-red-500/10 text-red-400 border-red-500/20", dot: "bg-red-500", label: "Failed" },
};

function StatusBadge({ status }: { status: InstanceStatus }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.failed;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${s.bg}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

// ── Billed time formatter ──────────────────────────────────────────────────

function formatBilledTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

// ── Uptime live counter for running instances ──────────────────────────────

function UptimeTicker({ startedAt }: { startedAt: string | null }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!startedAt) return;
    const start = new Date(startedAt).getTime();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  return <span className="font-mono text-sm text-emerald-300">{formatBilledTime(elapsed)}</span>;
}

// ── Instance card ─────────────────────────────────────────────────────────

function InstanceCard({ instance, onAction }: { instance: Instance; onAction: () => void }) {
  const { token } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const cost = (
    Number(instance.price_per_second_usd) * instance.billed_seconds
  ).toFixed(6);

  const handle = async (action: "stop" | "start" | "terminate") => {
    if (!token) return;
    setLoading(true);
    try {
      if (action === "stop") await instancesApi.stop(token, instance.id);
      if (action === "start") await instancesApi.start(token, instance.id);
      if (action === "terminate") {
        if (!confirm("Terminate this instance? This action is irreversible and will shred all data.")) {
          setLoading(false);
          return;
        }
        await instancesApi.terminate(token, instance.id);
      }
      onAction();
    } catch (e: unknown) {
      alert((e as Error).message ?? "Action failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-5 hover:border-violet-500/40 transition-all duration-200 group">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <button
            onClick={() => router.push(`/instances/${instance.id}`)}
            className="font-mono text-sm text-slate-300 hover:text-violet-300 transition-colors"
          >
            {instance.id.substring(0, 8)}…
          </button>
          <div className="mt-1">
            <StatusBadge status={instance.status} />
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-slate-500 mb-1">Billed</div>
          {instance.status === "running" ? (
            <UptimeTicker startedAt={instance.started_at} />
          ) : (
            <span className="font-mono text-sm text-slate-300">
              {formatBilledTime(instance.billed_seconds)}
            </span>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-slate-800/50 rounded-xl p-3">
          <div className="text-xs text-slate-500 mb-1">Cost so far</div>
          <div className="font-mono text-sm text-amber-300">${cost}</div>
        </div>
        <div className="bg-slate-800/50 rounded-xl p-3">
          <div className="text-xs text-slate-500 mb-1">Rate</div>
          <div className="font-mono text-sm text-slate-300">
            ${Number(instance.price_per_second_usd).toFixed(8)}<span className="text-slate-500">/s</span>
          </div>
        </div>
      </div>

      {/* WireGuard IP */}
      {instance.wireguard_ip && (
        <div className="text-xs text-slate-500 mb-4 font-mono">
          WG: {instance.wireguard_ip}
          {instance.firecracker_vm_id && (
            <span className="ml-3">VM: {instance.firecracker_vm_id}</span>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 flex-wrap">
        {instance.status === "running" && (
          <>
            <button
              onClick={() => router.push(`/instances/${instance.id}`)}
              className="flex-1 bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium py-2 px-3 rounded-lg transition-colors"
            >
              SSH Connect
            </button>
            <button
              onClick={() => handle("stop")}
              disabled={loading}
              className="bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs font-medium py-2 px-3 rounded-lg transition-colors disabled:opacity-50"
            >
              Stop
            </button>
          </>
        )}
        {instance.status === "stopped" && (
          <button
            onClick={() => handle("start")}
            disabled={loading}
            className="flex-1 bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-medium py-2 px-3 rounded-lg transition-colors disabled:opacity-50"
          >
            Resume
          </button>
        )}
        {!["terminated", "failed"].includes(instance.status) && (
          <button
            onClick={() => handle("terminate")}
            disabled={loading}
            className="bg-red-900/40 hover:bg-red-800/60 text-red-400 text-xs font-medium py-2 px-3 rounded-lg border border-red-800/40 transition-colors disabled:opacity-50"
          >
            Terminate
          </button>
        )}
        {instance.status === "terminated" && (
          <Link
            href={`/instances/${instance.id}?tab=receipt`}
            className="text-xs text-slate-500 hover:text-slate-300 py-2 px-3 rounded-lg border border-slate-700/50 transition-colors"
          >
            View Receipt
          </Link>
        )}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────

const STATUS_FILTERS: { label: string; value: InstanceStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Running", value: "running" },
  { label: "Stopped", value: "stopped" },
  { label: "Provisioning", value: "provisioning" },
  { label: "Terminated", value: "terminated" },
];

export default function InstancesPage() {
  const { token, user } = useAuthStore();
  const router = useRouter();
  const [instances, setInstances] = useState<Instance[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<InstanceStatus | "all">("all");
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await instancesApi.list(
        token,
        filter === "all" ? undefined : filter,
        page
      );
      setInstances(res.items);
      setTotal(res.total);
    } catch {
      setInstances([]);
    } finally {
      setLoading(false);
    }
  }, [token, filter, page]);

  useEffect(() => {
    if (!token) { router.push("/login"); return; }
    load();
  }, [token, load, router]);

  // Auto-refresh every 5s if any instance is in a transient state
  useEffect(() => {
    const hasTransient = instances.some((i) =>
      ["pending", "provisioning", "stopping"].includes(i.status)
    );
    if (!hasTransient) return;
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [instances, load]);

  const totalPages = Math.ceil(total / 20);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white">
      {/* Header */}
      <div className="border-b border-slate-800/50 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">My Instances</h1>
            <p className="text-xs text-slate-500">{total} total</p>
          </div>
          <Link
            href="/marketplace"
            className="bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium py-2 px-4 rounded-xl transition-colors flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Launch New
          </Link>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Filter tabs */}
        <div className="flex gap-2 mb-8 overflow-x-auto pb-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => { setFilter(f.value); setPage(1); }}
              className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-colors ${
                filter === f.value
                  ? "bg-violet-600 text-white"
                  : "bg-slate-800/50 text-slate-400 hover:text-white hover:bg-slate-700/50"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-5 animate-pulse h-48" />
            ))}
          </div>
        ) : instances.length === 0 ? (
          <div className="text-center py-24">
            <div className="w-16 h-16 rounded-2xl bg-slate-800/50 flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </div>
            <h3 className="text-slate-400 font-medium mb-2">No instances yet</h3>
            <p className="text-slate-600 text-sm mb-6">Launch your first compute instance from the marketplace.</p>
            <Link
              href="/marketplace"
              className="bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium py-2.5 px-6 rounded-xl transition-colors"
            >
              Browse Marketplace
            </Link>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {instances.map((instance) => (
                <InstanceCard key={instance.id} instance={instance} onAction={load} />
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex justify-center gap-2 mt-8">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-4 py-2 bg-slate-800 rounded-xl text-sm text-slate-300 disabled:opacity-40"
                >
                  ← Prev
                </button>
                <span className="px-4 py-2 text-slate-500 text-sm">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-4 py-2 bg-slate-800 rounded-xl text-sm text-slate-300 disabled:opacity-40"
                >
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
