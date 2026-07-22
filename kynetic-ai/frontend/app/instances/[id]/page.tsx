"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { instancesApi, Instance, ConnectionInfo, DeletionReceipt } from "@/lib/api";
import { useAuthStore } from "@/lib/stores/auth";

// ── Status badge ──────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, { bg: string; dot: string; label: string }> = {
  pending:      { bg: "bg-yellow-500/10 text-yellow-300 border-yellow-500/20", dot: "bg-yellow-400 animate-pulse", label: "Pending" },
  provisioning: { bg: "bg-blue-500/10 text-blue-300 border-blue-500/20", dot: "bg-blue-400 animate-pulse", label: "Provisioning" },
  running:      { bg: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20", dot: "bg-emerald-400 animate-pulse", label: "Running" },
  stopping:     { bg: "bg-orange-500/10 text-orange-300 border-orange-500/20", dot: "bg-orange-400 animate-pulse", label: "Stopping" },
  stopped:      { bg: "bg-slate-500/10 text-slate-400 border-slate-500/20", dot: "bg-slate-500", label: "Stopped" },
  terminated:   { bg: "bg-red-500/10 text-red-400 border-red-500/20", dot: "bg-red-500", label: "Terminated" },
  failed:       { bg: "bg-red-500/10 text-red-400 border-red-500/20", dot: "bg-red-500", label: "Failed" },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.failed;
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border ${s.bg}`}>
      <span className={`w-2 h-2 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

// ── SSH Connection panel ──────────────────────────────────────────────────

function ConnectionPanel({ instanceId }: { instanceId: string }) {
  const { token } = useAuthStore();
  const [conn, setConn] = useState<ConnectionInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [keyVisible, setKeyVisible] = useState(false);

  const fetch = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await instancesApi.getConnection(token, instanceId);
      setConn(data);
    } catch (e: unknown) {
      alert((e as Error).message ?? "Failed to get connection info");
    } finally {
      setLoading(false);
    }
  };

  const copy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  };

  if (!conn) {
    return (
      <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-6">
        <h2 className="text-lg font-semibold text-white mb-2">SSH Connection</h2>
        <p className="text-slate-400 text-sm mb-4">
          Fetch your ephemeral SSH credentials. The private key is shown once — save it immediately.
        </p>
        <button
          onClick={fetch}
          disabled={loading}
          className="bg-violet-600 hover:bg-violet-500 text-white font-medium py-2.5 px-5 rounded-xl transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          {loading ? (
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
          )}
          Get SSH Credentials
        </button>
      </div>
    );
  }

  return (
    <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-6 space-y-5">
      <h2 className="text-lg font-semibold text-white">SSH Connection</h2>

      {/* Warning */}
      <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4 flex gap-3">
        <svg className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
        </svg>
        <p className="text-amber-300 text-sm">
          Save the private key now — it cannot be retrieved again. Store it at <code className="text-amber-200">~/.ssh/kynetic_key.pem</code> and set permissions to <code className="text-amber-200">chmod 600</code>.
        </p>
      </div>

      {/* SSH Command */}
      <div>
        <label className="text-xs text-slate-500 uppercase tracking-wider mb-2 block">Quick Connect</label>
        <div className="flex items-center gap-2 bg-slate-800/60 border border-slate-700/50 rounded-xl p-3">
          <code className="flex-1 text-sm text-emerald-300 font-mono break-all">{conn.ssh_command}</code>
          <button
            onClick={() => copy(conn.ssh_command, "cmd")}
            className="flex-shrink-0 text-slate-400 hover:text-white transition-colors"
          >
            {copied === "cmd" ? (
              <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Private key */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs text-slate-500 uppercase tracking-wider">Private Key (RSA 4096)</label>
          <div className="flex gap-2">
            <button
              onClick={() => setKeyVisible((v) => !v)}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              {keyVisible ? "Hide" : "Show"}
            </button>
            <button
              onClick={() => copy(conn.private_key_pem, "key")}
              className="text-xs text-violet-400 hover:text-violet-300 transition-colors"
            >
              {copied === "key" ? "✓ Copied!" : "Copy"}
            </button>
          </div>
        </div>
        <div className="bg-slate-950/60 border border-slate-700/50 rounded-xl p-3 max-h-48 overflow-y-auto">
          <pre className={`text-xs font-mono text-slate-300 whitespace-pre-wrap break-all ${keyVisible ? "" : "blur-sm select-none"}`}>
            {conn.private_key_pem}
          </pre>
        </div>
      </div>

      {/* Connection details */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-slate-800/40 rounded-xl p-3">
          <div className="text-xs text-slate-500 mb-1">Host</div>
          <code className="text-sm text-slate-300 font-mono">{conn.ssh_host}</code>
        </div>
        <div className="bg-slate-800/40 rounded-xl p-3">
          <div className="text-xs text-slate-500 mb-1">Port / User</div>
          <code className="text-sm text-slate-300 font-mono">{conn.ssh_port} / {conn.ssh_user}</code>
        </div>
      </div>

      {conn.key_expires_at && (
        <p className="text-xs text-slate-500">
          Key rotates at: {new Date(conn.key_expires_at).toLocaleString()}
        </p>
      )}
    </div>
  );
}

// ── Deletion Receipt panel ─────────────────────────────────────────────────

function DeletionReceiptPanel({ instanceId }: { instanceId: string }) {
  const { token } = useAuthStore();
  const [receipt, setReceipt] = useState<DeletionReceipt | null>(null);

  useEffect(() => {
    if (!token) return;
    instancesApi.getDeletionReceipt(token, instanceId).then(setReceipt).catch(() => {});
  }, [token, instanceId]);

  if (!receipt) return null;

  return (
    <div className="bg-emerald-900/10 border border-emerald-700/30 rounded-2xl p-6">
      <h2 className="text-lg font-semibold text-emerald-300 mb-4 flex items-center gap-2">
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
        Secure Deletion Receipt
      </h2>
      <div className="space-y-3">
        <div>
          <div className="text-xs text-slate-500 mb-1">Deletion Method</div>
          <code className="text-sm text-emerald-300 font-mono">{receipt.method}</code>
        </div>
        <div>
          <div className="text-xs text-slate-500 mb-1">SHA-256 Confirmation Hash</div>
          <code className="text-xs text-slate-400 font-mono break-all">{receipt.agent_confirmation_hash}</code>
        </div>
        <div>
          <div className="text-xs text-slate-500 mb-1">Verified At</div>
          <div className="text-sm text-slate-300">{new Date(receipt.verified_at).toLocaleString()}</div>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────

export default function InstanceDetailPage() {
  const { token } = useAuthStore();
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const instanceId = params.id as string;
  const activeTab = searchParams.get("tab") ?? "overview";

  const [instance, setInstance] = useState<Instance | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const data = await instancesApi.get(token, instanceId);
      setInstance(data);
    } finally {
      setLoading(false);
    }
  }, [token, instanceId]);

  useEffect(() => {
    if (!token) { router.push("/login"); return; }
    load();
  }, [token, load, router]);

  // Auto-refresh for transient states
  useEffect(() => {
    if (!instance) return;
    if (!["pending", "provisioning", "stopping"].includes(instance.status)) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [instance, load]);

  const handleAction = async (action: "stop" | "start" | "terminate") => {
    if (!token || !instance) return;
    if (action === "terminate" && !confirm("Terminate this instance? This is irreversible.")) return;
    setActionLoading(true);
    try {
      if (action === "stop") await instancesApi.stop(token, instanceId);
      if (action === "start") await instancesApi.start(token, instanceId);
      if (action === "terminate") await instancesApi.terminate(token, instanceId);
      await load();
    } catch (e: unknown) {
      alert((e as Error).message ?? "Action failed");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!instance) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
        Instance not found.
      </div>
    );
  }

  const costTotal = (Number(instance.price_per_second_usd) * instance.billed_seconds).toFixed(6);
  const TABS = [
    { id: "overview", label: "Overview" },
    { id: "connection", label: "SSH Connect", show: instance.status === "running" },
    { id: "receipt", label: "Deletion Receipt", show: instance.status === "terminated" },
  ].filter((t) => t.show !== false);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white">
      {/* Header */}
      <div className="border-b border-slate-800/50 bg-slate-950/80 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3 mb-1">
            <Link href="/instances" className="text-slate-500 hover:text-slate-300 transition-colors text-sm">
              ← Instances
            </Link>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h1 className="font-mono text-lg text-white">{instance.id.substring(0, 8)}…</h1>
              <StatusBadge status={instance.status} />
            </div>
            <div className="flex gap-2">
              {instance.status === "running" && (
                <button
                  onClick={() => handleAction("stop")}
                  disabled={actionLoading}
                  className="bg-slate-700 hover:bg-slate-600 text-white text-sm py-2 px-4 rounded-xl transition-colors disabled:opacity-50"
                >
                  Stop
                </button>
              )}
              {instance.status === "stopped" && (
                <button
                  onClick={() => handleAction("start")}
                  disabled={actionLoading}
                  className="bg-emerald-700 hover:bg-emerald-600 text-white text-sm py-2 px-4 rounded-xl transition-colors disabled:opacity-50"
                >
                  Resume
                </button>
              )}
              {!["terminated", "failed"].includes(instance.status) && (
                <button
                  onClick={() => handleAction("terminate")}
                  disabled={actionLoading}
                  className="bg-red-900/30 hover:bg-red-800/50 text-red-400 text-sm py-2 px-4 rounded-xl border border-red-800/40 transition-colors disabled:opacity-50"
                >
                  Terminate
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Tabs */}
        <div className="flex gap-1 mb-8 bg-slate-800/30 p-1 rounded-xl w-fit">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => router.push(`/instances/${instanceId}?tab=${tab.id}`)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? "bg-violet-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "overview" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Stats */}
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-5">
                  <div className="text-xs text-slate-500 mb-2">Total Cost</div>
                  <div className="text-2xl font-bold font-mono text-amber-300">${costTotal}</div>
                  <div className="text-xs text-slate-500 mt-1">
                    ${Number(instance.price_per_second_usd).toFixed(8)}/s
                  </div>
                </div>
                <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-5">
                  <div className="text-xs text-slate-500 mb-2">Billed Time</div>
                  <div className="text-2xl font-bold font-mono text-violet-300">
                    {Math.floor(instance.billed_seconds / 3600)}h {Math.floor((instance.billed_seconds % 3600) / 60)}m
                  </div>
                  <div className="text-xs text-slate-500 mt-1">{instance.billed_seconds}s total</div>
                </div>
              </div>

              <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-5">
                <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">Hold</div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-300">${Number(instance.hold_amount).toFixed(6)}</span>
                  <span className={`text-xs px-2 py-1 rounded-full ${
                    instance.hold_released
                      ? "bg-emerald-900/30 text-emerald-400"
                      : "bg-slate-800 text-slate-400"
                  }`}>
                    {instance.hold_released ? "Released" : "Held"}
                  </span>
                </div>
              </div>
            </div>

            {/* Instance info */}
            <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-5 space-y-3">
              <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">Details</div>
              {[
                { label: "Instance ID", value: instance.id, mono: true },
                { label: "Listing", value: instance.listing_id.substring(0, 12) + "…", mono: true },
                { label: "Host", value: instance.host_id.substring(0, 12) + "…", mono: true },
                { label: "VM ID", value: instance.firecracker_vm_id ?? "—", mono: true },
                { label: "WireGuard IP", value: instance.wireguard_ip ?? "—", mono: true },
                { label: "SSH Port", value: String(instance.ssh_port), mono: true },
                { label: "Created", value: new Date(instance.created_at).toLocaleString(), mono: false },
                { label: "Started", value: instance.started_at ? new Date(instance.started_at).toLocaleString() : "—", mono: false },
              ].map(({ label, value, mono }) => (
                <div key={label} className="flex items-start justify-between gap-4 py-2 border-b border-slate-800/50 last:border-0">
                  <span className="text-xs text-slate-500">{label}</span>
                  <span className={`text-xs text-slate-300 break-all ${mono ? "font-mono" : ""}`}>{value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "connection" && instance.status === "running" && (
          <ConnectionPanel instanceId={instanceId} />
        )}

        {activeTab === "receipt" && instance.status === "terminated" && (
          <DeletionReceiptPanel instanceId={instanceId} />
        )}
      </div>
    </div>
  );
}
