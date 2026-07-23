'use client';

import React from 'react';

interface EmptyStateProps {
  title: string;
  description: string;
  actionText?: string;
  onAction?: () => void;
}

export function EmptyState({ title, description, actionText, onAction }: EmptyStateProps) {
  return (
    <div style={{
      textAlign: 'center',
      padding: '48px 24px',
      backgroundColor: '#111827',
      border: '1px border-dashed #1f2937',
      borderRadius: '8px',
    }}>
      <div style={{ fontSize: '36px', marginBottom: '12px' }}>📦</div>
      <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#f3f4f6', marginBottom: '8px' }}>{title}</h3>
      <p style={{ color: '#9ca3af', fontSize: '14px', maxWidth: '400px', margin: '0 auto 20px' }}>{description}</p>
      {actionText && onAction && (
        <button
          onClick={onAction}
          style={{
            backgroundColor: '#38bdf8',
            color: '#090d16',
            fontWeight: 'bold',
            border: 'none',
            padding: '10px 20px',
            borderRadius: '6px',
            cursor: 'pointer',
          }}
        >
          {actionText}
        </button>
      )}
    </div>
  );
}
