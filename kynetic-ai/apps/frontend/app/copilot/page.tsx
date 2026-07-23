'use client';

import React, { useState } from 'react';

interface ChatMessage {
  sender: 'user' | 'copilot';
  text: string;
  recommendation?: {
    gpu: string;
    vram: string;
    rate: string;
    hostLocation: string;
    clusterId: string;
  };
}

export default function CopilotChatPage() {
  const [inputPrompt, setInputPrompt] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      sender: 'copilot',
      text: "👋 Hi! I'm Kynetic AI Copilot. Tell me about your workload, framework, or budget, and I'll route you to the optimal compute node.",
    },
  ]);

  const handleSend = () => {
    if (!inputPrompt.trim()) return;

    const userMsg: ChatMessage = { sender: 'user', text: inputPrompt };
    setMessages(prev => [...prev, userMsg]);
    setInputPrompt("");

    // Simulate AI Resource Router WebSocket response
    setTimeout(() => {
      const copilotMsg: ChatMessage = {
        sender: 'copilot',
        text: "Based on your requirements, I've matched the optimal hardware node in our marketplace:",
        recommendation: {
          gpu: "NVIDIA RTX 4090 (24GB VRAM)",
          vram: "24 GB GDDR6X",
          rate: "$0.50 / hr",
          hostLocation: "Mumbai, IN (Latency: 14ms)",
          clusterId: "node_rtx4090_mumbai_0192",
        },
      };
      setMessages(prev => [...prev, copilotMsg]);
    }, 1000);
  };

  return (
    <div style={{ maxWidth: '900px', margin: '40px auto', padding: '0 20px', fontFamily: 'system-ui, sans-serif', color: '#f3f4f6' }}>
      <h1 style={{ fontSize: '28px', fontWeight: 'bold', color: '#38bdf8', marginBottom: '8px' }}>AI Resource Copilot</h1>
      <p style={{ color: '#9ca3af', marginBottom: '24px' }}>Interactive AI assistant matching workloads to hardware nodes.</p>

      {/* Chat Messages Window */}
      <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '20px', minHeight: '400px', marginBottom: '20px' }}>
        {messages.map((m, idx) => (
          <div key={idx} style={{ marginBottom: '16px', textAlign: m.sender === 'user' ? 'right' : 'left' }}>
            <div style={{
              display: 'inline-block',
              padding: '12px 16px',
              borderRadius: '8px',
              maxWidth: '80%',
              backgroundColor: m.sender === 'user' ? '#0284c7' : '#1f2937',
              color: '#f3f4f6',
            }}>
              <div>{m.text}</div>

              {/* Recommendation Card */}
              {m.recommendation && (
                <div style={{ marginTop: '12px', padding: '12px', backgroundColor: '#090d16', borderRadius: '6px', border: '1px solid #38bdf8', textAlign: 'left' }}>
                  <div style={{ color: '#38bdf8', fontWeight: 'bold' }}>⚡ Recommended Node: {m.recommendation.gpu}</div>
                  <div style={{ fontSize: '13px', color: '#9ca3af', marginTop: '4px' }}>Location: {m.recommendation.hostLocation}</div>
                  <div style={{ fontSize: '13px', color: '#34d399', fontWeight: 'bold', marginTop: '4px' }}>Rate: {m.recommendation.rate}</div>
                  <button style={{ marginTop: '10px', backgroundColor: '#10b981', color: 'white', fontWeight: 'bold', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer' }}>
                    🚀 Deploy Workload on Node
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Input Form */}
      <div style={{ display: 'flex', gap: '12px' }}>
        <input
          type="text"
          value={inputPrompt}
          onChange={(e) => setInputPrompt(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Ask Copilot e.g., 'I need an RTX 4090 to fine-tune Llama 3 8B under $1.50/hr'..."
          style={{ flex: 1, padding: '14px', borderRadius: '6px', backgroundColor: '#111827', border: '1px solid #374151', color: 'white', fontSize: '15px' }}
        />
        <button
          onClick={handleSend}
          style={{ backgroundColor: '#38bdf8', color: '#090d16', fontWeight: 'bold', border: 'none', padding: '0 24px', borderRadius: '6px', cursor: 'pointer' }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
