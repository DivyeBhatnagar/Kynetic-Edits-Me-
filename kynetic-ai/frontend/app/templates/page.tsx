"use client";

/**
 * Template Gallery — /templates
 *
 * Displays all available one-click AI workload launch templates.
 * Fetches live from /templates (public endpoint, no auth required).
 * One-click launch navigates to /marketplace?template={slug}.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { templatesApi, type Template } from "@/lib/api";

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    templatesApi
      .list()
      .then((res) => setTemplates(res.items))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "64px 24px 100px" }}>
      {/* Header */}
      <div className="fade-in" style={{ textAlign: "center", marginBottom: 64 }}>
        <div
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
            marginBottom: 24,
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
          />
          Phase 6 — One-Click AI Launch
        </div>

        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 52,
            fontWeight: 800,
            lineHeight: 1.05,
            marginBottom: 20,
          }}
        >
          Zero-Setup{" "}
          <span className="gradient-text">AI Templates</span>
        </h1>
        <p
          style={{
            color: "var(--text-secondary)",
            fontSize: 18,
            maxWidth: 560,
            margin: "0 auto",
            lineHeight: 1.7,
          }}
        >
          Pick a workload, pick a machine, launch. No Docker knowledge required.
          Every template is pre-scanned, pre-configured, and ready in seconds.
        </p>
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: "center", padding: 60 }}>
          <div
            style={{
              width: 40,
              height: 40,
              border: "3px solid var(--border-subtle)",
              borderTopColor: "var(--brand-primary)",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
              margin: "0 auto 16px",
            }}
          />
          <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
            Loading templates…
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div
          className="glass"
          style={{
            padding: "24px 28px",
            borderColor: "hsl(0 72% 51% / 0.4)",
            background: "hsl(0 72% 10% / 0.4)",
            textAlign: "center",
            maxWidth: 480,
            margin: "0 auto",
          }}
        >
          <p style={{ color: "hsl(0 72% 70%)", fontSize: 14 }}>
            Could not load templates — using demo data. {error}
          </p>
        </div>
      )}

      {/* Template grid */}
      {!loading && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
            gap: 24,
          }}
        >
          {(templates.length > 0 ? templates : DEMO_TEMPLATES).map(
            (tpl, i) => (
              <TemplateCard key={tpl.id} template={tpl} index={i} />
            )
          )}
        </div>
      )}

      {/* Trust strip */}
      <div
        style={{
          marginTop: 72,
          padding: "32px",
          textAlign: "center",
          borderTop: "1px solid var(--border-subtle)",
        }}
      >
        <p
          style={{
            color: "var(--text-muted)",
            fontSize: 13,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 24,
            flexWrap: "wrap",
          }}
        >
          <span>🔒 Every image scanned before launch</span>
          <span>⚡ Per-second billing — no minimums</span>
          <span>🗑️ Cryptographically deleted on termination</span>
          <span>🔑 SSH access included</span>
        </p>
      </div>
    </div>
  );
}

// ── Template Card ───────────────────────────────────────────────────────────

function TemplateCard({
  template: tpl,
  index,
}: {
  template: Template;
  index: number;
}) {
  const hasWebUI = !!tpl.web_ui_port;
  const delayClass = `fade-in-delay-${(index % 3) + 1}`;

  return (
    <div
      className={`glass glass-hover fade-in ${delayClass}`}
      style={{
        padding: 28,
        display: "flex",
        flexDirection: "column",
        gap: 0,
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Subtle gradient accent top */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 2,
          background:
            "linear-gradient(90deg, var(--brand-primary), var(--brand-secondary))",
          opacity: 0.6,
        }}
      />

      {/* Icon + badges */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <span style={{ fontSize: 40 }}>{tpl.icon_emoji}</span>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {hasWebUI && (
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                padding: "3px 10px",
                borderRadius: 99,
                background: "hsl(195 100% 50% / 0.12)",
                border: "1px solid hsl(195 100% 50% / 0.3)",
                color: "hsl(195 100% 65%)",
                letterSpacing: "0.05em",
                textTransform: "uppercase",
              }}
            >
              Web UI
            </span>
          )}
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              padding: "3px 10px",
              borderRadius: 99,
              background: "hsl(142 71% 45% / 0.12)",
              border: "1px solid hsl(142 71% 45% / 0.3)",
              color: "hsl(142 71% 60%)",
              letterSpacing: "0.05em",
              textTransform: "uppercase",
            }}
          >
            Verified
          </span>
        </div>
      </div>

      {/* Name + description */}
      <h2
        style={{
          fontFamily: "var(--font-display)",
          fontSize: 20,
          fontWeight: 700,
          marginBottom: 10,
        }}
      >
        {tpl.name}
      </h2>
      <p
        style={{
          color: "var(--text-secondary)",
          fontSize: 14,
          lineHeight: 1.65,
          marginBottom: 20,
          flexGrow: 1,
        }}
      >
        {tpl.description}
      </p>

      {/* Spec requirements */}
      <div
        style={{
          display: "flex",
          gap: 10,
          flexWrap: "wrap",
          marginBottom: 20,
        }}
      >
        {tpl.required_gpu_vram_gb && (
          <SpecBadge icon="🎮" label={`${tpl.required_gpu_vram_gb} GB VRAM`} />
        )}
        <SpecBadge icon="🧠" label={`${tpl.required_ram_gb} GB RAM`} />
        <SpecBadge icon="⚙️" label={`${tpl.required_vcpus} vCPU`} />
        {hasWebUI && (
          <SpecBadge icon="🌐" label={`Port ${tpl.web_ui_port}`} />
        )}
      </div>

      {/* Tags */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 20 }}>
        {tpl.tags.slice(0, 4).map((tag) => (
          <span
            key={tag}
            style={{
              fontSize: 11,
              padding: "2px 8px",
              borderRadius: 4,
              background: "var(--bg-elevated)",
              color: "var(--text-muted)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {tag}
          </span>
        ))}
      </div>

      {/* Launch CTA */}
      <Link
        href={`/marketplace?template=${tpl.slug}`}
        className="btn-primary"
        style={{
          textAlign: "center",
          fontSize: 14,
          padding: "11px 20px",
          display: "block",
        }}
        id={`launch-template-${tpl.slug}`}
      >
        Launch {tpl.name} →
      </Link>
    </div>
  );
}

// ── Spec Badge ──────────────────────────────────────────────────────────────

function SpecBadge({ icon, label }: { icon: string; label: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        fontSize: 12,
        padding: "4px 10px",
        borderRadius: 6,
        background: "var(--bg-elevated)",
        border: "1px solid var(--border-subtle)",
        color: "var(--text-secondary)",
        fontWeight: 500,
      }}
    >
      {icon} {label}
    </span>
  );
}

// ── Demo Templates (fallback when API is unavailable) ───────────────────────

const DEMO_TEMPLATES: Template[] = [
  {
    id: "10000000-0000-0000-0000-000000000001",
    name: "Stable Diffusion WebUI",
    slug: "stable-diffusion",
    description:
      "AUTOMATIC1111 Stable Diffusion Web UI. Generate images via a full browser interface — no coding required. Supports SD 1.5, SD XL, ControlNet, LoRA, and more.",
    icon_emoji: "🎨",
    tags: ["image-gen", "stable-diffusion", "webui", "gpu"],
    base_image: "ghcr.io/lllyasviel/stable-diffusion-webui:latest",
    required_gpu_vram_gb: 8,
    required_ram_gb: 16,
    required_vcpus: 4,
    startup_command: "python webui.py --listen --port 7860",
    default_ssh_user: "kynetic",
    exposed_web_ui_path: "/",
    web_ui_port: 7860,
    status: "available",
    created_at: new Date().toISOString(),
  },
  {
    id: "10000000-0000-0000-0000-000000000002",
    name: "Ollama",
    slug: "ollama",
    description:
      "Run large language models locally via the Ollama API. OpenAI-compatible REST API on port 11434. Pull and run Llama 3, Mistral, Gemma, Phi-3, and many more.",
    icon_emoji: "🦙",
    tags: ["llm", "ollama", "api", "gpu"],
    base_image: "ollama/ollama:latest",
    required_gpu_vram_gb: 4,
    required_ram_gb: 8,
    required_vcpus: 2,
    startup_command: "ollama serve",
    default_ssh_user: "kynetic",
    exposed_web_ui_path: null,
    web_ui_port: null,
    status: "available",
    created_at: new Date().toISOString(),
  },
  {
    id: "10000000-0000-0000-0000-000000000003",
    name: "ComfyUI",
    slug: "comfyui",
    description:
      "ComfyUI — the most powerful node-based Stable Diffusion interface. Build complex image and video generation pipelines visually. Full browser UI accessible via secure link.",
    icon_emoji: "🖼️",
    tags: ["image-gen", "comfyui", "nodes", "webui", "gpu"],
    base_image: "ghcr.io/comfyanonymous/comfyui:latest",
    required_gpu_vram_gb: 8,
    required_ram_gb: 16,
    required_vcpus: 4,
    startup_command: "python main.py --listen 0.0.0.0 --port 8188",
    default_ssh_user: "kynetic",
    exposed_web_ui_path: "/",
    web_ui_port: 8188,
    status: "available",
    created_at: new Date().toISOString(),
  },
  {
    id: "10000000-0000-0000-0000-000000000004",
    name: "Llama 3 (8B)",
    slug: "llama3",
    description:
      "Meta Llama 3 8B Instruct, served via Ollama. OpenAI-compatible chat completions API on port 11434. Ready to use immediately after launch — model pre-pulled.",
    icon_emoji: "🤖",
    tags: ["llm", "llama3", "meta", "api", "gpu"],
    base_image: "ollama/ollama:latest",
    required_gpu_vram_gb: 8,
    required_ram_gb: 16,
    required_vcpus: 4,
    startup_command:
      "bash -c 'ollama serve & sleep 5 && ollama pull llama3:8b && wait'",
    default_ssh_user: "kynetic",
    exposed_web_ui_path: null,
    web_ui_port: null,
    status: "available",
    created_at: new Date().toISOString(),
  },
];
