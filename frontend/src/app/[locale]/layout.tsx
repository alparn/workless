import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { NextIntlClientProvider } from "next-intl";
import { notFound } from "next/navigation";
import Image from "next/image";
import { routing } from "@/i18n/routing";
import { Toaster } from "@/components/toaster";
import { LanguageSwitcher } from "@/components/language-switcher";
import de from "@messages/de.json";
import en from "@messages/en.json";

const allMessages: Record<string, typeof de> = { de, en };

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

type Props = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function RootLayout({ children, params }: Props) {
  const { locale } = await params;

  if (!routing.locales.includes(locale as "de" | "en")) {
    notFound();
  }

  const messages = allMessages[locale] ?? allMessages[routing.defaultLocale];

  return (
    <html
      lang={locale}
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <NextIntlClientProvider locale={locale} messages={messages}>
          <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <div className="mx-auto flex h-14 max-w-6xl items-center px-6 lg:px-8">
              <a href={`/${locale}/clients`} className="flex items-center gap-2 text-[15px] font-bold tracking-tight">
                <Image src="/workless-logo.png" alt="Workless" width={28} height={28} className="rounded" />
                <span>Workless</span>
              </a>
              <div className="ml-auto">
                <LanguageSwitcher />
              </div>
            </div>
          </header>
          <div className="flex-1">{children}</div>
          <Toaster />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
