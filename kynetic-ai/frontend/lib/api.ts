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

// ── Phase 7: AI Router & Copilot types ─────────────────────────────────────

export interface BudgetFilter {
  amount: string;
  currency: "usd" | "inr";
}

export interface RecommendRequest {
  budget?: BudgetFilter;
  goal?: "fastest" | "cheapest" | "balanced";
  template_id?: string;
  min_gpu_vram_gb?: number;
  region?: string;
}

export interface ScoredListing {
  listing_id: string;
  host_id: string;
  title: string | null;
  gpu_model: string | null;
  gpu_count: number | null;
  gpu_vram_gb: number | null;
  cpu_cores: number | null;
  ram_gb: number | null;
  region: string | null;
  price_per_hour_usd: string;
  price_per_hour_inr: string;
  estimated_cost_usd: string | null;
  estimated_cost_inr: string | null;
  estimated_hours: number | null;
  score_price: number;
  score_benchmark: number;
  score_availability: number;
  score_composite: number;
  benchmark_score: number | null;
  benchmark_type: string | null;
  reputation_score: number;
}

export interface RecommendResponse {
  recommendation_id: string;
  request: Record<string, unknown>;
  results: ScoredListing[];
  total_candidates_evaluated: number;
}

export interface CopilotChatRequest {
  session_id?: string;
  message: string;
}

export interface CopilotChatResponse {
  session_id: string;
  message_id: string;
  role: "assistant";
  content: string;
  recommendation: RecommendResponse | null;
}

export interface CopilotMessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  router_recommendation_id: string | null;
  created_at: string;
}

export interface CopilotSessionHistory {
  session_id: string;
  developer_id: string | null;
  created_at: string;
  messages: CopilotMessageOut[];
}

export const routerApi = {
  recommend: (body: RecommendRequest, token?: string) =>
    request<RecommendResponse>("/router/recommend", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),
};

export const copilotApi = {
  chat: (body: CopilotChatRequest, token: string) =>
    request<CopilotChatResponse>("/copilot/chat", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),

  getHistory: (sessionId: string, token: string) =>
    request<CopilotSessionHistory>(`/copilot/sessions/${sessionId}/history`, {
      token,
    }),
};

/**
 * WebSocket-based Copilot client.
 *
 * Usage:
 *   const ws = new CopilotWebSocket(sessionId, token, onMessage, onError);
 *   ws.send("I need a GPU for LoRA training with a ₹120 budget");
 *   ws.close();
 */
export class CopilotWebSocket {
  private ws: WebSocket | null = null;
  private sessionId: string | null;

  constructor(
    sessionId: string | null,
    private token: string,
    private onMessage: (data: WSOutbound) => void,
    private onError: (err: Event) => void,
    private onOpen?: () => void,
  ) {
    this.sessionId = sessionId;
    this._connect();
  }

  private _connect() {
    const wsBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
      .replace("http://", "ws://")
      .replace("https://", "wss://");
    const url = `${wsBase}/copilot/ws/${this.sessionId ?? "new"}`;
    this.ws = new WebSocket(url, [`Bearer.${this.token}`]);
    this.ws.onmessage = (ev) => {
      try {
        this.onMessage(JSON.parse(ev.data) as WSOutbound);
      } catch {
        /* ignore parse errors */
      }
    };
    this.ws.onerror = this.onError;
    this.ws.onopen = () => this.onOpen?.();
  }

  send(message: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({ type: "chat", session_id: this.sessionId, message })
      );
    }
  }

  close() {
    this.ws?.close();
  }
}

export interface WSOutbound {
  type: "chat_response" | "error" | "ping";
  session_id: string | null;
  message_id: string | null;
  content: string;
  recommendation: RecommendResponse | null;
  error: string | null;
}


// ── Phase 8 Types ──────────────────────────────────────────────────────────────

export interface ReputationComponents {
  uptime_score: number | null;
  latency_score: number | null;
  network_score: number | null;
  job_success_rate: number | null;
  benchmark_score_normalised: number | null;
  response_time_score: number | null;
}

export interface ReputationScore {
  host_id: string;
  composite_score: number;
  components: ReputationComponents;
  jobs_evaluated: number;
  computed_at: string;
  trend: number[];
}

export interface PricingSuggestion {
  listing_id: string;
  suggested_price_usd: string;
  suggested_price_inr: string;
  confidence_interval_low_usd: string | null;
  confidence_interval_high_usd: string | null;
  model_version: string;
  rationale: string;
}

export interface IdlePrediction {
  host_id: string;
  predicted_idle_hours_per_day: number;
  predicted_utilization_fraction: number;
  income_projection_monthly_usd: string;
  income_projection_monthly_inr: string;
  electricity_cost_monthly_usd: string | null;
  net_income_monthly_usd: string | null;
  computed_at: string;
}

export interface RevenueAnalytics {
  total_revenue_usd_7d: string;
  total_revenue_usd_30d: string;
  total_revenue_inr_7d: string;
  total_revenue_inr_30d: string;
  total_jobs_completed: number;
  avg_job_duration_hours: number;
}

export interface HealthSnapshot {
  last_heartbeat_at: string | null;
  uptime_pct_30d: number | null;
  gpu_temp_celsius: number | null;
  cpu_temp_celsius: number | null;
  power_draw_watts: number | null;
}

export interface HostDashboard {
  host_id: string;
  reputation: ReputationScore | null;
  revenue: RevenueAnalytics;
  health: HealthSnapshot;
  idle_prediction: IdlePrediction | null;
  pricing_suggestion: PricingSuggestion | null;
}


// ── Phase 8 API helpers ────────────────────────────────────────────────────────

export const reputationApi = {
  /** GET /hosts/{id}/reputation — public, no auth required */
  get: (hostId: string): Promise<ReputationScore> =>
    request<ReputationScore>(`/hosts/${hostId}/reputation`),
};

export const dashboardApi = {
  /** GET /hosts/{id}/dashboard — requires auth */
  get: (hostId: string, token: string): Promise<HostDashboard> =>
    request<HostDashboard>(`/hosts/${hostId}/dashboard`, { token }),
};

export const pricingSuggestApi = {
  /** GET /pricing/suggest?listing_id=... — requires auth */
  suggest: (listingId: string, token: string): Promise<PricingSuggestion> =>
    request<PricingSuggestion>(`/pricing/suggest?listing_id=${listingId}`, { token }),
};


// ── Phase 10 Types ──────────────────────────────────────────────────────────

export interface Invoice {
  id: string;
  transaction_id: string;
  user_id: string;
  invoice_number: string;
  gstin: string | null;
  amount_inr: string;
  gst_rate_pct: string;
  gst_amount_inr: string;
  pdf_url: string | null;
  issued_at: string;
}

export interface InvoiceListResponse {
  items: Invoice[];
  total: number;
  page: number;
  page_size: number;
}

export interface Notification {
  id: string;
  notification_type: string;
  channel: string;
  title: string;
  body: string;
  payload: Record<string, unknown> | null;
  is_read: boolean;
  sent_at: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: Notification[];
  total: number;
  unread_count: number;
  page: number;
  page_size: number;
}

export interface NotificationPreference {
  email_enabled: boolean;
  sms_enabled: boolean;
  low_balance_threshold_usd: string;
}

export interface SupportTicket {
  id: string;
  user_id: string;
  region: string;
  subject: string;
  status: string;
  external_ticket_id: string | null;
  created_at: string;
}

export interface UpiTopupResponse {
  razorpay_order_id: string;
  amount_inr: string;
  amount_paise: number;
  razorpay_key_id: string;
  currency: string;
}


// ── Phase 10 API helpers ────────────────────────────────────────────────────

export const notificationsApi = {
  list: (token: string, params?: { page?: number; unread_only?: boolean }): Promise<NotificationListResponse> => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", String(params.page));
    if (params?.unread_only) q.set("unread_only", "true");
    return request<NotificationListResponse>(`/notifications?${q}`, { token });
  },
  markRead: (id: string, token: string): Promise<void> =>
    request<void>(`/notifications/${id}/read`, { method: "POST", token }),
  markAllRead: (token: string): Promise<void> =>
    request<void>("/notifications/mark-all-read", { method: "POST", token }),
  getPreferences: (token: string): Promise<NotificationPreference> =>
    request<NotificationPreference>("/notifications/preferences", { token }),
  updatePreferences: (prefs: Partial<NotificationPreference>, token: string): Promise<NotificationPreference> =>
    request<NotificationPreference>("/notifications/preferences", {
      method: "PUT",
      body: JSON.stringify(prefs),
      token,
    }),
};

export const invoicesApi = {
  list: (token: string, page = 1): Promise<InvoiceListResponse> =>
    request<InvoiceListResponse>(`/billing/invoices?page=${page}`, { token }),
  get: (id: string, token: string): Promise<Invoice> =>
    request<Invoice>(`/billing/invoices/${id}`, { token }),
};

export const supportApi = {
  create: (body: { subject: string; description: string; region: string }, token: string): Promise<SupportTicket> =>
    request<SupportTicket>("/support/tickets", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),
  list: (token: string): Promise<SupportTicket[]> =>
    request<SupportTicket[]>("/support/tickets", { token }),
};

export const upiApi = {
  createOrder: (amount_inr: number, token: string): Promise<UpiTopupResponse> =>
    request<UpiTopupResponse>("/wallet/topup/upi", {
      method: "POST",
      body: JSON.stringify({ amount_inr }),
      token,
    }),
  confirmPayment: (
    payload: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string },
    token: string
  ): Promise<{ received: boolean; status: string }> =>
    request("/billing/webhooks/razorpay", {
      method: "POST",
      body: JSON.stringify(payload),
      token,
    }),
};
