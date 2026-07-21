"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { isLongSummary, truncateAtSentence } from "@/lib/text-summary";

/** Expandable body copy with sentence-aware preview (keeps full text in DOM when expanded). */
export function ExpandableText({
  text,
  previewLen = 600,
  className,
}: {
  text: string;
  previewLen?: number;
  className?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const long = isLongSummary(text, previewLen);
  const shown = !long || expanded ? text : truncateAtSentence(text, previewLen);

  return (
    <div className={cn("space-y-2", className)}>
      <p className="whitespace-pre-wrap text-sm text-muted-foreground">{shown}</p>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-footnote font-medium link-action hover:underline"
        >
          {expanded ? "Show less" : "Read more"}
        </button>
      )}
    </div>
  );
}
