"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const NAV_LINKS = [
  { href: "/marketplace", label: "Marketplace" },
  { href: "/wallet", label: "Wallet" },
];

export default function Navbar() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        height: "64px",
        display: "flex",
        alignItems: "center",
        padding: "0 24px",
        background: "linear-gradient(90deg, hsl(224 27% 6% / 0.92), hsl(224 20% 10% / 0.92))",
        backdropFilter: "blur(16px)",
        borderBottom: "1px solid hsl(224 20% 20%)",
      }}
    >
      {/* Logo */}
      <Link href="/" style={{ display: "flex", alignItems: "center", gap: "10px", textDecoration: "none" }}>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: "linear-gradient(135deg, hsl(258 90% 60%), hsl(195 100% 50%))",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 16,
            fontWeight: 700,
            color: "#fff",
            fontFamily: "var(--font-display)",
            boxShadow: "0 0 16px hsl(258 90% 66% / 0.5)",
          }}
        >
          K
        </div>
        <span
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: 18,
            background: "linear-gradient(135deg, hsl(258 90% 76%) 0%, hsl(195 100% 60%) 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Kynetic AI
        </span>
      </Link>

      {/* Desktop Nav */}
      <nav style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4 }}>
        {NAV_LINKS.map((link) => {
          const active = pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              style={{
                padding: "6px 14px",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 500,
                textDecoration: "none",
                color: active ? "hsl(258 90% 76%)" : "hsl(220 10% 65%)",
                background: active ? "hsl(258 90% 66% / 0.12)" : "transparent",
                border: active ? "1px solid hsl(258 90% 66% / 0.3)" : "1px solid transparent",
                transition: "all 0.15s ease",
              }}
            >
              {link.label}
            </Link>
          );
        })}

        <Link
          href="/wallet"
          className="btn-primary"
          style={{ marginLeft: 8, padding: "7px 18px", fontSize: 13 }}
        >
          Get Started
        </Link>
      </nav>
    </header>
  );
}
