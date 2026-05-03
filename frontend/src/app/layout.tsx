import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import Image from "next/image";
import { Toaster } from "@/components/toaster";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Workless",
  description: "AI-powered accounting with DATEV export",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="de"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="mx-auto flex h-14 max-w-6xl items-center px-6 lg:px-8">
            <a href="/clients" className="flex items-center gap-2 text-[15px] font-bold tracking-tight">
              <Image src="/workless-logo.png" alt="Workless" width={28} height={28} className="rounded" />
              <span>Workless</span>
            </a>
          </div>
        </header>
        <div className="flex-1">{children}</div>
        <Toaster />
      </body>
    </html>
  );
}
