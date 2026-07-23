import React from 'react';

export const metadata = {
  title: 'Kynetic AI — Operations & Admin Console',
  description: 'Internal Operations Dashboard for Kynetic AI Support, Security, and Finance teams.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, -apple-system, sans-serif', backgroundColor: '#090d16', color: '#f3f4f6' }}>
        <div style={{ display: 'flex', minHeight: '100vh' }}>
          {/* Navigation Sidebar */}
          <aside style={{ width: '260px', backgroundColor: '#111827', borderRight: '1px solid #1f2937', padding: '24px 16px' }}>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#38bdf8', marginBottom: '32px' }}>
              🛡️ Kynetic Ops Center
            </div>
            <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <a href="/" style={{ color: '#e5e7eb', textDecoration: 'none', padding: '10px 12px', borderRadius: '6px', backgroundColor: '#1f2937' }}>
                📊 Overview
              </a>
              <a href="/fraud" style={{ color: '#9ca3af', textDecoration: 'none', padding: '10px 12px', borderRadius: '6px' }}>
                🚨 Fraud Queue
              </a>
              <a href="/tickets" style={{ color: '#9ca3af', textDecoration: 'none', padding: '10px 12px', borderRadius: '6px' }}>
                🎫 Support Tickets
              </a>
              <a href="/reconciliation" style={{ color: '#9ca3af', textDecoration: 'none', padding: '10px 12px', borderRadius: '6px' }}>
                💵 Financial Ledger
              </a>
              <a href="/hosts" style={{ color: '#9ca3af', textDecoration: 'none', padding: '10px 12px', borderRadius: '6px' }}>
                🖥️ Host Moderation
              </a>
            </nav>
          </aside>

          {/* Main Content View */}
          <main style={{ flex: 1, padding: '32px' }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
