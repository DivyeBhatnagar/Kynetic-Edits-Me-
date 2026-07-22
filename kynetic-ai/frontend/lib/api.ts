/**
 * API client — typed fetch wrapper for the Kynetic AI gateway.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string } = {}
): Promise<T> {
  const { token, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? "Request failed");
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Types ──────────────────────────────────────────────────────────────────

export type ResourceType = "gpu" | "cpu" | "ram" | "nvme" | "workstation_bundle";
export type ListingStatus = "draft" | "active" | "paused" | "delisted";
export type Currency = "usd" | "inr";
export type TransactionType = "topup" | "debit" | "refund" | "payout";

export interface ListingBrief {
  id: string;
  resource_type: ResourceType;
  gpu_model: string | null;
  cpu_cores: number | null;
  ram_gb: number | null;
  price_per_hour_usd: string;
  price_per_hour_inr: string;
  region: string | null;
  status: ListingStatus;
  is_available: boolean;
  title: string | null;
}

export interface ListingDetail extends ListingBrief {
  host_id: string;
  owner_user_id: string;
  gpu_count: number | null;
  gpu_vram_gb: number | null;
  storage_gb: number | null;
  storage_type: string | null;
  price_per_second_usd: string;
  price_per_second_inr: string;
  benchmark_scores: Record<string, number> | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ListingSearchResponse {
  items: ListingBrief[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface WalletBalance {
  wallet_id: string;
  preferred_currency: Currency;
  balance: string;
  balance_usd: string;
  balance_inr: string;
}

export interface Transaction {
  id: string;
  wallet_id: string;
  transaction_type: TransactionType;
  amount: string;
  currency: Currency;
  stripe_payment_intent_id: string | null;
  description: string | null;
  balance_after_usd: string;
  balance_after_inr: string;
  created_at: string;
}

export interface TransactionListResponse {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface TopupResponse {
  payment_intent_id: string;
  client_secret: string;
  amount_usd: string;
  amount_inr: string;
  stripe_publishable_key: string;
}

// ── Marketplace API ────────────────────────────────────────────────────────

export interface ListingSearchParams {
  resource_type?: ResourceType;
  gpu_model?: string;
  min_price_usd?: number;
  max_price_usd?: number;
  region?: string;
  available_only?: boolean;
  page?: number;
  page_size?: number;
}

export const marketplaceApi = {
  search: (params: ListingSearchParams = {}) => {
    const qs = new URLSearchParams();
    if (params.resource_type) qs.set("resource_type", params.resource_type);
    if (params.gpu_model) qs.set("gpu_model", params.gpu_model);
    if (params.min_price_usd != null) qs.set("min_price_usd", String(params.min_price_usd));
    if (params.max_price_usd != null) qs.set("max_price_usd", String(params.max_price_usd));
    if (params.region) qs.set("region", params.region);
    qs.set("available_only", String(params.available_only ?? true));
    qs.set("page", String(params.page ?? 1));
    qs.set("page_size", String(params.page_size ?? 20));
    return request<ListingSearchResponse>(`/listings?${qs}`);
  },

  getById: (id: string) => request<ListingDetail>(`/listings/${id}`),
};

// ── Wallet API ─────────────────────────────────────────────────────────────

export const walletApi = {
  getBalance: (token: string) =>
    request<WalletBalance>("/wallet/balance", { token }),

  getTransactions: (token: string, page = 1) =>
    request<TransactionListResponse>(`/wallet/transactions?page=${page}`, { token }),

  topup: (token: string, amount_usd: number) =>
    request<TopupResponse>("/wallet/topup", {
      method: "POST",
      token,
      body: JSON.stringify({ amount_usd, currency: "usd" }),
    }),
};
