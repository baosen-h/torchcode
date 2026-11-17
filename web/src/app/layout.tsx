import type { Metadata } from "next";
import "./globals.css";
import "./library.css";
import { LanguageProvider } from "@/lib/i18n";
import { LibraryProvider } from "@/components/library-provider";
import { SiteHeader } from "@/components/ui";

export const metadata: Metadata = {
  title: "TorchCode",
  description: "A personal workspace for machine learning code practice",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className="h-full antialiased"
    >
      <body className="h-full flex flex-col overflow-hidden"><LanguageProvider><LibraryProvider><SiteHeader />{children}</LibraryProvider></LanguageProvider></body>
    </html>
  );
}
