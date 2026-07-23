'use client';

import React from 'react';

export default function MarketplaceHomePage() {
  return (
    <div style={{ maxWidth: '1000px', margin: '40px auto', padding: '0 20px', fontFamily: 'system-ui, sans-serif' }}>
      <div style={{ textAlign: 'center', marginBottom: '48px' }}>
        <h1 style={{ fontSize: '36px', fontWeight: 'bold', color: '#38bdf8', marginBottom: '12px' }}>
          DeCentralized GPU & Compute Marketplace
        </h1>
        <p style={{ color: '#9ca3af', fontSize: '18px', maxWidth: '600px', margin: '0 auto' }}>
          Rent high-performance GPUs (RTX 4090, A100, H100) or monetize your idle hardware in minutes.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '24px' }}>
        <a href="/onboarding" style={{ textDecoration: 'none', backgroundColor: '#111827', border: '1px solid #1f2937', padding: '24px', borderRadius: '8px', color: '#f3f4f6' }}>
          <h2 style={{ fontSize: '20px', color: '#34d399', marginTop: 0 }}>🖥️ Become a Host</h2>
          <p style={{ color: '#9ca3af', fontSize: '14px' }}>Monetize your idle gaming PC or server. Keep 85% of all gross rental revenue.</p>
        </a>

        <a href="/copilot" style={{ textDecoration: 'none', backgroundColor: '#111827', border: '1px solid #1f2937', padding: '24px', borderRadius: '8px', color: '#f3f4f6' }}>
          <h2 style={{ fontSize: '20px', color: '#38bdf8', marginTop: 0 }}>🤖 AI Copilot Match</h2>
          <p style={{ color: '#9ca3af', fontSize: '14px' }}>Tell Copilot your workload & budget for 1-click hardware node recommendations.</p>
        </a>

        <a href="/instances" style={{ textDecoration: 'none', backgroundColor: '#111827', border: '1px solid #1f2937', padding: '24px', borderRadius: '8px', color: '#f3f4f6' }}>
          <h2 style={{ fontSize: '20px', color: '#a855f7', marginTop: 0 }}>🚀 Active Instances</h2>
          <p style={{ color: '#9ca3af', fontSize: '14px' }}>Start, stop, monitor telemetry, and retrieve SSH connection details for active nodes.</p>
        </a>
      </div>
    </div>
  );
}
