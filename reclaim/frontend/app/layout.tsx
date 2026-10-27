import "./globals.css";
import { OfflineBoot } from "@/components/OfflineBoot";
import type { Metadata } from "next";
import { EB_Garamond, Figtree, JetBrains_Mono } from "next/font/google";

const ebGaramond = EB_Garamond({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
  weight: ["400", "500", "600", "700", "800"],
  style: ["normal", "italic"],
});

const figtree = Figtree({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: ["300", "400", "500", "600", "700", "800", "900"],
  style: ["normal", "italic"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "RECLAIM · From problem to proof to resolution",
  description: "RECLAIM — Universal Evidence & Action Operating System. Transform consumer disputes into verified statutory claims with Action Fabric and Human Approval Gate.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${ebGaramond.variable} ${figtree.variable} ${jetbrainsMono.variable}`}>
      <body className="font-sans antialiased text-[#1a1715]"><OfflineBoot />{children}</body>
    </html>
  );
}

