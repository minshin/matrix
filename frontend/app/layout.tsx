import type { Metadata } from "next";
import { DM_Serif_Display, Space_Mono } from "next/font/google";
import "./globals.css";

const serif = DM_Serif_Display({ subsets: ["latin"], weight: "400", variable: "--font-serif" });
const mono = Space_Mono({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Matrix Dashboard",
  description: "Layered probability inference dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className={`${serif.variable} ${mono.variable} min-h-screen`}>
        <main className="min-h-screen w-full">{children}</main>
      </body>
    </html>
  );
}
