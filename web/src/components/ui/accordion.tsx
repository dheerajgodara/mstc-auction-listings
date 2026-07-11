"use client";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
export function AccordionItem({
  title,
  children,
  defaultOpen = false,
  className,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={cn("border-b border-border", className)}>
      {" "}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 py-4 text-left focus-ring"
        aria-expanded={open}
      >
        {" "}
        <span className="text-sm font-medium text-foreground">
          {title}
        </span>{" "}
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-accordion",
            open && "rotate-180",
          )}
        />{" "}
      </button>{" "}
      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-accordion ease-marketplace",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        {" "}
        <div className="overflow-hidden">
          {" "}
          <div className="pb-4 text-body-sm">{children}</div>{" "}
        </div>{" "}
      </div>{" "}
    </div>
  );
}
