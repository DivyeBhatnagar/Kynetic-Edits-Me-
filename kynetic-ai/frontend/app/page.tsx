import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Kynetic AI — Peer-to-Peer Compute Marketplace",
  description:
    "Rent GPU, CPU, and compute from verified hosts. Per-second billing, mTLS security, hardware-verified nodes.",
};

export default function HomePage() {
  const features = [
    {
      icon: "🎮",
      title: "GPU-First",
      desc: "RTX 4090s, A100s, H100s — rent exactly the GPU you need, by the second.",
    },
    {
      icon: "🔒",
      title: "Hardware Verified",
      desc: "Every host passes our benchmark suite and mTLS authentication before listing.",
    },
    {
      icon: "⚡",
      title: "Per-Second Billing",
      desc: "No hourly minimums. Dual USD/INR wallet. Top up and go.",
    },
    {
      icon: "🛡️",
      title: "Isolated Containers",
      desc: "Your workload runs in an isolated environment — cryptographically deleted on termination.",
    },
    {
      icon: "🌏",
      title: "Global Network",
      desc: "Hosts across US, EU, India and APAC. Low-latency routing coming in Phase 7.",
    },
    {
      icon: "📊",
      title: "Real-Time Availability",
      desc: "Live availability index — no stale listings. Browse and rent in seconds.",
    },
  ];

  return (
    <div>
      {/* Hero */}
      <section
        style={{
          maxWidth: 900,
          margin: "0 auto",
          padding: "100px 24px 80px",
          textAlign: "center",
        }}
      >
        <div
          className="fade-in"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 16px",
            borderRadius: 99,
            background: "hsl(258 90% 66% / 0.1)",
            border: "1px solid hsl(258 90% 66% / 0.3)",
            fontSize: 13,
            color: "hsl(258 90% 76%)",
            marginBottom: 28,
            fontWeight: 500,
          }}
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: "hsl(258 90% 66%)",
              display: "inline-block",
              boxShadow: "0 0 6px hsl(258 90% 66%)",
            }}
            className="pulse-dot"
          />
          Now in Phase 3 — Marketplace Live
        </div>

        <h1
          className="fade-in fade-in-delay-1"
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 64,
            fontWeight: 800,
            lineHeight: 1.05,
            marginBottom: 24,
          }}
        >
          Peer-to-Peer{" "}
          <span className="gradient-text">Compute</span>
          {" "}for AI Builders
        </h1>

        <p
          className="fade-in fade-in-delay-2"
          style={{
            color: "var(--text-secondary)",
            fontSize: 18,
            lineHeight: 1.7,
            maxWidth: 580,
            margin: "0 auto 40px",
          }}
        >
          Rent verified GPU, CPU, and RAM by the second. No subscription. No lock-in.
          Powered by hardware-verified hosts and mTLS security.
        </p>

        <div
          className="fade-in fade-in-delay-3"
          style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap" }}
        >
          <Link href="/marketplace" className="btn-primary" style={{ fontSize: 15, padding: "12px 28px" }}>
            Browse Compute →
          </Link>
          <Link href="/wallet" className="btn-ghost" style={{ fontSize: 15, padding: "12px 28px" }}>
            Add Funds
          </Link>
        </div>
      </section>

      {/* Feature grid */}
      <section
        style={{ maxWidth: 1100, margin: "0 auto", padding: "0 24px 100px" }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
            gap: 20,
          }}
        >
          {features.map((f, i) => (
            <div
              key={f.title}
              className={`glass glass-hover fade-in fade-in-delay-${(i % 3) + 1}`}
              style={{ padding: 28 }}
            >
              <div style={{ fontSize: 36, marginBottom: 14 }}>{f.icon}</div>
              <h3
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: 17,
                  fontWeight: 600,
                  marginBottom: 8,
                }}
              >
                {f.title}
              </h3>
              <p style={{ color: "var(--text-secondary)", fontSize: 14, lineHeight: 1.6 }}>
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA banner */}
      <section style={{ maxWidth: 800, margin: "0 auto 100px", padding: "0 24px" }}>
        <div
          className="glass"
          style={{
            padding: "48px 40px",
            textAlign: "center",
            background:
              "linear-gradient(135deg, hsl(258 50% 15% / 0.6), hsl(195 60% 10% / 0.4))",
            borderColor: "hsl(258 60% 45% / 0.3)",
          }}
        >
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 32,
              fontWeight: 700,
              marginBottom: 12,
            }}
          >
            Ready to rent your first GPU?
          </h2>
          <p style={{ color: "var(--text-secondary)", marginBottom: 28, fontSize: 15 }}>
            Add $10 to your wallet and rent a verified RTX 4090 in under 60 seconds.
          </p>
          <Link href="/marketplace" className="btn-primary" style={{ fontSize: 15, padding: "12px 32px" }}>
            Browse the Marketplace →
          </Link>
        </div>
      </section>
    </div>
  );
}
