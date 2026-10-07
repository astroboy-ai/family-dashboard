import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AppRoot } from "@/components/app-root";
import { ServiceWorkerRegistrar } from "@/components/service-worker-registrar";
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
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-32.png", type: "image/png", sizes: "32x32" },
      { url: "/icon-192.png", type: "image/png", sizes: "192x192" },
    ],
    // iOS ignores the manifest icons and looks for this link instead.
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  // Standalone on iOS: without this, launching from the home screen opens Safari.
  appleWebApp: {
    capable: true,
    title: "FamilyOS",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  themeColor: "#17654c",
  width: "device-width",
  initialScale: 1,
  // The app draws its own chrome; let it reach the notch and the edges.
  viewportFit: "cover",
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
        <ServiceWorkerRegistrar />
      </body>
    </html>
  );
}
