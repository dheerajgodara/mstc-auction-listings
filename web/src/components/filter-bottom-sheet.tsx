"use client";
import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
export function FilterBottomSheet({
  open,
  onClose,
  onApply,
  onReset,
  title = "Filters",
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  onApply: () => void;
  onReset: () => void;
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {" "}
      {open && (
        <div
          className="fixed inset-0 z-50 sm:hidden"
          role="dialog"
          aria-modal="true"
          aria-label={title}
        >
          {" "}
          <motion.button
            type="button"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 bg-black/50"
            aria-label="Close filters"
            onClick={onClose}
          />
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 28, stiffness: 320 }}
            className={cn(
              "absolute inset-x-0 bottom-0 flex max-h-[90vh] flex-col rounded-t-[var(--radius-xl)] border border-border bg-card shadow-modal",
              className,
            )}
          >
            {" "}
            <div className="flex items-center justify-between border-b border-border px-4 py-4">
              <h2 className="text-title text-foreground">{title}</h2>
              <button
                type="button"
                onClick={onClose}
                className="btn-secondary !min-h-[44px] !min-w-[44px] !rounded-full !p-0"
                aria-label="Close"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
            <div className="flex gap-2 border-t border-border p-4">
              {" "}
              <button
                type="button"
                onClick={onReset}
                className="btn-secondary flex-1"
              >
                {" "}
                Reset{" "}
              </button>{" "}
              <button
                type="button"
                onClick={onApply}
                className="btn-primary flex-1"
              >
                {" "}
                Apply{" "}
              </button>{" "}
            </div>{" "}
          </motion.div>{" "}
        </div>
      )}{" "}
    </AnimatePresence>
  );
}
