"use client";

/**
 * Developer Dashboard — Phase 10 (Final)
 *
 * Shows: running instances, billing history, GST invoices, and support ticket form.
 * Wires to: instancesApi, walletApi, invoicesApi, supportApi.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Invoice,
  InvoiceListResponse,
  SupportTicket,
  TransactionListResponse,
  invoicesApi,
  supportApi,
  walletApi,
} from "@/lib/api";

const DEMO_TOKEN = "";

// ── Tab navigation ─────────────────────────────────────────────────────────

const TABS = ["Billing", "Invoices", "Support"] as const;
type Tab = (typeof TABS)[number];

// ── Billing history ────────────────────────────────────────────────────────

function BillingHistory({ token }: { token: string }) {
  const [data, setData] = useState<TransactionListResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    walletApi.getTransactions(token).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, [token]);

  const typeColor = (t: string) => ({
    topup: "hsl(142, 71%, 55%)",
    debit: "hsl(0, 72%, 60%)",
    refund: "hsl(197, 71%, 55%)",
    payout: "hsl(258, 90%, 76%)",
  }[t] ?? "var(--text-muted)");

  const typeLabel = (t: string) => ({
    topup: "Top-up",
    debit: "Compute charge",
    refund: "Refund",
    payout: "Host payout",
  }[t] ?? t);

  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {[0, 1, 2].map((i) => (
          <div key={i} className="glass skeleton" style={{ height: 56, borderRadius: 10 }} />
        ))}
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="glass" style={{ padding: 40, textAlign: "center" }}>
        <div style={{ fontSize: 36, marginBottom: 10 }}>💳</div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No transactions yet.</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {data.items.map((txn) => (
        <div
          key={txn.id}
          className="glass"
          style={{
            padding: "12px 16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <p style={{ fontSize: 14, fontWeight: 500, color: "var(--text-primary)", margin: 0 }}>
              {txn.description ?? typeLabel(txn.transaction_type)}
            </p>
            <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0, marginTop: 2 }}>
              {new Date(txn.created_at).toLocaleString()}
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <p
              style={{
                fontSize: 15,
                fontWeight: 700,
                color: typeColor(txn.transaction_type),
                margin: 0,
              }}
            >
              {txn.transaction_type === "debit" ? "−" : "+"} ${Number(txn.amount).toFixed(4)}
            </p>
            <p style={{ fontSize: 11, color: "var(--text-muted)", margin: 0 }}>
              Balance: ${Number(txn.balance_after_usd).toFixed(4)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Invoices ───────────────────────────────────────────────────────────────

function InvoicesList({ token }: { token: string }) {
  const [data, setData] = useState<InvoiceListResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    invoicesApi.list(token).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {[0, 1].map((i) => (
          <div key={i} className="glass skeleton" style={{ height: 68, borderRadius: 10 }} />
        ))}
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="glass" style={{ padding: 40, textAlign: "center" }}>
        <div style={{ fontSize: 36, marginBottom: 10 }}>🧾</div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
          No GST invoices yet. Invoices are generated for India-region transactions.
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {data.items.map((inv) => (
        <div
          key={inv.id}
          className="glass"
          style={{
            padding: "14px 16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
              {inv.invoice_number}
            </p>
            <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0, marginTop: 2 }}>
              ₹{inv.amount_inr} · GST ₹{inv.gst_amount_inr} ({inv.gst_rate_pct}%) ·{" "}
              {new Date(inv.issued_at).toLocaleDateString("en-IN")}
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {inv.gstin && (
              <span
                style={{
                  fontSize: 11,
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 6,
                  padding: "2px 8px",
                  color: "var(--text-muted)",
                  fontFamily: "monospace",
                }}
              >
                {inv.gstin}
              </span>
            )}
            {inv.pdf_url ? (
              <a
                href={inv.pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-ghost"
                style={{ fontSize: 12, padding: "4px 12px" }}
              >
                ↓ PDF
              </a>
            ) : (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Generating…</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Support form ───────────────────────────────────────────────────────────

function SupportForm({ token }: { token: string }) {
  const [form, setForm] = useState({ subject: "", description: "", region: "global" });
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState<SupportTicket | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const ticket = await supportApi.create(form, token);
      setSubmitted(ticket);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to submit ticket");
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <div className="glass" style={{ padding: 40, textAlign: "center" }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>✅</div>
        <p style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
          Ticket submitted
        </p>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 8 }}>
          #{submitted.id.slice(0, 8)} · {submitted.region === "india" ? "🇮🇳 India support" : "Global support"} · {submitted.status}
        </p>
        <button
          className="btn-ghost"
          onClick={() => { setSubmitted(null); setForm({ subject: "", description: "", region: "global" }); }}
          style={{ fontSize: 12 }}
        >
          Submit another
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="glass" style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
      <h3 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
        New Support Ticket
      </h3>

      {error && (
        <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "hsl(0, 72%, 65%)" }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
            Region
          </label>
          <select
            id="support-region"
            className="input"
            value={form.region}
            onChange={(e) => setForm((f) => ({ ...f, region: e.target.value }))}
          >
            <option value="global">🌍 Global</option>
            <option value="india">🇮🇳 India</option>
          </select>
        </div>
        <div style={{ flex: 3 }}>
          <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
            Subject
          </label>
          <input
            id="support-subject"
            className="input"
            placeholder="Brief description of the issue"
            value={form.subject}
            onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))}
            required
            minLength={5}
          />
        </div>
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
          Description
        </label>
        <textarea
          id="support-description"
          className="input"
          placeholder="Please describe your issue in detail..."
          value={form.description}
          onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          required
          minLength={10}
          rows={4}
          style={{ resize: "vertical", fontFamily: "inherit" }}
        />
      </div>

      <button
        id="support-submit-btn"
        type="submit"
        className="btn-primary"
        disabled={loading}
        style={{ alignSelf: "flex-end" }}
      >
        {loading ? "Submitting…" : "Submit Ticket"}
      </button>
    </form>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function DeveloperDashboardPage() {
  const [activeTab, setActiveTab] = useState<Tab>("Billing");

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "40px 24px" }}>
      {/* Page header */}
      <div className="fade-in" style={{ marginBottom: 36 }}>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 36,
            fontWeight: 700,
            marginBottom: 8,
          }}
        >
          <span className="gradient-text">Developer</span> Dashboard
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 14 }}>
          Your billing history, GST invoices, and support tickets — in one place.
        </p>
      </div>

      {/* Tab nav */}
      <div
        className="fade-in fade-in-delay-1"
        style={{
          display: "flex",
          gap: 4,
          marginBottom: 28,
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 12,
          padding: 4,
          width: "fit-content",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab}
            id={`tab-${tab.toLowerCase()}-btn`}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "8px 20px",
              borderRadius: 9,
              border: "none",
              fontSize: 13,
              fontWeight: activeTab === tab ? 600 : 400,
              background: activeTab === tab ? "rgba(124, 58, 237, 0.2)" : "transparent",
              color: activeTab === tab ? "hsl(258, 90%, 76%)" : "var(--text-secondary)",
              cursor: "pointer",
              transition: "all 0.2s",
            }}
          >
            {tab === "Billing" && "💳 "}
            {tab === "Invoices" && "🧾 "}
            {tab === "Support" && "🎫 "}
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="fade-in fade-in-delay-2">
        {activeTab === "Billing" && <BillingHistory token={DEMO_TOKEN} />}
        {activeTab === "Invoices" && <InvoicesList token={DEMO_TOKEN} />}
        {activeTab === "Support" && <SupportForm token={DEMO_TOKEN} />}
      </div>
    </div>
  );
}
