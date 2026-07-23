import React from 'react';

export default function AdminOverviewPage() {
  return (
    <div>
      <h1 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '8px' }}>Operations & Control Overview</h1>
      <p style={{ color: '#9ca3af', marginBottom: '32px' }}>Real-time metrics, flagged reviews, and active operational status.</p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '32px' }}>
        <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '20px', borderRadius: '8px' }}>
          <div style={{ color: '#9ca3af', fontSize: '14px' }}>Active MicroVMs</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#38bdf8', marginTop: '8px' }}>42</div>
        </div>
        <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '20px', borderRadius: '8px' }}>
          <div style={{ color: '#9ca3af', fontSize: '14px' }}>Pending Fraud Flags</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#ef4444', marginTop: '8px' }}>3</div>
        </div>
        <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '20px', borderRadius: '8px' }}>
          <div style={{ color: '#9ca3af', fontSize: '14px' }}>Open Support Tickets</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#f59e0b', marginTop: '8px' }}>7</div>
        </div>
        <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '20px', borderRadius: '8px' }}>
          <div style={{ color: '#9ca3af', fontSize: '14px' }}>24h Ledger Status</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#10b981', marginTop: '8px' }}>Reconciled</div>
        </div>
      </div>
    </div>
  );
}
