import React from 'react';

export const metadata = {
  title: 'Terms of Service & Acceptable Use Policy — Kynetic AI',
  description: 'Terms of Service, Acceptable Use Policy, and Prohibited Workload Rules for Kynetic AI.',
};

export default function TermsPage() {
  return (
    <div style={{ maxWidth: '900px', margin: '0 auto', padding: '40px 20px', fontFamily: 'system-ui, sans-serif', color: '#f3f4f6', backgroundColor: '#090d16' }}>
      <h1 style={{ fontSize: '32px', fontWeight: 'bold', color: '#38bdf8', marginBottom: '16px' }}>Terms of Service & Acceptable Use Policy</h1>
      <p style={{ color: '#9ca3af', marginBottom: '32px' }}>Last Updated: July 24, 2026</p>

      <section style={{ marginBottom: '32px', lineHeight: '1.6' }}>
        <h2 style={{ fontSize: '20px', color: '#f3f4f6', borderBottom: '1px solid #1f2937', paddingBottom: '8px' }}>1. Acceptable Use & Prohibited Workloads</h2>
        <p>Developers and Hosts using Kynetic AI must comply with our Acceptable Use Policy. The following are strictly prohibited:</p>
        <ul>
          <li>Cryptocurrency mining (unauthorised background mining)</li>
          <li>Hosting malware, botnets, or ransomware</li>
          <li>Unauthorised network scanning or DDoS attacks</li>
          <li>Illegal or infringing content</li>
        </ul>
      </section>

      <section style={{ marginBottom: '32px', lineHeight: '1.6' }}>
        <h2 style={{ fontSize: '20px', color: '#f3f4f6', borderBottom: '1px solid #1f2937', paddingBottom: '8px' }}>2. Enforcement & Kill-Switch</h2>
        <p>Kynetic AI employs eBPF kernel anomaly detection and emergency administrative kill-switch controls. Violations will result in immediate workload termination, account suspension, and wallet forfeiture.</p>
      </section>
    </div>
  );
}
