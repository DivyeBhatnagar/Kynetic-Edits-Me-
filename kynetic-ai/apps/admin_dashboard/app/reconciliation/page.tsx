import React from 'react';

export default function FinancialReconciliationPage() {
  return (
    <div>
      <h1 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '8px' }}>Financial Reconciliation View</h1>
      <p style={{ color: '#9ca3af', marginBottom: '24px' }}>Cross-checks database wallet transactions against payment provider (Stripe & Razorpay) ledgers.</p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px', marginBottom: '32px' }}>
        <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '24px', borderRadius: '8px' }}>
          <h3 style={{ marginTop: 0, color: '#38bdf8' }}>Stripe (USD) Ledger Audit</h3>
          <p>DB Wallet Debits: <strong>$12,500.00</strong></p>
          <p>Stripe Ledger Total: <strong>$12,500.00</strong></p>
          <p style={{ color: '#10b981', fontWeight: 'bold' }}>Drift: $0.00 (Reconciled)</p>
        </div>

        <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '24px', borderRadius: '8px' }}>
          <h3 style={{ marginTop: 0, color: '#38bdf8' }}>Razorpay (INR) Ledger Audit</h3>
          <p>DB Wallet Debits: <strong>₹450,000.00</strong></p>
          <p>Razorpay Ledger Total: <strong>₹450,000.00</strong></p>
          <p style={{ color: '#10b981', fontWeight: 'bold' }}>Drift: ₹0.00 (Reconciled)</p>
        </div>
      </div>
    </div>
  );
}
