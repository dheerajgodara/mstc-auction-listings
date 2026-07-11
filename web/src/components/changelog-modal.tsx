"use client";
import { useEffect, useState } from "react";
import { Sparkles, X } from "lucide-react";
import {
  CHANGELOG,
  latestChangelogVersion,
  markChangelogSeen,
  shouldShowChangelog,
} from "@/lib/changelog";
import { cn } from "@/lib/utils";
export function ChangelogModal({
  forceOpen,
  onClose,
  className,
}: {
  forceOpen?: boolean;
  onClose?: () => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const latest = latestChangelogVersion();
  const entry = CHANGELOG[0];
  useEffect(() => {
    if (forceOpen) {
      setOpen(true);
      return;
    }
    setOpen(shouldShowChangelog());
  }, [forceOpen]);
  const handleClose = () => {
    if (latest) markChangelogSeen(latest);
    setOpen(false);
    onClose?.();
  };
  if (!open || !entry) return null;
  return (
    <div
      className={cn(
        "fixed inset-0 z-[70] flex items-center justify-center p-4",
        className,
      )}
      role="dialog"
      aria-modal="true"
      aria-labelledby="changelog-title"
    >
      {" "}
      <button
        type="button"
        className="absolute inset-0 bg-black/45"
        aria-label="Close changelog"
        onClick={handleClose}
      />{" "}
      <div className="surface-elevated relative w-full max-w-md p-5 shadow-2xl">
        {" "}
        <button
          type="button"
          onClick={handleClose}
          className="absolute right-3 top-3 rounded-lg p-1 text-muted-foreground hover:bg-card"
          aria-label="Close"
        >
          {" "}
          <X className="h-4 w-4" />{" "}
        </button>{" "}
        <div className="mb-4 flex items-center gap-2">
          {" "}
          <Sparkles className="h-5 w-5 text-muted-foreground" />{" "}
          <div>
            {" "}
            <p className="text-xs font-medium uppercase tracking-wide link-action">
              {" "}
              What&apos;s new · v{entry.version}{" "}
            </p>{" "}
            <h2
              id="changelog-title"
              className="text-lg font-semibold text-foreground"
            >
              {" "}
              {entry.title}{" "}
            </h2>{" "}
          </div>{" "}
        </div>{" "}
        <p className="mb-3 text-xs text-muted-foreground">{entry.date}</p>{" "}
        <ul className="mb-5 space-y-2 text-sm text-muted-foreground">
          {" "}
          {entry.items.map((item) => (
            <li key={item} className="flex gap-2">
              {" "}
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted" />{" "}
              <span>{item}</span>{" "}
            </li>
          ))}{" "}
        </ul>{" "}
        <button
          type="button"
          onClick={handleClose}
          className="btn-primary w-full"
        >
          {" "}
          Got it{" "}
        </button>{" "}
      </div>{" "}
    </div>
  );
}
