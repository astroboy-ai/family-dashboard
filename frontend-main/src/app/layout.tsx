import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AppRoot } from "@/components/app-root";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "FamilyOS",
  description: "Family notes and shared routines",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <AppRoot>{children}</AppRoot>
      </body>
    </html>
  );
}
