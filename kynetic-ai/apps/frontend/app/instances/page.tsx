'use client';

import React, { useState } from 'react';

interface Instance {
  id: string;
  name: string;
  gpu: string;
  status: 'running' | 'stopped' | 'terminated';
  sshCommand: string;
  httpUrl: string;
  costPerHour: string;
  uptimeSeconds: number;
}

export default function InstanceManagementPage() {
  const [instances, setInstances] = useState<Instance[]>([
    {
      id: "inst-88219",
      name: "PyTorch Fine-Tuning Node #1",
      gpu: "NVIDIA RTX 4090 (24GB)",
      status: "running",
      sshCommand: "ssh -i ~/.ssh/id_rsa developer@34.120.91.44 -p 22022",
      httpUrl: "https://inst-88219.kynetic.app",
      costPerHour: "$0.50",
      uptimeSeconds: 7420,
    },
    {
      id: "inst-99104",
      name: "Llama 3 70B Inference Server",
      gpu: "2x NVIDIA A100 (80GB)",
      status: "stopped",
      sshCommand: "ssh -i ~/.ssh/id_rsa developer@34.120.91.45 -p 22023",
      httpUrl: "https://inst-99104.kynetic.app",
      costPerHour: "$2.40",
      uptimeSeconds: 0,
    },
  ]);

  const [selectedInst, setSelectedInst] = useState<Instance | null>(instances[0]);

  const handleAction = (instId: string, action: 'start' | 'stop' | 'terminate') => {
    setInstances(prev =>
      prev.map(i => {
        if (i.id === instId) {
          if (action === 'start') return { ...i, status: 'running' };
          if (action === 'stop') return { ...i, status: 'stopped' };
          if (action === 'terminate') return { ...i, status: 'terminated' };
        }
        return i;
      })
    );
  };

  return (
    <div style={{ maxWidth: '1100px', margin: '40px auto', padding: '0 20px', fontFamily: 'system-ui, sans-serif', color: '#f3f4f6' }}>
      <h1 style={{ fontSize: '28px', fontWeight: 'bold', color: '#38bdf8', marginBottom: '8px' }}>My Active Compute Instances</h1>
      <p style={{ color: '#9ca3af', marginBottom: '32px' }}>Manage, monitor telemetry, and connect to your rented compute nodes.</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px' }}>
        {/* Instances Table */}
        <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #1f2937', color: '#9ca3af', fontSize: '14px' }}>
                <th style={{ padding: '16px' }}>Instance Name</th>
                <th style={{ padding: '16px' }}>GPU Model</th>
                <th style={{ padding: '16px' }}>Status</th>
                <th style={{ padding: '16px' }}>Rate</th>
                <th style={{ padding: '16px' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {instances.map(inst => (
                <tr
                  key={inst.id}
                  onClick={() => setSelectedInst(inst)}
                  style={{
                    borderBottom: '1px solid #1f2937',
                    cursor: 'pointer',
                    backgroundColor: selectedInst?.id === inst.id ? '#1f2937' : 'transparent',
                  }}
                >
                  <td style={{ padding: '16px', fontWeight: 'bold' }}>{inst.name}</td>
                  <td style={{ padding: '16px', color: '#9ca3af' }}>{inst.gpu}</td>
                  <td style={{ padding: '16px' }}>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      fontWeight: 'bold',
                      backgroundColor: inst.status === 'running' ? '#065f46' : inst.status === 'stopped' ? '#374151' : '#991b1b',
                      color: inst.status === 'running' ? '#34d399' : inst.status === 'stopped' ? '#9ca3af' : '#f87171',
                    }}>
                      {inst.status.toUpperCase()}
                    </span>
                  </td>
                  <td style={{ padding: '16px', fontWeight: 'bold', color: '#38bdf8' }}>{inst.costPerHour}/hr</td>
                  <td style={{ padding: '16px' }}>
                    {inst.status === 'running' && (
                      <button onClick={(e) => { e.stopPropagation(); handleAction(inst.id, 'stop'); }} style={{ padding: '6px 12px', marginRight: '6px', borderRadius: '4px', backgroundColor: '#d97706', color: 'white', border: 'none', cursor: 'pointer' }}>Stop</button>
                    )}
                    {inst.status === 'stopped' && (
                      <button onClick={(e) => { e.stopPropagation(); handleAction(inst.id, 'start'); }} style={{ padding: '6px 12px', marginRight: '6px', borderRadius: '4px', backgroundColor: '#10b981', color: 'white', border: 'none', cursor: 'pointer' }}>Start</button>
                    )}
                    {inst.status !== 'terminated' && (
                      <button onClick={(e) => { e.stopPropagation(); handleAction(inst.id, 'terminate'); }} style={{ padding: '6px 12px', borderRadius: '4px', backgroundColor: '#ef4444', color: 'white', border: 'none', cursor: 'pointer' }}>Terminate</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Drawer Details & Connection Info */}
        {selectedInst && (
          <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '20px' }}>
            <h2 style={{ fontSize: '18px', marginTop: 0, borderBottom: '1px solid #1f2937', paddingBottom: '12px' }}>Connection & Details</h2>
            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '12px', color: '#9ca3af' }}>Instance ID:</label>
              <div style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{selectedInst.id}</div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '12px', color: '#9ca3af' }}>SSH Connection String:</label>
              <pre style={{ backgroundColor: '#090d16', padding: '10px', borderRadius: '4px', fontSize: '12px', color: '#34d399', overflowX: 'auto' }}>
                {selectedInst.sshCommand}
              </pre>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '12px', color: '#9ca3af' }}>Web UI HTTP Tunnel:</label>
              <div style={{ marginTop: '4px' }}>
                <a href={selectedInst.httpUrl} target="_blank" rel="noreferrer" style={{ color: '#38bdf8', fontSize: '14px' }}>{selectedInst.httpUrl} ↗</a>
              </div>
            </div>

            <button style={{ width: '100%', padding: '10px', backgroundColor: '#1f2937', color: 'white', border: '1px solid #374151', borderRadius: '6px', cursor: 'pointer' }}>
              🔑 Download Fernet Encrypted Key
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
