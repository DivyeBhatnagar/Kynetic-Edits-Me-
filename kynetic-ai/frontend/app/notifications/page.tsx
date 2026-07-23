"use client";

/**
 * Notifications Page — Phase 10
 *
 * Full-page view of all notifications with filtering, mark-read,
 * and notification preferences.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Notification,
  NotificationListResponse,
  NotificationPreference,
  notificationsApi,
} from "@/lib/api";

const TYPE_ICONS: Record<string, string> = {
  low_balance: "⚠️",
  wallet_topup_confirmed: "✅",
  payout_confirmed: "💸",
  invoice_ready: "🧾",
  instance_started: "🚀",
  instance_stopped: "⏸️",
  instance_terminated: "🛑",
  instance_failed: "❌",
  system_alert: "🔔",
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// Demo token for now (Phase 10 — auth integration in next step)
const DEMO_TOKEN = "";

export default function NotificationsPage() {
  const [data, setData] = useState<NotificationListResponse | null>(null);
  const [prefs, setPrefs] = useState<NotificationPreference | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [showPrefs, setShowPrefs] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [notifData, prefData] = await Promise.all([
        notificationsApi.list(DEMO_TOKEN, { unread_only: filter === "unread" }),
        notificationsApi.getPreferences(DEMO_TOKEN),
      ]);
      setData(notifData);
      setPrefs(prefData);
    } catch {
      // handle gracefully
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleMarkRead = async (id: string) => {
    try {
      await notificationsApi.markRead(id, DEMO_TOKEN);
      setData((prev) =>
        prev
          ? {
              ...prev,
              unread_count: Math.max(0, prev.unread_count - 1),
              items: prev.items.map((n) =>
                n.id === id ? { ...n, is_read: true } : n
              ),
            }
          : prev
      );
    } catch { /* silent */ }
  };

  const handleMarkAllRead = async () => {
    try {
      await notificationsApi.markAllRead(DEMO_TOKEN);
      setData((prev) =>
        prev
          ? { ...prev, unread_count: 0, items: prev.items.map((n) => ({ ...n, is_read: true })) }
          : prev
      );
    } catch { /* silent */ }
  };

  const handlePrefsUpdate = async (update: Partial<NotificationPreference>) => {
    try {
      const updated = await notificationsApi.updatePreferences(update, DEMO_TOKEN);
      setPrefs(updated);
    } catch { /* silent */ }
  };

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "40px 24px" }}>
      {/* Header */}
      <div className="fade-in" style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1
              style={{
                fontFamily: "var(--font-display)",
                fontSize: 32,
                fontWeight: 700,
                marginBottom: 6,
              }}
            >
              <span className="gradient-text">Notifications</span>
            </h1>
            {data && (
              <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                {data.unread_count} unread · {data.total} total
              </p>
            )}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              id="prefs-toggle-btn"
              className="btn-ghost"
              onClick={() => setShowPrefs((p) => !p)}
              style={{ fontSize: 13 }}
            >
              ⚙️ Preferences
            </button>
            {data && data.unread_count > 0 && (
              <button
                id="mark-all-read-btn"
                className="btn-ghost"
                onClick={handleMarkAllRead}
                style={{ fontSize: 13 }}
              >
                Mark all read
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Preferences panel */}
      {showPrefs && prefs && (
        <div
          className="glass fade-in"
          style={{ padding: 20, marginBottom: 24, display: "flex", gap: 32, alignItems: "center" }}
        >
          <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)" }}>
            Notification Preferences
          </h3>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
            <input
              id="email-notifs-toggle"
              type="checkbox"
              checked={prefs.email_enabled}
              onChange={(e) => handlePrefsUpdate({ email_enabled: e.target.checked })}
              style={{ accentColor: "hsl(258, 90%, 66%)" }}
            />
            Email notifications
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
            <input
              id="sms-notifs-toggle"
              type="checkbox"
              checked={prefs.sms_enabled}
              onChange={(e) => handlePrefsUpdate({ sms_enabled: e.target.checked })}
              style={{ accentColor: "hsl(258, 90%, 66%)" }}
            />
            SMS (coming soon)
          </label>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <span style={{ color: "var(--text-secondary)" }}>Low balance alert below</span>
            <span
              style={{
                background: "rgba(124, 58, 237, 0.15)",
                border: "1px solid hsl(258, 90%, 66% / 0.3)",
                borderRadius: 6,
                padding: "2px 8px",
                fontSize: 12,
                fontFamily: "monospace",
                color: "hsl(258, 90%, 76%)",
              }}
            >
              ${prefs.low_balance_threshold_usd}
            </span>
          </div>
        </div>
      )}

      {/* Filter tabs */}
      <div
        className="fade-in fade-in-delay-1"
        style={{ display: "flex", gap: 4, marginBottom: 20 }}
      >
        {(["all", "unread"] as const).map((f) => (
          <button
            key={f}
            id={`filter-${f}-btn`}
            onClick={() => setFilter(f)}
            style={{
              padding: "6px 16px",
              borderRadius: 8,
              border: "1px solid",
              fontSize: 13,
              cursor: "pointer",
              fontWeight: filter === f ? 600 : 400,
              borderColor: filter === f ? "hsl(258, 90%, 66%)" : "rgba(255,255,255,0.1)",
              background: filter === f ? "rgba(124, 58, 237, 0.15)" : "transparent",
              color: filter === f ? "hsl(258, 90%, 76%)" : "var(--text-secondary)",
              transition: "all 0.2s",
            }}
          >
            {f === "all" ? "All" : `Unread${data ? ` (${data.unread_count})` : ""}`}
          </button>
        ))}
      </div>

      {/* Notification list */}
      <div className="fade-in fade-in-delay-2" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {loading && (
          <>
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="glass skeleton"
                style={{ height: 72, borderRadius: 12 }}
              />
            ))}
          </>
        )}

        {!loading && data && data.items.length === 0 && (
          <div className="glass" style={{ padding: 48, textAlign: "center" }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>🎉</div>
            <p style={{ color: "var(--text-secondary)", fontSize: 14 }}>
              {filter === "unread" ? "No unread notifications." : "No notifications yet."}
            </p>
          </div>
        )}

        {!loading &&
          data?.items.map((n) => (
            <div
              key={n.id}
              className="glass"
              style={{
                padding: "14px 16px",
                display: "flex",
                gap: 14,
                alignItems: "flex-start",
                background: n.is_read
                  ? "rgba(255,255,255,0.02)"
                  : "rgba(124, 58, 237, 0.06)",
                borderColor: n.is_read
                  ? "rgba(255,255,255,0.07)"
                  : "hsl(258, 90%, 66% / 0.25)",
                transition: "all 0.2s",
              }}
            >
              <span style={{ fontSize: 22, flexShrink: 0 }}>
                {TYPE_ICONS[n.notification_type] ?? "📌"}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p
                  style={{
                    fontSize: 14,
                    fontWeight: n.is_read ? 400 : 600,
                    color: "var(--text-primary)",
                    margin: 0,
                    marginBottom: 3,
                  }}
                >
                  {n.title}
                </p>
                <p
                  style={{
                    fontSize: 13,
                    color: "var(--text-secondary)",
                    margin: 0,
                    marginBottom: 6,
                  }}
                >
                  {n.body}
                </p>
                <p style={{ fontSize: 11, color: "var(--text-muted)", margin: 0 }}>
                  {timeAgo(n.created_at)}
                </p>
              </div>
              {!n.is_read && (
                <button
                  id={`mark-read-${n.id}`}
                  className="btn-ghost"
                  onClick={() => handleMarkRead(n.id)}
                  style={{ fontSize: 11, padding: "4px 10px", flexShrink: 0 }}
                >
                  Mark read
                </button>
              )}
            </div>
          ))}
      </div>
    </div>
  );
}
