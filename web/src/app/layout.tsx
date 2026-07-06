import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";

const SITE_URL = "https://lightcyan-camel-979846.hostingersite.com/auctions/";
const GA_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID?.trim();

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "MSTC, GeM & eAuction Listings | Discover Public Auctions",
  description:
    "Search and filter MSTC, GeM Forward, and eAuction public listings with import dates, documents, and buyer-ready summaries.",
  alternates: { canonical: SITE_URL },
  openGraph: {
    title: "MSTC, GeM & eAuction Listings",
    description:
      "Discover public auction listings across MSTC, GeM Forward, and eAuction sources.",
    url: SITE_URL,
    type: "website",
    siteName: "Auction Listings",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        {children}
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
