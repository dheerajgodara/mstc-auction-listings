import type { Metadata, Viewport } from "next";
import { Figtree } from "next/font/google";
import Script from "next/script";
import { ThemeProvider } from "@/components/theme-provider";
import { PaywallProvider } from "@/components/upgrade-prompt";
import { ServiceWorkerRegister } from "@/components/service-worker-register";
import { SITE_BASE_URL } from "@/lib/site-url";
import "./globals.css";

/** Legal Cereal-compatible geometric sans (Airbnb Cereal VF is not redistributable). */
const figtree = Figtree({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-figtree",
  weight: ["400", "500", "600", "700"],
});

const GA_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID?.trim();

export const metadata: Metadata = {
  metadataBase: new URL(SITE_BASE_URL),
  title: "Scrap Auction India | MSTC, GeM & eAuction Listings",
  description:
    "Search and filter scrap auction listings across MSTC, GeM Forward, and eAuction.gov.in — import dates, documents, and buyer-ready summaries for discovery.",
  alternates: { canonical: SITE_BASE_URL },
  manifest: "/auctions/manifest.webmanifest",
  applicationName: "Scrap Auction India",
  appleWebApp: {
    capable: true,
    title: "Scrap Auction India",
    statusBarStyle: "default",
  },
  openGraph: {
    title: "Scrap Auction India | MSTC, GeM & eAuction",
    description:
      "Discover scrap and surplus auction listings across MSTC, GeM Forward, and eAuction sources in India.",
    url: SITE_BASE_URL,
    type: "website",
    siteName: "Scrap Auction India",
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={figtree.variable} suppressHydrationWarning>
      <body className="font-sans antialiased">
        <ThemeProvider>
          <PaywallProvider>{children}</PaywallProvider>
        </ThemeProvider>
        <ServiceWorkerRegister />
        {GA_ID ? (
          <>
            <Script
              src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`}
              strategy="afterInteractive"
            />
            <Script id="ga4-init" strategy="afterInteractive">
              {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${GA_ID}',{send_page_view:false});`}
            </Script>
          </>
        ) : null}
      </body>
    </html>
  );
}
