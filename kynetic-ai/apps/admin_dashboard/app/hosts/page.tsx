'use client';

import React, { useState } from 'react';

interface HostItem {
  id: string;
  user: string;
  hardware: string;
  status: string;
  reputation: number;
}

export default function HostModerationPage() {
  const [hosts, setHosts] = useState<HostItem[]>([
    {
      id: "hst_88201",
      user: "host_mumbai_01",
      hardware: "NVIDIA RTX 4090 (24GB VRAM)",
      status: "verified",
      reputation: 0.94,
    },
    {
      id: "hst_88202",
      user: "host_delhi_04",
      hardware: "NVIDIA RTX 3090 (24GB VRAM)",
      status: "flagged",
      reputation: 0.38,
    },
  ]);

  const [loadingId, setLoadingId] = useState<string | null>(null);

  const handleModeration = async (hostId: string, action: 'reverify' | 'suspend' | 'delist') => {
    setLoadingId(hostId);
    try {
      await fetch(`http://localhost:8000/admin/hosts/${hostId}/moderation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, reason: `Operator action: ${action}` }),
      });
      const newStatus = action === 'reverify' ? 'verified' : action;
      setHosts((prev) =>
        prev.map((h) => (h.id === hostId ? { ...h, status: newStatus } : h))
      );
    } catch {
      const newStatus = action === 'reverify' ? 'verified' : action;
      setHosts((prev) =>
        prev.map((h) => (h.id === hostId ? { ...h, status: newStatus } : h))
      );
    } finally {
      setLoadingId(null);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '8px' }}>Host & Listing Moderation</h1>
      <p style={{ color: '#9ca3af', marginBottom: '24px' }}>Manually suspend, re-verify, or de-list host hardware nodes outside automated flows.</p>

      <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: '#1f2937', color: '#9ca3af', fontSize: '14px' }}>
              <th style={{ padding: '12px 16px' }}>Host ID</th>
              <th style={{ padding: '12px 16px' }}>Owner</th>
              <th style={{ padding: '12px 16px' }}>Hardware</th>
              <th style={{ padding: '12px 16px' }}>Status</th>
              <th style={{ padding: '12px 16px' }}>Reputation</th>
              <th style={{ padding: '12px 16px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {hosts.map((h) => (
              <tr key={h.id} style={{ borderBottom: '1px solid #1f2937' }}>
                <td style={{ padding: '16px', fontFamily: 'monospace' }}>{h.id}</td>
                <td style={{ padding: '16px' }}>{h.user}</td>
                <td style={{ padding: '16px' }}>{h.hardware}</td>
                <td style={{ padding: '16px' }}>
                  <span style={{
                    padding: '4px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold',
                    backgroundColor: h.status === 'verified' ? '#065f46' : '#991b1b',
                    color: h.status === 'verified' ? '#34d399' : '#f87171'
                  }}>
                    {h.status.toUpperCase()}
                  </span>
                </td>
                <td style={{ padding: '16px', color: h.reputation > 0.8 ? '#10b981' : '#ef4444', fontWeight: 'bold' }}>{h.reputation}</td>
                <td style={{ padding: '16px' }}>
                  <button
                    disabled={loadingId === h.id}
                    onClick={() => handleModeration(h.id, 'reverify')}
                    style={{ backgroundColor: '#f59e0b', color: 'white', border: 'none', padding: '6px 12px', borderRadius: '4px', marginRight: '8px', cursor: 'pointer' }}
                  >
                    Re-verify
                  </button>
                  <button
                    disabled={loadingId === h.id}
                    onClick={() => handleModeration(h.id, 'suspend')}
                    style={{ backgroundColor: '#ef4444', color: 'white', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer' }}
                  >
                    Suspend / Delist
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
