import React from 'react';

export const metadata = {
  title: 'Kynetic AI — Compute Marketplace',
  description: 'Resource-agnostic compute marketplace connecting idle GPUs with AI developers.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, -apple-system, sans-serif', backgroundColor: '#090d16', color: '#f3f4f6' }}>
        <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
          {/* Header Navigation Bar */}
          <header style={{ backgroundColor: '#111827', borderBottom: '1px solid #1f2937', padding: '16px 32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <a href="/" style={{ fontSize: '20px', fontWeight: 'bold', color: '#38bdf8', textDecoration: 'none' }}>
              ⚡ Kynetic AI
            </a>
            <nav style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
              <a href="/onboarding" style={{ color: '#e5e7eb', textDecoration: 'none', fontSize: '14px' }}>🖥️ Host Onboarding</a>
              <a href="/instances" style={{ color: '#e5e7eb', textDecoration: 'none', fontSize: '14px' }}>🚀 My Instances</a>
              <a href="/copilot" style={{ color: '#e5e7eb', textDecoration: 'none', fontSize: '14px' }}>🤖 AI Copilot</a>
              <a href="/terms" style={{ color: '#9ca3af', textDecoration: 'none', fontSize: '14px' }}>Terms</a>
              <a href="/privacy" style={{ color: '#9ca3af', textDecoration: 'none', fontSize: '14px' }}>Privacy</a>
            </nav>
          </header>

          {/* Main Body */}
          <main style={{ flex: 1 }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
