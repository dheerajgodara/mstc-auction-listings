import { StatusPageApp } from "@/components/status-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";

export const metadata = NOINDEX_METADATA;

export default function StatusPage() {
  return <StatusPageApp />;
}
