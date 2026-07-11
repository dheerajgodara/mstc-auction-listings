import { LaunchReadinessPageApp } from "@/components/launch-readiness-page-app";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";

export const metadata = NOINDEX_METADATA;

export default function LaunchReadinessPage() {
  return <LaunchReadinessPageApp />;
}
