import React from 'react';

export default function SupportTicketsPage() {
  const tickets = [
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
  ];

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
                <td style={{ padding: '16px', color: '#f59e0b', fontWeight: 'bold' }}>{t.status}</td>
                <td style={{ padding: '16px' }}>
                  <button style={{ backgroundColor: '#3b82f6', color: 'white', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer' }}>Respond / Resolve</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
