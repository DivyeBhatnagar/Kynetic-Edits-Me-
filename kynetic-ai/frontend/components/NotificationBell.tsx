"use client";

/**
 * NotificationBell — Phase 10
 *
 * Displays unread count badge. Opens a dropdown with latest notifications.
 * Marks all as read when dropdown closes.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Notification, NotificationListResponse, notificationsApi } from "@/lib/api";

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

export function NotificationBell({ token }: { token: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<NotificationListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const res = await notificationsApi.list(token, { page: 1 });
      setData(res);
    } catch {
      // fail silently — bell is non-critical
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetch();
    const interval = setInterval(fetch, 60_000); // poll every 60s
    return () => clearInterval(interval);
  }, [fetch]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Mark all read when closing
  const handleClose = async () => {
    setOpen(false);
    if (data && data.unread_count > 0) {
      try {
        await notificationsApi.markAllRead(token);
        setData((prev) => prev ? { ...prev, unread_count: 0, items: prev.items.map(n => ({ ...n, is_read: true })) } : prev);
      } catch {
        // best-effort
      }
    }
  };

  const unread = data?.unread_count ?? 0;

  return (
    <div style={{ position: "relative" }} ref={dropdownRef}>
      <button
        id="notification-bell-btn"
        onClick={() => open ? handleClose() : setOpen(true)}
        style={{
          position: "relative",
          background: "transparent",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 10,
          padding: "8px 10px",
          cursor: "pointer",
          fontSize: 18,
          lineHeight: 1,
          color: "var(--text-secondary)",
          transition: "all 0.2s ease",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.25)"; }}
        onMouseLeave={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)"; }}
        aria-label={`Notifications${unread > 0 ? ` (${unread} unread)` : ""}`}
      >
        🔔
        {unread > 0 && (
          <span
            style={{
              position: "absolute",
              top: -4,
              right: -4,
              background: "hsl(258, 90%, 66%)",
              color: "#fff",
              borderRadius: "50%",
              minWidth: 18,
              height: 18,
              fontSize: 11,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "0 4px",
              lineHeight: 1,
            }}
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 8px)",
            width: 340,
            background: "hsl(240, 15%, 10%)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 14,
            boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
            zIndex: 1000,
            overflow: "hidden",
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: "14px 16px",
              borderBottom: "1px solid rgba(255,255,255,0.06)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
              Notifications
            </span>
            {unread > 0 && (
              <button
                onClick={async () => {
                  await notificationsApi.markAllRead(token);
                  setData((prev) => prev ? { ...prev, unread_count: 0, items: prev.items.map(n => ({ ...n, is_read: true })) } : prev);
                }}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "hsl(258, 90%, 76%)",
                  fontSize: 12,
                  cursor: "pointer",
                }}
              >
                Mark all read
              </button>
            )}
          </div>

          {/* Items */}
          <div style={{ maxHeight: 380, overflowY: "auto" }}>
            {loading && (
              <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                Loading...
              </div>
            )}
            {!loading && (!data || data.items.length === 0) && (
              <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>🎉</div>
                All caught up!
              </div>
            )}
            {!loading && data?.items.map((n) => (
              <div
                key={n.id}
                style={{
                  padding: "12px 16px",
                  borderBottom: "1px solid rgba(255,255,255,0.04)",
                  background: n.is_read ? "transparent" : "rgba(124, 58, 237, 0.06)",
                  display: "flex",
                  gap: 10,
                  alignItems: "flex-start",
                }}
              >
                <span style={{ fontSize: 18, flexShrink: 0, marginTop: 1 }}>
                  {TYPE_ICONS[n.notification_type] ?? "📌"}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{
                    fontSize: 13,
                    fontWeight: n.is_read ? 400 : 600,
                    color: "var(--text-primary)",
                    margin: 0,
                    marginBottom: 2,
                  }}>
                    {n.title}
                  </p>
                  <p style={{
                    fontSize: 12,
                    color: "var(--text-secondary)",
                    margin: 0,
                    marginBottom: 4,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}>
                    {n.body}
                  </p>
                  <p style={{ fontSize: 11, color: "var(--text-muted)", margin: 0 }}>
                    {timeAgo(n.created_at)}
                  </p>
                </div>
                {!n.is_read && (
                  <div style={{
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: "hsl(258, 90%, 66%)",
                    flexShrink: 0,
                    marginTop: 6,
                  }} />
                )}
              </div>
            ))}
          </div>

          {/* Footer */}
          <div style={{ padding: "10px 16px", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
            <a
              href="/notifications"
              style={{
                fontSize: 12,
                color: "hsl(258, 90%, 76%)",
                textDecoration: "none",
                display: "block",
                textAlign: "center",
              }}
            >
              View all notifications →
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
