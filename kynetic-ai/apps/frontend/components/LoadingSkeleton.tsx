'use client';

import React from 'react';

export function CardSkeleton() {
  return (
    <div style={{
      backgroundColor: '#111827',
      border: '1px solid #1f2937',
      borderRadius: '8px',
      padding: '20px',
      animation: 'pulse 1.5s infinite ease-in-out',
    }}>
      <div style={{ width: '40%', height: '16px', backgroundColor: '#1f2937', borderRadius: '4px', marginBottom: '12px' }} />
      <div style={{ width: '80%', height: '24px', backgroundColor: '#374151', borderRadius: '4px', marginBottom: '8px' }} />
      <div style={{ width: '60%', height: '14px', backgroundColor: '#1f2937', borderRadius: '4px' }} />
    </div>
  );
}

export function TableRowSkeleton() {
  return (
    <tr style={{ borderBottom: '1px solid #1f2937' }}>
      <td style={{ padding: '16px' }}><div style={{ width: '80px', height: '16px', backgroundColor: '#1f2937', borderRadius: '4px' }} /></td>
      <td style={{ padding: '16px' }}><div style={{ width: '140px', height: '16px', backgroundColor: '#1f2937', borderRadius: '4px' }} /></td>
      <td style={{ padding: '16px' }}><div style={{ width: '100px', height: '16px', backgroundColor: '#1f2937', borderRadius: '4px' }} /></td>
      <td style={{ padding: '16px' }}><div style={{ width: '60px', height: '16px', backgroundColor: '#1f2937', borderRadius: '4px' }} /></td>
    </tr>
  );
}
