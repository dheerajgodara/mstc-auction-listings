import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MSTC Auction Listings",
  description: "Search MSTC e-auctions",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
