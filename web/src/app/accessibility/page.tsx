import type { Metadata } from "next";
import { AccessibilityPageApp } from "@/components/accessibility-page-app";
export const metadata: Metadata = {
  title: "Accessibility statement",
  description: "Accessibility commitment for the auction discovery site.",
};
export default function AccessibilityPage() {
  return (
    <div className="surface-base min-h-screen">
      {" "}
      <AccessibilityPageApp />{" "}
    </div>
  );
}
