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

// ── Instance Types ─────────────────────────────────────────────────────────

export type InstanceStatus =
  | "pending"
  | "provisioning"
  | "running"
  | "stopping"
  | "stopped"
  | "terminated"
  | "failed";

export interface Instance {
  id: string;
  developer_id: string;
  listing_id: string;
  host_id: string;
  status: InstanceStatus;
  hold_amount: string;
  hold_released: boolean;
  firecracker_vm_id: string | null;
  wireguard_ip: string | null;
  public_ip: string | null;
  ssh_port: number;
  billed_seconds: number;
  price_per_second_usd: string;
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
  terminated_at: string | null;
}

export interface InstanceListResponse {
  items: Instance[];
  total: number;
  page: number;
  page_size: number;
}

export interface ConnectionInfo {
  instance_id: string;
  status: InstanceStatus;
  ssh_host: string;
  ssh_port: number;
  ssh_user: string;
  private_key_pem: string;
  public_key: string;
  ssh_command: string;
  key_expires_at: string | null;
}

export interface DeletionReceipt {
  instance_id: string;
  method: string;
  agent_confirmation_hash: string;
  verified_at: string;
}

// ── Instances API ──────────────────────────────────────────────────────────

export const instancesApi = {
  launch: (token: string, listing_id: string, template_id?: string) =>
    request<Instance>("/instances", {
      method: "POST",
      token,
      body: JSON.stringify({ listing_id, template_id }),
    }),

  get: (token: string, instanceId: string) =>
    request<Instance>(`/instances/${instanceId}`, { token }),

  list: (token: string, status?: InstanceStatus, page = 1) => {
    const qs = new URLSearchParams({ page: String(page) });
    if (status) qs.set("status_filter", status);
    return request<InstanceListResponse>(`/instances?${qs}`, { token });
  },

  stop: (token: string, instanceId: string) =>
    request<{ message: string }>(`/instances/${instanceId}/stop`, {
      method: "POST",
      token,
      body: JSON.stringify({}),
    }),

  start: (token: string, instanceId: string) =>
    request<{ message: string }>(`/instances/${instanceId}/start`, {
      method: "POST",
      token,
    }),

  terminate: (token: string, instanceId: string, force = false) =>
    request<{ message: string }>(`/instances/${instanceId}/terminate`, {
      method: "POST",
      token,
      body: JSON.stringify({ force }),
    }),

  getConnection: (token: string, instanceId: string) =>
    request<ConnectionInfo>(`/instances/${instanceId}/connection`, { token }),

  getDeletionReceipt: (token: string, instanceId: string) =>
    request<DeletionReceipt>(`/instances/${instanceId}/deletion-receipt`, { token }),

  /** Phase 6 — get web UI access link for a running templated instance */
  getWebUI: (token: string, instanceId: string) =>
    request<WebUILink>(`/instances/${instanceId}/web-ui`, { token }),
};

// ── Phase 6: Templates ─────────────────────────────────────────────────────

export type TemplateStatus = "pending_scan" | "available" | "disabled";

export interface Template {
  id: string;
  name: string;
  slug: string;
  description: string;
  icon_emoji: string;
  tags: string[];
  base_image: string;
  required_gpu_vram_gb: number | null;
  required_ram_gb: number;
  required_vcpus: number;
  startup_command: string | null;
  default_ssh_user: string;
  exposed_web_ui_path: string | null;
  web_ui_port: number | null;
  status: TemplateStatus;
  created_at: string;
}

export interface TemplateListResponse {
  items: Template[];
  total: number;
}

export interface WebUILink {
  instance_id: string;
  template_id: string;
  web_ui_url: string;
  token: string;
  expires_at: string;
  web_ui_port: number;
  note: string;
}

export const templatesApi = {
  /** Public — no auth required */
  list: () =>
    request<TemplateListResponse>("/templates"),

  /** Public — get by UUID or slug */
  get: (idOrSlug: string) =>
    request<Template>(`/templates/${idOrSlug}`),
};
