'use client';

import React, { useState } from 'react';

export default function HostOnboardingWizard() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [verifying, setVerifying] = useState(false);
  const [verifiedHardware, setVerifiedHardware] = useState<any>(null);
  const [hourlyUsd, setHourlyUsd] = useState("0.50");
  const [published, setPublished] = useState(false);

  const runVerificationSimulation = async () => {
    setVerifying(true);
    // Simulate host agent sending hardware benchmark payload
    setTimeout(() => {
      setVerifiedHardware({
        gpu_model: "NVIDIA RTX 4090",
        vram_gb: 24,
        cuda_cores: 16384,
        nvme_write_mbps: 3200,
        benchmark_passed: true,
      });
      setVerifying(false);
      setStep(3);
    }, 2000);
  };

  return (
    <div style={{ maxWidth: '800px', margin: '40px auto', padding: '0 20px', fontFamily: 'system-ui, sans-serif', color: '#f3f4f6' }}>
      <h1 style={{ fontSize: '28px', fontWeight: 'bold', color: '#38bdf8', marginBottom: '8px' }}>Host Hardware Onboarding Wizard</h1>
      <p style={{ color: '#9ca3af', marginBottom: '32px' }}>Monetize your idle gaming PC, workstation, or server in 3 simple steps.</p>

      {/* Progress Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '32px', borderBottom: '1px solid #1f2937', paddingBottom: '16px' }}>
        <div style={{ color: step >= 1 ? '#38bdf8' : '#6b7280', fontWeight: 'bold' }}>1. Download Agent</div>
        <div style={{ color: step >= 2 ? '#38bdf8' : '#6b7280', fontWeight: 'bold' }}>2. Hardware Verification</div>
        <div style={{ color: step >= 3 ? '#38bdf8' : '#6b7280', fontWeight: 'bold' }}>3. Set Price & Publish</div>
      </div>

      {/* Step 1: Install Agent */}
      {step === 1 && (
        <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '24px', borderRadius: '8px' }}>
          <h2 style={{ fontSize: '20px', marginTop: 0 }}>Step 1: Download & Run Kynetic Host Agent</h2>
          <p style={{ color: '#9ca3af' }}>Run this single command in your Linux terminal or PowerShell prompt:</p>
          <pre style={{ backgroundColor: '#090d16', padding: '16px', borderRadius: '6px', border: '1px solid #374151', color: '#34d399', overflowX: 'auto' }}>
            curl -sSL https://get.kynetic.ai/host-agent.sh | bash -s -- --join-token=kt_live_998231
          </pre>
          <button
            onClick={() => setStep(2)}
            style={{ backgroundColor: '#38bdf8', color: '#090d16', fontWeight: 'bold', border: 'none', padding: '12px 24px', borderRadius: '6px', marginTop: '16px', cursor: 'pointer' }}
          >
            Agent Installed — Next Step →
          </button>
        </div>
      )}

      {/* Step 2: Verification */}
      {step === 2 && (
        <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '24px', borderRadius: '8px' }}>
          <h2 style={{ fontSize: '20px', marginTop: 0 }}>Step 2: Automated Hardware Benchmark & Anti-Spoof Test</h2>
          <p style={{ color: '#9ca3af' }}>Running PyTorch matrix multiplication benchmark and verifying VRAM & WireGuard NAT tunnel...</p>
          <button
            onClick={runVerificationSimulation}
            disabled={verifying}
            style={{ backgroundColor: '#10b981', color: 'white', fontWeight: 'bold', border: 'none', padding: '12px 24px', borderRadius: '6px', cursor: 'pointer' }}
          >
            {verifying ? "Verifying Hardware..." : "⚡ Run Verification Benchmark"}
          </button>
        </div>
      )}

      {/* Step 3: Pricing & Publish */}
      {step === 3 && (
        <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '24px', borderRadius: '8px' }}>
          <h2 style={{ fontSize: '20px', marginTop: 0, color: '#34d399' }}>✓ Hardware Verified: {verifiedHardware?.gpu_model} ({verifiedHardware?.vram_gb}GB VRAM)</h2>
          <p style={{ color: '#9ca3af' }}>Set your hourly rental price (85% earnings paid directly to your wallet):</p>
          <div style={{ margin: '20px 0' }}>
            <label style={{ display: 'block', marginBottom: '8px' }}>Hourly Rental Rate ($ USD / hr):</label>
            <input
              type="number"
              step="0.05"
              value={hourlyUsd}
              onChange={(e) => setHourlyUsd(e.target.value)}
              style={{ padding: '10px', borderRadius: '6px', backgroundColor: '#1f2937', border: '1px solid #374151', color: 'white', fontSize: '16px', width: '200px' }}
            />
            <span style={{ marginLeft: '12px', color: '#9ca3af' }}>≈ ₹{(parseFloat(hourlyUsd || "0") * 84).toFixed(2)} INR / hr</span>
          </div>

          {!published ? (
            <button
              onClick={() => setPublished(true)}
              style={{ backgroundColor: '#38bdf8', color: '#090d16', fontWeight: 'bold', border: 'none', padding: '12px 24px', borderRadius: '6px', cursor: 'pointer' }}
            >
              🚀 Publish Listing on Marketplace
            </button>
          ) : (
            <div style={{ padding: '16px', backgroundColor: '#065f46', borderRadius: '6px', color: '#34d399', fontWeight: 'bold' }}>
              🎉 Listing Live! Your hardware is now visible on the marketplace.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
