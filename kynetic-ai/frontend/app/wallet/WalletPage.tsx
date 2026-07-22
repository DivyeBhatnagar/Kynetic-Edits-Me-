"use client";

import { useEffect, useState } from "react";
import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from "@stripe/react-stripe-js";
import {
  Transaction,
  TransactionListResponse,
  WalletBalance,
  walletApi,
} from "@/lib/api";

// ── Mock auth token for demo ───────────────────────────────────────────────
// In production this comes from your session/cookie/JWT context
const DEMO_TOKEN = process.env.NEXT_PUBLIC_DEMO_TOKEN ?? "";

// ── Balance card ───────────────────────────────────────────────────────────

function BalanceCard({
  balance,
  onTopup,
}: {
  balance: WalletBalance | null;
  onTopup: () => void;
}) {
  const usd = balance ? parseFloat(balance.balance_usd) : null;
  const inr = balance ? parseFloat(balance.balance_inr) : null;

  return (
    <div
      className="glass"
      style={{
        padding: 32,
        background:
          "linear-gradient(135deg, hsl(258 50% 15% / 0.8), hsl(224 20% 10% / 0.6))",
        borderColor: "hsl(258 60% 45% / 0.4)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Glow orb */}
      <div
        style={{
          position: "absolute",
          top: -60,
          right: -60,
          width: 200,
          height: 200,
          borderRadius: "50%",
          background: "hsl(258 90% 66% / 0.12)",
          filter: "blur(40px)",
          pointerEvents: "none",
        }}
      />

      <div style={{ position: "relative", zIndex: 1 }}>
        <div
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            marginBottom: 12,
          }}
        >
          💳 Wallet Balance
        </div>

        {usd === null ? (
          <div>
            <div className="skeleton" style={{ height: 52, width: 200, marginBottom: 8 }} />
            <div className="skeleton" style={{ height: 18, width: 120 }} />
          </div>
        ) : (
          <>
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontSize: 52,
                fontWeight: 700,
                lineHeight: 1,
                marginBottom: 6,
                background:
                  "linear-gradient(135deg, hsl(258 90% 82%) 0%, hsl(195 100% 70%) 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              ${usd.toFixed(2)}
            </div>
            <div style={{ color: "var(--text-muted)", fontSize: 14 }}>
              ≈ ₹{(inr ?? 0).toFixed(2)} INR
            </div>
          </>
        )}

        <button
          className="btn-primary"
          onClick={onTopup}
          style={{ marginTop: 24, gap: 8 }}
        >
          ⚡ Add Funds
        </button>
      </div>
    </div>
  );
}

// ── Quick stats ────────────────────────────────────────────────────────────

function QuickStat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="glass" style={{ padding: 20, textAlign: "center" }}>
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: "var(--text-muted)",
          textTransform: "uppercase",
          letterSpacing: "0.1em",
          marginBottom: 8,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontSize: 22,
          fontWeight: 700,
          color: "var(--text-primary)",
        }}
      >
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>{sub}</div>
      )}
    </div>
  );
}

// ── Transaction row ────────────────────────────────────────────────────────

const TXN_ICONS: Record<string, string> = {
  topup: "⬆️",
  debit: "⬇️",
  refund: "↩️",
  payout: "💸",
};

const TXN_COLORS: Record<string, string> = {
  topup: "var(--status-available)",
  debit: "var(--status-offline)",
  refund: "hsl(45 93% 58%)",
  payout: "hsl(195 100% 50%)",
};

function TransactionRow({ txn }: { txn: Transaction }) {
  const amount = parseFloat(txn.amount);
  const isCredit = txn.transaction_type === "topup" || txn.transaction_type === "refund";
  const date = new Date(txn.created_at);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "14px 0",
        borderBottom: "1px solid var(--border-subtle)",
        transition: "background 0.15s ease",
      }}
    >
      {/* Icon */}
      <div
        style={{
          width: 38,
          height: 38,
          borderRadius: 10,
          background: `${TXN_COLORS[txn.transaction_type] ?? "var(--brand-primary)"}22`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 16,
          flexShrink: 0,
          border: `1px solid ${TXN_COLORS[txn.transaction_type] ?? "var(--brand-primary)"}44`,
        }}
      >
        {TXN_ICONS[txn.transaction_type] ?? "💱"}
      </div>

      {/* Description */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 14,
            fontWeight: 500,
            color: "var(--text-primary)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {txn.description ?? txn.transaction_type.charAt(0).toUpperCase() + txn.transaction_type.slice(1)}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
          {date.toLocaleDateString()} · {date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          {txn.stripe_payment_intent_id && (
            <span style={{ marginLeft: 8, fontFamily: "var(--font-mono)", fontSize: 10 }}>
              {txn.stripe_payment_intent_id.slice(0, 18)}…
            </span>
          )}
        </div>
      </div>

      {/* Amount */}
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div
          style={{
            fontSize: 15,
            fontWeight: 700,
            color: TXN_COLORS[txn.transaction_type] ?? "var(--text-primary)",
          }}
        >
          {isCredit ? "+" : "-"}${amount.toFixed(2)}
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
          bal: ${parseFloat(txn.balance_after_usd).toFixed(2)}
        </div>
      </div>
    </div>
  );
}

// ── Stripe top-up form ─────────────────────────────────────────────────────

function TopupForm({
  clientSecret,
  onSuccess,
  onCancel,
}: {
  clientSecret: string;
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!stripe || !elements) return;

    setLoading(true);
    setError(null);

    const { error: stripeError } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: window.location.href },
      redirect: "if_required",
    });

    if (stripeError) {
      setError(stripeError.message ?? "Payment failed");
      setLoading(false);
    } else {
      onSuccess();
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <div
        style={{
          padding: "16px",
          borderRadius: 10,
          background: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          marginBottom: 16,
        }}
      >
        <PaymentElement
          options={{
            layout: "tabs",
          }}
        />
      </div>

      {error && (
        <div
          style={{
            padding: "10px 14px",
            borderRadius: 8,
            background: "hsl(0 72% 51% / 0.12)",
            border: "1px solid hsl(0 72% 51% / 0.3)",
            color: "var(--status-offline)",
            fontSize: 13,
            marginBottom: 12,
          }}
        >
          ⚠️ {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 10 }}>
        <button
          type="button"
          className="btn-ghost"
          onClick={onCancel}
          style={{ flex: 1 }}
          disabled={loading}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="btn-primary"
          style={{ flex: 2 }}
          disabled={!stripe || loading}
        >
          {loading ? "Processing…" : "Confirm Payment"}
        </button>
      </div>
    </form>
  );
}

// ── Top-up modal ───────────────────────────────────────────────────────────

function TopupModal({
  open,
  onClose,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [amount, setAmount] = useState<number>(25);
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [stripeKey, setStripeKey] = useState<string | null>(null);
  const [creatingIntent, setCreatingIntent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const PRESETS = [10, 25, 50, 100];

  const handleCreateIntent = async () => {
    setCreatingIntent(true);
    setError(null);
    try {
      const res = await walletApi.topup(DEMO_TOKEN, amount);
      setClientSecret(res.client_secret);
      setStripeKey(res.stripe_publishable_key);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create payment intent");
    } finally {
      setCreatingIntent(false);
    }
  };

  const handleSuccess = () => {
    setSuccess(true);
    setTimeout(() => {
      onSuccess();
      onClose();
    }, 1500);
  };

  if (!open) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "hsl(0 0% 0% / 0.6)",
        backdropFilter: "blur(6px)",
        padding: 24,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="glass"
        style={{
          width: "100%",
          maxWidth: 480,
          padding: 32,
          animation: "fadeIn 0.2s ease",
        }}
      >
        {success ? (
          <div style={{ textAlign: "center", padding: "20px 0" }}>
            <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
            <h3 style={{ fontFamily: "var(--font-display)", fontSize: 20, marginBottom: 8 }}>
              Payment Successful!
            </h3>
            <p style={{ color: "var(--text-secondary)" }}>
              Your wallet has been credited with ${amount.toFixed(2)}.
            </p>
          </div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
              <h2 style={{ fontFamily: "var(--font-display)", fontSize: 20 }}>Add Funds</h2>
              <button
                onClick={onClose}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--text-muted)",
                  fontSize: 20,
                  cursor: "pointer",
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>

            {!clientSecret ? (
              <>
                {/* Amount presets */}
                <div style={{ marginBottom: 16 }}>
                  <label style={{ fontSize: 13, color: "var(--text-secondary)", display: "block", marginBottom: 8 }}>
                    Select Amount (USD)
                  </label>
                  <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                    {PRESETS.map((p) => (
                      <button
                        key={p}
                        onClick={() => setAmount(p)}
                        style={{
                          flex: 1,
                          padding: "9px 0",
                          borderRadius: 8,
                          border: amount === p
                            ? "1px solid hsl(258 90% 66% / 0.5)"
                            : "1px solid var(--border-subtle)",
                          background: amount === p
                            ? "hsl(258 90% 66% / 0.12)"
                            : "var(--bg-surface)",
                          color: amount === p ? "hsl(258 90% 76%)" : "var(--text-secondary)",
                          fontSize: 14,
                          fontWeight: 600,
                          cursor: "pointer",
                          transition: "all 0.15s ease",
                        }}
                      >
                        ${p}
                      </button>
                    ))}
                  </div>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    value={amount}
                    onChange={(e) => setAmount(Number(e.target.value))}
                    placeholder="Custom amount"
                  />
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6 }}>
                    ≈ ₹{(amount * 84).toFixed(0)} INR
                  </div>
                </div>

                {error && (
                  <div style={{ color: "var(--status-offline)", fontSize: 13, marginBottom: 12 }}>
                    ⚠️ {error}
                  </div>
                )}

                <button
                  className="btn-primary"
                  style={{ width: "100%" }}
                  onClick={handleCreateIntent}
                  disabled={creatingIntent || amount < 1}
                >
                  {creatingIntent ? "Creating payment…" : `Continue with $${amount}`}
                </button>
              </>
            ) : (
              stripeKey && (
                <Elements
                  stripe={loadStripe(stripeKey)}
                  options={{
                    clientSecret,
                    appearance: {
                      theme: "night",
                      variables: {
                        colorPrimary: "hsl(258, 90%, 66%)",
                        colorBackground: "hsl(224, 20%, 13%)",
                        colorText: "hsl(220, 15%, 95%)",
                        borderRadius: "10px",
                        fontFamily: "Inter, sans-serif",
                      },
                    },
                  }}
                >
                  <TopupForm
                    clientSecret={clientSecret}
                    onSuccess={handleSuccess}
                    onCancel={() => setClientSecret(null)}
                  />
                </Elements>
              )
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Main Wallet page ───────────────────────────────────────────────────────

export default function WalletPage() {
  const [balance, setBalance] = useState<WalletBalance | null>(null);
  const [txns, setTxns] = useState<TransactionListResponse | null>(null);
  const [txnPage, setTxnPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [showTopup, setShowTopup] = useState(false);

  const fetchData = async (page = 1) => {
    try {
      const [b, t] = await Promise.all([
        walletApi.getBalance(DEMO_TOKEN),
        walletApi.getTransactions(DEMO_TOKEN, page),
      ]);
      setBalance(b);
      setTxns(t);
    } catch {
      // In a real app, redirect to login if 401
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(txnPage);
  }, [txnPage]);

  const totalSpent = txns?.items
    .filter((t) => t.transaction_type === "debit")
    .reduce((sum, t) => sum + parseFloat(t.amount), 0) ?? 0;

  const totalTopups = txns?.items
    .filter((t) => t.transaction_type === "topup")
    .reduce((sum, t) => sum + parseFloat(t.amount), 0) ?? 0;

  return (
    <>
      <TopupModal
        open={showTopup}
        onClose={() => setShowTopup(false)}
        onSuccess={() => fetchData(1)}
      />

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "40px 24px" }}>
        {/* Header */}
        <div className="fade-in" style={{ marginBottom: 32 }}>
          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 36,
              fontWeight: 700,
              marginBottom: 8,
            }}
          >
            <span className="gradient-text">Wallet</span>
          </h1>
          <p style={{ color: "var(--text-secondary)" }}>
            Manage your compute credits — dual USD/INR support.
          </p>
        </div>

        {/* Balance + stats row */}
        <div
          className="fade-in fade-in-delay-1"
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 18, marginBottom: 28 }}
        >
          <div style={{ gridColumn: "1 / 2" }}>
            <BalanceCard balance={balance} onTopup={() => setShowTopup(true)} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <QuickStat
              label="Total Spent"
              value={`$${totalSpent.toFixed(2)}`}
              sub="on compute"
            />
            <QuickStat
              label="Top-ups"
              value={`$${totalTopups.toFixed(2)}`}
              sub="added this period"
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <QuickStat
              label="Transactions"
              value={String(txns?.total ?? "—")}
              sub="all time"
            />
            <QuickStat
              label="Currency"
              value={balance?.preferred_currency?.toUpperCase() ?? "USD"}
              sub="preferred"
            />
          </div>
        </div>

        {/* Transaction history */}
        <div className="fade-in fade-in-delay-2 glass" style={{ padding: 28 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 20,
            }}
          >
            <h2
              style={{
                fontFamily: "var(--font-display)",
                fontSize: 16,
                fontWeight: 600,
              }}
            >
              Transaction History
            </h2>
            <button
              className="btn-ghost"
              onClick={() => fetchData(txnPage)}
              style={{ fontSize: 13 }}
            >
              ↻ Refresh
            </button>
          </div>

          {loading && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0" }}>
                  <div className="skeleton" style={{ width: 38, height: 38, borderRadius: 10, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <div className="skeleton" style={{ height: 14, width: "60%", marginBottom: 6 }} />
                    <div className="skeleton" style={{ height: 11, width: "35%" }} />
                  </div>
                  <div className="skeleton" style={{ height: 20, width: 70 }} />
                </div>
              ))}
            </div>
          )}

          {!loading && txns?.items.length === 0 && (
            <div style={{ textAlign: "center", padding: "48px 20px" }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>💰</div>
              <h3 style={{ fontFamily: "var(--font-display)", fontSize: 18, marginBottom: 8 }}>
                No transactions yet
              </h3>
              <p style={{ color: "var(--text-secondary)", marginBottom: 20 }}>
                Add funds to your wallet to start renting compute.
              </p>
              <button className="btn-primary" onClick={() => setShowTopup(true)}>
                ⚡ Add Funds
              </button>
            </div>
          )}

          {!loading && txns && txns.items.length > 0 && (
            <>
              <div>
                {txns.items.map((txn) => (
                  <TransactionRow key={txn.id} txn={txn} />
                ))}
              </div>

              {/* Pagination */}
              {Math.ceil(txns.total / txns.page_size) > 1 && (
                <div
                  style={{
                    marginTop: 20,
                    display: "flex",
                    justifyContent: "center",
                    gap: 8,
                    alignItems: "center",
                  }}
                >
                  <button
                    className="btn-ghost"
                    disabled={txnPage === 1}
                    onClick={() => setTxnPage((p) => p - 1)}
                  >
                    ← Prev
                  </button>
                  <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>
                    Page {txns.page} / {Math.ceil(txns.total / txns.page_size)}
                  </span>
                  <button
                    className="btn-ghost"
                    disabled={txnPage >= Math.ceil(txns.total / txns.page_size)}
                    onClick={() => setTxnPage((p) => p + 1)}
                  >
                    Next →
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
