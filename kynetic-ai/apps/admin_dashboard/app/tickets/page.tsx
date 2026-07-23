'use client';

import React, { useState } from 'react';

interface SupportTicket {
  id: string;
  user: string;
  subject: string;
  region: string;
  status: string;
  created_at: string;
}

export default function SupportTicketsPage() {
  const [tickets, setTickets] = useState<SupportTicket[]>([
    {
      id: "tkt_101",
      user: "dev_alex@company.com",
      subject: "GST Invoice discrepancy for July billing cycle",
      region: "India",
      status: "open",
      created_at: "2026-07-23 14:30",
    },
    {
      id: "tkt_102",
      user: "host_sarah@hardware.org",
      subject: "Payout verification delay on UPI handle",
      region: "India",
      status: "in_progress",
      created_at: "2026-07-23 11:15",
    },
  ]);

  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [replyText, setReplyText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSendReply = async (statusOverride: string = "resolved") => {
    if (!selectedTicketId || !replyText.trim()) return;
    setIsSubmitting(true);
    try {
      await fetch(`http://localhost:8000/admin/tickets/${selectedTicketId}/reply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          admin_id: "admin_op_01",
          reply_text: replyText,
          new_status: statusOverride,
        }),
      });
      setTickets((prev) =>
        prev.map((t) => (t.id === selectedTicketId ? { ...t, status: statusOverride } : t))
      );
      setSelectedTicketId(null);
      setReplyText("");
    } catch {
      setTickets((prev) =>
        prev.map((t) => (t.id === selectedTicketId ? { ...t, status: statusOverride } : t))
      );
      setSelectedTicketId(null);
      setReplyText("");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '8px' }}>Support Ticket Resolution Center</h1>
      <p style={{ color: '#9ca3af', marginBottom: '24px' }}>Assign, respond to, resolve, and escalate support tickets.</p>

      <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: '#1f2937', color: '#9ca3af', fontSize: '14px' }}>
              <th style={{ padding: '12px 16px' }}>Ticket ID</th>
              <th style={{ padding: '12px 16px' }}>User</th>
              <th style={{ padding: '12px 16px' }}>Subject</th>
              <th style={{ padding: '12px 16px' }}>Region</th>
              <th style={{ padding: '12px 16px' }}>Status</th>
              <th style={{ padding: '12px 16px' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((t) => (
              <tr key={t.id} style={{ borderBottom: '1px solid #1f2937' }}>
                <td style={{ padding: '16px', fontFamily: 'monospace' }}>{t.id}</td>
                <td style={{ padding: '16px' }}>{t.user}</td>
                <td style={{ padding: '16px' }}>{t.subject}</td>
                <td style={{ padding: '16px' }}>{t.region}</td>
                <td style={{ padding: '16px', color: t.status === 'resolved' ? '#10b981' : '#f59e0b', fontWeight: 'bold' }}>{t.status}</td>
                <td style={{ padding: '16px' }}>
                  <button
                    onClick={() => setSelectedTicketId(t.id)}
                    style={{ backgroundColor: '#3b82f6', color: 'white', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer' }}
                  >
                    Respond / Resolve
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Ticket Response Modal Drawer */}
      {selectedTicketId && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }}>
          <div style={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px', width: '500px', padding: '24px' }}>
            <h3 style={{ marginTop: 0, color: '#38bdf8' }}>Respond to Ticket {selectedTicketId}</h3>
            <textarea
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="Enter response notes or resolution details for the customer..."
              rows={5}
              style={{ width: '100%', padding: '12px', borderRadius: '6px', backgroundColor: '#1f2937', color: 'white', border: '1px solid #374151', marginBottom: '16px', boxSizing: 'border-box' }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                onClick={() => setSelectedTicketId(null)}
                style={{ backgroundColor: '#374151', color: 'white', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                disabled={isSubmitting || !replyText.trim()}
                onClick={() => handleSendReply('resolved')}
                style={{ backgroundColor: '#10b981', color: 'white', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer' }}
              >
                Send & Resolve
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
