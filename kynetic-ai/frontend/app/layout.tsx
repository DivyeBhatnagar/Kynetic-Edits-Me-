import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: {
    default: "Kynetic AI — Compute Marketplace",
    template: "%s | Kynetic AI",
  },
  description:
    "Rent peer-to-peer GPU, CPU, and compute from verified hosts. Built for AI developers.",
  keywords: ["GPU rental", "compute marketplace", "AI cloud", "distributed compute"],
  openGraph: {
    type: "website",
    siteName: "Kynetic AI",
    images: [{ url: "/og-image.png" }],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>
        <Navbar />
        <main className="pt-16 min-h-screen">{children}</main>
      </body>
    </html>
  );
}
