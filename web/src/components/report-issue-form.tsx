"use client";
import { AlertCircle, ExternalLink } from "lucide-react";
const REPORT_FORM_URL = process.env.NEXT_PUBLIC_REPORT_FORM_URL?.trim();
const REPORT_EMAIL = "support@mstc-auction-listings.example";
export function ReportIssueForm({
  auctionId,
  auctionTitle,
  className,
}: {
  auctionId: string;
  auctionTitle?: string;
  className?: string;
}) {
  const subject = encodeURIComponent(`Issue report: Auction ${auctionId}`);
  const body = encodeURIComponent(
    [
      `Auction ID: ${auctionId}`,
      auctionTitle ? `Title: ${auctionTitle}` : null,
      "",
      "Describe the issue:",
      "",
      `Page URL: ${typeof window !== "undefined" ? window.location.href : ""}`,
    ]
      .filter(Boolean)
      .join("\n"),
  );
  if (REPORT_FORM_URL) {
    const url = new URL(REPORT_FORM_URL);
    url.searchParams.set("auction_id", auctionId);
    if (auctionTitle) url.searchParams.set("title", auctionTitle);
    return (
      <div className={className}>
        {" "}
        <a
          href={url.toString()}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-secondary inline-flex items-center gap-2 text-xs"
        >
          {" "}
          <AlertCircle className="h-3.5 w-3.5" /> Report an issue{" "}
          <ExternalLink className="h-3 w-3" />{" "}
        </a>{" "}
      </div>
    );
  }
  return (
    <div className={className}>
      {" "}
      <a
        href={`mailto:${REPORT_EMAIL}?subject=${subject}&body=${body}`}
        className="btn-secondary inline-flex items-center gap-2 text-xs"
      >
        {" "}
        <AlertCircle className="h-3.5 w-3.5" /> Report an issue{" "}
      </a>{" "}
    </div>
  );
}
