import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Kynetic AI — Peer-to-Peer Compute Marketplace",
  description:
    "Rent GPU, CPU, and compute from verified hosts. One-click AI templates, per-second billing, mTLS security, hardware-verified nodes.",
};

// ── Intent tiles — "What do you want to run?" ──────────────────────────────

const INTENT_TILES = [
  {
    emoji: "🎨",
    title: "Stable Diffusion",
    desc: "AUTOMATIC1111 browser UI — generate images instantly",
    href: "/marketplace?template=stable-diffusion",
    accent: "hsl(258 90% 66%)",
    id: "intent-stable-diffusion",
  },
  {
    emoji: "🤖",
    title: "Llama 3 (8B)",
    desc: "OpenAI-compatible chat API, ready in 60 seconds",
    href: "/marketplace?template=llama3",
    accent: "hsl(195 100% 50%)",
    id: "intent-llama3",
  },
  {
    emoji: "🖼️",
    title: "ComfyUI",
    desc: "Node-based image pipeline editor with browser UI",
    href: "/marketplace?template=comfyui",
    accent: "hsl(142 71% 45%)",
    id: "intent-comfyui",
  },
  {
    emoji: "🦙",
    title: "Ollama",
    desc: "Run any open model via REST API — Mistral, Gemma, Phi",
    href: "/marketplace?template=ollama",
    accent: "hsl(38 95% 58%)",
    id: "intent-ollama",
  },
  {
    emoji: "🧠",
    title: "Fine-tune a Model",
    desc: "SSH into a GPU node — your environment, your control",
    href: "/marketplace?resource_type=gpu",
    accent: "hsl(328 90% 60%)",
    id: "intent-finetune",
  },
  {
    emoji: "⚡",
    title: "Raw GPU Power",
    desc: "Browse all verified GPUs — RTX 4090s, A100s, H100s",
    href: "/marketplace",
    accent: "hsl(258 60% 80%)",
    id: "intent-raw-gpu",
  },
];

const FEATURES = [
  {
    icon: "🔒",
    title: "Hardware Verified",
    desc: "Every host passes our benchmark suite and mTLS auth before listing.",
  },
  {
    icon: "⚡",
    title: "Per-Second Billing",
    desc: "No hourly minimums. Dual USD/INR wallet. Top up and go.",
  },
  {
    icon: "🛡️",
    title: "Isolated & Deleted",
    desc: "Cryptographically deleted on termination — no residual data.",
  },
  {
    icon: "🎯",
    title: "One-Click Templates",
    desc: "Stable Diffusion, Ollama, ComfyUI, Llama 3 — zero Docker required.",
  },
  {
    icon: "🌏",
    title: "Global Network",
    desc: "Verified hosts across US, EU, India and APAC.",
  },
  {
    icon: "📊",
    title: "Live Availability",
    desc: "Real-time inventory index — browse and rent in seconds.",
  },
];

export default function HomePage() {
  return (
    <div>
      {/* ── Hero ──────────────────────────────────────────────────────── */}
      <section
        style={{
          maxWidth: 960,
          margin: "0 auto",
          padding: "88px 24px 64px",
          textAlign: "center",
        }}
      >
        {/* Phase badge */}
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
          Phase 6 Live — One-Click AI Templates
        </div>

        <h1
          className="fade-in fade-in-delay-1"
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(40px, 7vw, 70px)",
            fontWeight: 800,
            lineHeight: 1.05,
            marginBottom: 24,
          }}
        >
          What do you want{" "}
          <span className="gradient-text">to run?</span>
        </h1>

        <p
          className="fade-in fade-in-delay-2"
          style={{
            color: "var(--text-secondary)",
            fontSize: 18,
            lineHeight: 1.7,
            maxWidth: 560,
            margin: "0 auto 52px",
          }}
        >
          Peer-to-peer compute for AI builders. Pick a workload below or browse
          bare GPUs. Per-second billing, verified hardware, zero lock-in.
        </p>

        {/* ── Intent tiles ──────────────────────────────────────────── */}
        <div
          className="fade-in fade-in-delay-3"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: 16,
            textAlign: "left",
            marginBottom: 40,
          }}
        >
          {INTENT_TILES.map((tile) => (
            <Link
              key={tile.id}
              href={tile.href}
              id={tile.id}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 16,
                padding: "20px 22px",
                borderRadius: 14,
                background: "var(--bg-card)",
                border: `1px solid ${tile.accent}30`,
                textDecoration: "none",
                color: "inherit",
                transition: "border-color 0.2s, background 0.2s, transform 0.15s",
                cursor: "pointer",
              }}
              className="glass-hover"
            >
              {/* Accent dot + emoji */}
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: 12,
                  background: `${tile.accent}18`,
                  border: `1px solid ${tile.accent}35`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 24,
                  flexShrink: 0,
                }}
              >
                {tile.emoji}
              </div>
              <div>
                <div
                  style={{
                    fontFamily: "var(--font-display)",
                    fontWeight: 700,
                    fontSize: 15,
                    marginBottom: 4,
                    color: "var(--text-primary)",
                  }}
                >
                  {tile.title}
                </div>
                <div
                  style={{
                    color: "var(--text-secondary)",
                    fontSize: 13,
                    lineHeight: 1.5,
                  }}
                >
                  {tile.desc}
                </div>
              </div>
              {/* Arrow */}
              <span
                style={{
                  marginLeft: "auto",
                  color: tile.accent,
                  fontSize: 18,
                  alignSelf: "center",
                  flexShrink: 0,
                }}
              >
                →
              </span>
            </Link>
          ))}
        </div>

        {/* Secondary CTAs */}
        <div
          className="fade-in fade-in-delay-3"
          style={{
            display: "flex",
            justifyContent: "center",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <Link
            href="/templates"
            className="btn-primary"
            id="cta-browse-templates"
            style={{ fontSize: 15, padding: "12px 28px" }}
          >
            All Templates →
          </Link>
          <Link
            href="/marketplace"
            className="btn-ghost"
            id="cta-browse-marketplace"
            style={{ fontSize: 15, padding: "12px 28px" }}
          >
            Browse Bare GPUs
          </Link>
          <Link
            href="/wallet"
            className="btn-ghost"
            id="cta-add-funds"
            style={{ fontSize: 15, padding: "12px 28px" }}
          >
            Add Funds
          </Link>
        </div>
      </section>

      {/* ── Feature grid ───────────────────────────────────────────────── */}
      <section
        style={{ maxWidth: 1100, margin: "0 auto", padding: "0 24px 80px" }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
            gap: 20,
          }}
        >
          {FEATURES.map((f, i) => (
            <div
              key={f.title}
              className={`glass glass-hover fade-in fade-in-delay-${(i % 3) + 1}`}
              style={{ padding: 28 }}
            >
              <div style={{ fontSize: 34, marginBottom: 14 }}>{f.icon}</div>
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
              <p
                style={{
                  color: "var(--text-secondary)",
                  fontSize: 14,
                  lineHeight: 1.6,
                }}
              >
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA banner ─────────────────────────────────────────────────── */}
      <section
        style={{ maxWidth: 820, margin: "0 auto 100px", padding: "0 24px" }}
      >
        <div
          className="glass"
          style={{
            padding: "52px 40px",
            textAlign: "center",
            background:
              "linear-gradient(135deg, hsl(258 50% 15% / 0.6), hsl(195 60% 10% / 0.4))",
            borderColor: "hsl(258 60% 45% / 0.3)",
          }}
        >
          <div style={{ fontSize: 42, marginBottom: 16 }}>🚀</div>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 30,
              fontWeight: 700,
              marginBottom: 12,
            }}
          >
            Launch your first AI workload in 60 seconds
          </h2>
          <p
            style={{
              color: "var(--text-secondary)",
              marginBottom: 28,
              fontSize: 15,
              maxWidth: 480,
              margin: "0 auto 28px",
              lineHeight: 1.6,
            }}
          >
            Add $10 to your wallet, pick a template, pick a GPU. Your instance
            is live before you finish your coffee.
          </p>
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <Link
              href="/templates"
              className="btn-primary"
              id="cta-banner-templates"
              style={{ fontSize: 15, padding: "12px 32px" }}
            >
              Browse Templates →
            </Link>
            <Link
              href="/marketplace"
              className="btn-ghost"
              id="cta-banner-marketplace"
              style={{ fontSize: 15, padding: "12px 28px" }}
            >
              Browse GPUs
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
