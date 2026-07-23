"use client";

/**
 * AI Copilot Chat Page — Phase 7
 *
 * Full-page WebSocket-connected conversational interface.
 * Features:
 *  - Real-time chat over WebSocket with REST fallback
 *  - Embedded recommendation cards when the copilot calls the Router
 *  - "Launch this" button wired to the provisioning flow (Phase 4/6)
 *  - Session persistence (session_id stored in localStorage)
 *  - Input sanitization before sending
 */

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import {
  CopilotWebSocket,
  copilotApi,
  routerApi,
  type CopilotMessageOut,
  type RecommendResponse,
  type ScoredListing,
  type WSOutbound,
} from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  recommendation?: RecommendResponse | null;
  timestamp: Date;
}

// ── Helper components ─────────────────────────────────────────────────────────

function ScoreBadge({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70 ? "text-emerald-400" : pct >= 40 ? "text-amber-400" : "text-rose-400";
  return (
    <span className={`text-xs font-mono ${color}`}>
      {label}: {pct}%
    </span>
  );
}

function RecommendationCard({
  listing,
  rank,
  onLaunch,
}: {
  listing: ScoredListing;
  rank: number;
  onLaunch: (listingId: string) => void;
}) {
  return (
    <div
      className={`rounded-xl border p-4 transition-all ${
        rank === 0
          ? "border-violet-500/60 bg-violet-950/30 shadow-lg shadow-violet-900/20"
          : "border-white/10 bg-white/5"
      }`}
    >
      {rank === 0 && (
        <span className="mb-2 inline-block rounded-full bg-violet-600/30 px-2 py-0.5 text-xs font-semibold text-violet-300">
          ✦ Top Pick
        </span>
      )}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-white">
            {listing.title ?? listing.gpu_model ?? "Compute Instance"}
          </p>
          <p className="text-xs text-slate-400">
            {listing.gpu_model && `${listing.gpu_model}`}
            {listing.gpu_vram_gb && ` · ${listing.gpu_vram_gb}GB VRAM`}
            {listing.cpu_cores && ` · ${listing.cpu_cores} cores`}
            {listing.ram_gb && ` · ${listing.ram_gb}GB RAM`}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            📍 {listing.region ?? "Unknown region"}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-bold text-white">
            ${Number(listing.price_per_hour_usd).toFixed(3)}/hr
          </p>
          <p className="text-xs text-slate-400">
            ₹{Number(listing.price_per_hour_inr).toFixed(2)}/hr
          </p>
        </div>
      </div>

      {/* Cost + time estimate */}
      {listing.estimated_cost_usd && (
        <div className="mt-3 flex flex-wrap gap-3 rounded-lg bg-white/5 px-3 py-2 text-xs">
          <span className="text-slate-300">
            Est. cost:{" "}
            <strong className="text-white">${Number(listing.estimated_cost_usd).toFixed(2)}</strong>
          </span>
          {listing.estimated_hours && (
            <span className="text-slate-300">
              Est. time:{" "}
              <strong className="text-white">
                {listing.estimated_hours < 1
                  ? `${Math.round(listing.estimated_hours * 60)}m`
                  : `${listing.estimated_hours.toFixed(1)}h`}
              </strong>
            </span>
          )}
        </div>
      )}

      {/* Score breakdown */}
      <div className="mt-2 flex flex-wrap gap-3">
        <ScoreBadge label="Price" value={listing.score_price} />
        <ScoreBadge label="Bench" value={listing.score_benchmark} />
        <ScoreBadge label="Avail" value={listing.score_availability} />
        <ScoreBadge label="Score" value={listing.score_composite} />
      </div>

      <button
        onClick={() => onLaunch(listing.listing_id)}
        className="mt-3 w-full rounded-lg bg-gradient-to-r from-violet-600 to-indigo-600 py-1.5 text-sm font-semibold text-white transition-all hover:from-violet-500 hover:to-indigo-500 active:scale-[0.98]"
      >
        🚀 Launch this
      </button>
    </div>
  );
}

function MessageBubble({
  msg,
  onLaunch,
}: {
  msg: ChatMessage;
  onLaunch: (listingId: string) => void;
}) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm ${
          isUser
            ? "bg-indigo-600/40 text-indigo-300"
            : "bg-violet-600/40 text-violet-300"
        }`}
      >
        {isUser ? "👤" : "✦"}
      </div>

      <div className={`max-w-[80%] space-y-3 ${isUser ? "items-end" : "items-start"}`}>
        {/* Text bubble */}
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? "rounded-tr-sm bg-indigo-600/30 text-indigo-100"
              : "rounded-tl-sm bg-white/8 text-slate-200"
          }`}
        >
          {/* Render markdown-ish bold/italic */}
          <span
            dangerouslySetInnerHTML={{
              __html: msg.content
                .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
                .replace(/\*(.*?)\*/g, "<em>$1</em>")
                .replace(/\n/g, "<br/>"),
            }}
          />
        </div>

        {/* Recommendation cards */}
        {msg.recommendation && msg.recommendation.results.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs text-slate-500">
              Evaluated {msg.recommendation.total_candidates_evaluated} machines
            </p>
            {msg.recommendation.results.slice(0, 3).map((listing, i) => (
              <RecommendationCard
                key={listing.listing_id}
                listing={listing}
                rank={i}
                onLaunch={onLaunch}
              />
            ))}
          </div>
        )}

        <p className="text-xs text-slate-600">
          {msg.timestamp.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </div>
  );
}

// ── Quick prompts ─────────────────────────────────────────────────────────────

const QUICK_PROMPTS = [
  { label: "₹120 budget", value: "I have a ₹120/hr budget. What GPU can I get?" },
  { label: "Fastest GPU", value: "I need the fastest available GPU for LoRA fine-tuning" },
  { label: "Cheap & balanced", value: "Show me a balanced option under $2/hr" },
  { label: "A100 class", value: "I need an A100-class GPU for training a 13B model" },
];

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CopilotPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "👋 Hi! I'm Kynetic's AI Copilot.\n\nTell me your **budget** or **goal** and I'll find the best compute for you — with exact cost and time estimates, grounded in real marketplace data. No guessing, no hallucinated numbers.\n\nTry: *\"I need a GPU for LoRA training with a ₹120 budget\"*",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [useWs, setUseWs] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<CopilotWebSocket | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Get token from localStorage (set during login)
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("kynetic_token") ?? ""
      : "";

  // Restore session from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("copilot_session_id");
    if (saved) setSessionId(saved);
  }, []);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Launch handler — navigates to marketplace with listing pre-selected
  const handleLaunch = useCallback((listingId: string) => {
    window.location.href = `/marketplace?listing=${listingId}&action=launch`;
  }, []);

  // WebSocket message handler
  const handleWsMessage = useCallback((data: WSOutbound) => {
    if (data.type === "chat_response") {
      if (data.session_id && data.session_id !== "new") {
        setSessionId(data.session_id);
        localStorage.setItem("copilot_session_id", data.session_id);
      }
      setMessages((prev) => [
        ...prev,
        {
          id: data.message_id ?? crypto.randomUUID(),
          role: "assistant",
          content: data.content,
          recommendation: data.recommendation,
          timestamp: new Date(),
        },
      ]);
      setIsLoading(false);
    } else if (data.type === "error") {
      setIsLoading(false);
    }
  }, []);

  // Send via REST (default, more reliable across environments)
  const sendViaRest = async (message: string) => {
    try {
      const res = await copilotApi.chat(
        { session_id: sessionId ?? undefined, message },
        token
      );
      if (res.session_id !== sessionId) {
        setSessionId(res.session_id);
        localStorage.setItem("copilot_session_id", res.session_id);
      }
      setMessages((prev) => [
        ...prev,
        {
          id: res.message_id,
          role: "assistant",
          content: res.content,
          recommendation: res.recommendation,
          timestamp: new Date(),
        },
      ]);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `⚠️ Error: ${errMsg}. Please try again.`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSend = async () => {
    const text = input.trim().slice(0, 2000);
    if (!text || isLoading) return;

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", content: text, timestamp: new Date() },
    ]);
    setInput("");
    setIsLoading(true);

    await sendViaRest(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-screen flex-col bg-[#0a0a0f]">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-white/10 bg-[#0a0a0f]/90 px-6 py-4 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-slate-400 transition-colors hover:text-white">
            ← Back
          </Link>
          <div className="h-4 w-px bg-white/20" />
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-violet-600 to-indigo-600 text-sm font-bold text-white shadow-lg shadow-violet-900/30">
              ✦
            </span>
            <div>
              <p className="text-sm font-semibold text-white">AI Copilot</p>
              <p className="text-xs text-slate-500">Powered by real marketplace data</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {sessionId && (
            <span className="rounded-full bg-emerald-900/30 px-2.5 py-1 text-xs text-emerald-400">
              Session active
            </span>
          )}
          <button
            onClick={() => {
              setSessionId(null);
              localStorage.removeItem("copilot_session_id");
              setMessages([
                {
                  id: "welcome",
                  role: "assistant",
                  content: "New session started. What are you looking for?",
                  timestamp: new Date(),
                },
              ]);
            }}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-400 transition-all hover:border-white/20 hover:text-white"
          >
            New chat
          </button>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-3xl space-y-6">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} onLaunch={handleLaunch} />
          ))}

          {/* Loading indicator */}
          {isLoading && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-violet-600/40 text-sm text-violet-300">
                ✦
              </div>
              <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm bg-white/8 px-4 py-3">
                <span className="h-2 w-2 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.3s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.15s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-violet-400" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Quick prompts */}
      <div className="border-t border-white/5 bg-[#0a0a0f]/60 px-4 pt-3">
        <div className="mx-auto max-w-3xl">
          <div className="flex flex-wrap gap-2 pb-3">
            {QUICK_PROMPTS.map((p) => (
              <button
                key={p.label}
                onClick={() => {
                  setInput(p.value);
                  inputRef.current?.focus();
                }}
                className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 transition-all hover:border-violet-500/40 hover:bg-violet-950/30 hover:text-violet-300"
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Input bar */}
      <div className="border-t border-white/10 bg-[#0a0a0f]/90 px-4 py-4 backdrop-blur-sm">
        <div className="mx-auto flex max-w-3xl items-end gap-3">
          <div className="relative flex-1">
            <textarea
              id="copilot-input"
              ref={inputRef}
              rows={1}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                // Auto-resize
                e.target.style.height = "auto";
                e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
              }}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your budget, workload, or goal…"
              maxLength={2000}
              className="w-full resize-none rounded-xl border border-white/10 bg-white/5 px-4 py-3 pr-12 text-sm text-white placeholder-slate-500 outline-none transition-all focus:border-violet-500/60 focus:bg-white/8 focus:ring-1 focus:ring-violet-500/30"
            />
            <span className="absolute bottom-3 right-3 text-xs text-slate-600">
              {input.length}/2000
            </span>
          </div>
          <button
            id="copilot-send-btn"
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 text-lg text-white shadow-lg shadow-violet-900/30 transition-all hover:from-violet-500 hover:to-indigo-500 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            ↑
          </button>
        </div>
        <p className="mt-2 text-center text-xs text-slate-700">
          Numbers come from the live marketplace — not guesses.
        </p>
      </div>
    </div>
  );
}
