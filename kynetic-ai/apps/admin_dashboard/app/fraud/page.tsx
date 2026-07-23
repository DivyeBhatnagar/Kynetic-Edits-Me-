import React from 'react';

export default function FraudReviewQueuePage() {
  const items = [
    {
      id: "frd_01",
      user_id: "usr_99823",
      reason: "High risk device fingerprint match across multiple accounts",
      risk_score: 85,
      status: "pending",
    },
    {
      id: "frd_02",
      host_id: "hst_44102",
      reason: "Reputation score dropped below 0.40 threshold",
      risk_score: 65,
      status: "pending",
    },
  ];

  return (
    <div>
      <h1 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '8px' }}>Fraud & Trust Review Queue</h1>
      <p style={{ color: '#9ca3af', marginBottom: '24px' }}>Review accounts flagged by fingerprinting, security events, or reputation drops.</p>

      <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: '#1f2937', color: '#9ca3af', fontSize: '14px' }}>
              <th style={{ padding: '12px 16px' }}>Target ID</th>
              <th style={{ padding: '12px 16px' }}>Reason</th>
              <th style={{ padding: '12px 16px' }}>Risk Score</th>
              <th style={{ padding: '12px 16px' }}>Status</th>
              <th style={{ padding: '12px 16px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} style={{ borderBottom: '1px solid #1f2937' }}>
                <td style={{ padding: '16px', fontFamily: 'monospace' }}>{item.user_id || item.host_id}</td>
                <td style={{ padding: '16px' }}>{item.reason}</td>
                <td style={{ padding: '16px', color: item.risk_score > 80 ? '#ef4444' : '#f59e0b', fontWeight: 'bold' }}>{item.risk_score}/100</td>
                <td style={{ padding: '16px' }}>{item.status}</td>
                <td style={{ padding: '16px' }}>
                  <button style={{ backgroundColor: '#10b981', color: 'white', border: 'none', padding: '6px 12px', borderRadius: '4px', marginRight: '8px', cursor: 'pointer' }}>Approve</button>
                  <button style={{ backgroundColor: '#ef4444', color: 'white', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer' }}>Suspend</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
