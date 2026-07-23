"use client";

/**
 * Recommendation Results Component — Phase 7
 *
 * Standalone component for displaying AI Router results.
 * Can be embedded anywhere in the app (marketplace, copilot, etc.)
 *
 * Props:
 *  recommendation — RecommendResponse from the Router API
 *  onLaunch       — callback when "Launch this" is clicked
 *  onClose        — optional close handler
 */

import type { RecommendResponse, ScoredListing } from "@/lib/api";

function ScoreBar({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span className="font-mono">{Math.round(value * 100)}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${value * 100}%` }}
        />
      </div>
    </div>
  );
}

function ListingResultCard({
  listing,
  rank,
  onLaunch,
}: {
  listing: ScoredListing;
  rank: number;
  onLaunch: (listingId: string) => void;
}) {
  const isTop = rank === 0;

  return (
    <div
      className={`group relative overflow-hidden rounded-2xl border transition-all duration-300 hover:shadow-xl ${
        isTop
          ? "border-violet-500/50 bg-gradient-to-b from-violet-950/50 to-slate-900/60 shadow-lg shadow-violet-900/20"
          : "border-white/10 bg-slate-900/40 hover:border-white/20"
      }`}
    >
      {/* Rank badge */}
      <div className="absolute right-3 top-3 flex items-center gap-1.5">
        {isTop ? (
          <span className="rounded-full bg-violet-600/30 px-2.5 py-1 text-xs font-semibold text-violet-300 ring-1 ring-violet-500/40">
            ✦ Top Pick
          </span>
        ) : (
          <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-500">
            #{rank + 1}
          </span>
        )}
      </div>

      <div className="p-5">
        {/* Header */}
        <div className="pr-20">
          <h3 className="font-semibold text-white">
            {listing.title ?? listing.gpu_model ?? "Compute Instance"}
          </h3>
          <p className="mt-0.5 text-sm text-slate-400">
            {[
              listing.gpu_model,
              listing.gpu_vram_gb && `${listing.gpu_vram_gb}GB VRAM`,
              listing.cpu_cores && `${listing.cpu_cores} cores`,
              listing.ram_gb && `${listing.ram_gb}GB RAM`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <p className="mt-1 text-xs text-slate-500">📍 {listing.region ?? "—"}</p>
        </div>

        {/* Pricing */}
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-white/5 p-3">
            <p className="text-xs text-slate-500">Price / hour</p>
            <p className="text-lg font-bold text-white">
              ${Number(listing.price_per_hour_usd).toFixed(3)}
            </p>
            <p className="text-xs text-slate-400">
              ₹{Number(listing.price_per_hour_inr).toFixed(2)}
            </p>
          </div>
          {listing.estimated_cost_usd && (
            <div className="rounded-xl bg-white/5 p-3">
              <p className="text-xs text-slate-500">Est. job cost</p>
              <p className="text-lg font-bold text-emerald-400">
                ${Number(listing.estimated_cost_usd).toFixed(2)}
              </p>
              {listing.estimated_hours && (
                <p className="text-xs text-slate-400">
                  ~{" "}
                  {listing.estimated_hours < 1
                    ? `${Math.round(listing.estimated_hours * 60)}m`
                    : `${listing.estimated_hours.toFixed(1)}h`}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Score breakdown */}
        <div className="mt-4 space-y-2">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
            Score breakdown
          </p>
          <ScoreBar
            label="Price efficiency"
            value={listing.score_price}
            color="bg-emerald-500"
          />
          <ScoreBar
            label="Performance"
            value={listing.score_benchmark}
            color="bg-blue-500"
          />
          <ScoreBar
            label="Availability"
            value={listing.score_availability}
            color="bg-amber-500"
          />
          <div className="mt-1 pt-1 border-t border-white/5">
            <ScoreBar
              label="Composite score"
              value={listing.score_composite}
              color={isTop ? "bg-violet-500" : "bg-slate-500"}
            />
          </div>
        </div>

        {/* Benchmark info */}
        {listing.benchmark_score && (
          <p className="mt-3 text-xs text-slate-600">
            Benchmark: {listing.benchmark_type} — {listing.benchmark_score.toFixed(1)} tokens/s
          </p>
        )}

        {/* Launch button */}
        <button
          id={`launch-btn-${listing.listing_id}`}
          onClick={() => onLaunch(listing.listing_id)}
          className={`mt-4 w-full rounded-xl py-2.5 text-sm font-semibold text-white transition-all active:scale-[0.98] ${
            isTop
              ? "bg-gradient-to-r from-violet-600 to-indigo-600 shadow-md shadow-violet-900/30 hover:from-violet-500 hover:to-indigo-500"
              : "bg-white/10 hover:bg-white/15"
          }`}
        >
          🚀 Launch this machine
        </button>
      </div>
    </div>
  );
}

export function RecommendationResults({
  recommendation,
  onLaunch,
  onClose,
  isLoading = false,
}: {
  recommendation: RecommendResponse | null;
  onLaunch: (listingId: string) => void;
  onClose?: () => void;
  isLoading?: boolean;
}) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-56 animate-pulse rounded-2xl border border-white/10 bg-white/5"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    );
  }

  if (!recommendation || recommendation.results.length === 0) {
    const requestedGpu = (recommendation?.request?.gpu_model as string) || "";
    
    return (
      <div className="rounded-2xl border border-white/10 bg-slate-900/40 p-8 text-center max-w-xl mx-auto">
        <p className="text-3xl mb-3">🔍</p>
        <p className="font-semibold text-lg text-white">
          {requestedGpu
            ? `No "${requestedGpu}" currently available.`
            : "No matching machines currently available."}
        </p>
        <p className="mt-2 text-sm text-slate-400">
          Try relaxing your budget, region, or VRAM requirements, or check one of our trusted partners below.
        </p>

        <div className="mt-6 border-t border-white/5 pt-6 text-left">
          <h4 className="text-xs font-semibold text-violet-400 uppercase tracking-wider mb-4">
            Recommended Alternatives
          </h4>
          <div className="grid grid-cols-2 gap-3">
            {[
              { name: "RunPod", url: "https://www.runpod.io/" },
              { name: "Vast.ai", url: "https://vast.ai/" },
              { name: "Lambda", url: "https://lambdalabs.com/" },
              { name: "Crusoe", url: "https://www.crusoecloud.com/" },
            ].map((provider) => (
              <a
                key={provider.name}
                href={provider.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between rounded-xl border border-white/5 bg-white/5 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-white/10 hover:border-violet-500/30"
              >
                <span>{provider.name}</span>
                <span className="text-slate-500 text-xs">↗</span>
              </a>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">
            {recommendation.results.length} Recommendation
            {recommendation.results.length !== 1 ? "s" : ""}
          </h2>
          <p className="text-xs text-slate-500">
            From {recommendation.total_candidates_evaluated} candidates evaluated
          </p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-400 hover:text-white"
          >
            Clear
          </button>
        )}
      </div>

      <div className="space-y-4">
        {recommendation.results.map((listing, i) => (
          <ListingResultCard
            key={listing.listing_id}
            listing={listing}
            rank={i}
            onLaunch={onLaunch}
          />
        ))}
      </div>
    </div>
  );
}
