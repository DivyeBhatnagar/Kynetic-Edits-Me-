import React from 'react';

export const metadata = {
  title: 'Privacy Policy & DPDP Act Statement — Kynetic AI',
  description: 'Privacy Policy, Data Collection Scope, and India DPDP Act Compliance Statement.',
};

export default function PrivacyPage() {
  return (
    <div style={{ maxWidth: '900px', margin: '0 auto', padding: '40px 20px', fontFamily: 'system-ui, sans-serif', color: '#f3f4f6', backgroundColor: '#090d16' }}>
      <h1 style={{ fontSize: '32px', fontWeight: 'bold', color: '#38bdf8', marginBottom: '16px' }}>Privacy Policy & Data Protection</h1>
      <p style={{ color: '#9ca3af', marginBottom: '32px' }}>Last Updated: July 24, 2026</p>

      <section style={{ marginBottom: '32px', lineHeight: '1.6' }}>
        <h2 style={{ fontSize: '20px', color: '#f3f4f6', borderBottom: '1px solid #1f2937', paddingBottom: '8px' }}>1. Zero Host Access & Workload Privacy</h2>
        <p>Your rented compute workloads run inside isolated Firecracker MicroVMs or container sandboxes. Hardware hosts have zero access to your container filesystem, memory space, or environment variables.</p>
      </section>

      <section style={{ marginBottom: '32px', lineHeight: '1.6' }}>
        <h2 style={{ fontSize: '20px', color: '#f3f4f6', borderBottom: '1px solid #1f2937', paddingBottom: '8px' }}>2. India DPDP Act & Data Residency</h2>
        <p>All personal data, audit logs, and tax invoices for Indian residents are stored strictly in AWS region <code>ap-south-1</code> (Mumbai, India) in full compliance with the Digital Personal Data Protection Act 2023.</p>
      </section>
    </div>
  );
}
