import type { Metadata } from "next"; /** Shared robots metadata for utility and low-value pages. */
export const NOINDEX_METADATA: Metadata = {
  robots: { index: false, follow: true },
};
