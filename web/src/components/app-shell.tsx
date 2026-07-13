"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bookmark,
  Compass,
  CreditCard,
  Layers,
  Smartphone,
  Map,
  MapPin,
  Menu,
  Moon,
  Search,
  Star,
  Sun,
  X,
} from "lucide-react";
import { useState } from "react";
import { useTheme } from "@/components/theme-provider";
import { cn } from "@/lib/utils";

function appRoute(segment: string): string {
  if (!segment) return "/";
  return `/${segment.replace(/^\/|\/$/g, "")}/`;
}

function activePath(pathname: string | null): string {
  let current = pathname?.replace(/\/$/, "") || "/";
  if (current.startsWith("/auctions")) {
    current = current.slice("/auctions".length) || "/";
  }
  return current || "/";
}

function activeSegment(segment: string): string {
  if (!segment) return "/";
  return `/${segment.replace(/^\/|\/$/g, "")}`;
}

function BrandMark() {
  return (
    <span
      className="relative inline-flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-[14px] bg-[var(--color-rausch)] text-[13px] font-black uppercase tracking-[-0.02em] text-white shadow-[0_10px_24px_rgba(224,11,65,0.28)]"
      aria-hidden
    >
      <span className="absolute -right-4 -top-4 h-8 w-8 rounded-full bg-white/24" />
      <span className="absolute -bottom-5 -left-4 h-10 w-10 rounded-full bg-black/10" />
      <span className="relative">SA</span>
    </span>
  );
}

const NAV = [
  { href: "", label: "Discover", icon: Compass },
  { href: "hub/material/ferrous_scrap/", label: "Materials", icon: Layers },
  { href: "hub/region/ncr/", label: "Regions", icon: MapPin },
  { href: "watchlist/", label: "Watchlist", icon: Star },
  { href: "pricing/", label: "Pricing", icon: CreditCard },
  { href: "app/", label: "App", icon: Smartphone },
  { href: "map/", label: "Map", icon: Map },
  { href: "status/", label: "Status", icon: Activity },
] as const;

export function AppShell({
  children,
  freshnessLabel,
  onOpenSearch,
}: {
  children: React.ReactNode;
  freshnessLabel?: string;
  onOpenSearch?: () => void;
}) {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (segment: string) => {
    const current = activePath(pathname);
    const normalized = activeSegment(segment);
    return current === normalized || current.startsWith(`${normalized}/`);
  };

  const navLinks = (
    <>
      {NAV.map(({ href, label, icon: Icon }) => (
        <Link
          key={href || "discover"}
          href={appRoute(href)}
          onClick={() => setMobileOpen(false)}
          className={cn(
            "inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-full px-3 text-sm font-semibold transition-colors duration-hover",
            isActive(href)
              ? "text-action"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          <Icon className="h-4 w-4 shrink-0" aria-hidden />
          <span>{label}</span>
        </Link>
      ))}
      <Link
        href={appRoute("saved/")}
        onClick={() => setMobileOpen(false)}
        className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-full px-3 text-sm font-semibold text-muted-foreground hover:text-foreground"
      >
        <Bookmark className="h-4 w-4 shrink-0" aria-hidden />
        <span>Saved</span>
      </Link>
      <Link
        href={appRoute("liquidate/")}
        onClick={() => setMobileOpen(false)}
        className="inline-flex min-h-[44px] items-center rounded-full px-3 text-xs font-semibold text-muted-foreground hover:text-foreground"
      >
        Liquidate
      </Link>
    </>
  );

  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-card focus:px-4 focus:py-2 focus:shadow-lg"
      >
        Skip to main content
      </a>
      <header className="sticky top-0 z-[var(--z-globalnav)] border-b border-border surface-translucent-nav">
        <div className="container-marketplace flex h-[var(--nav-height-regular)] items-center justify-between gap-3">
          <Link
            href="/"
            className="group inline-flex items-center gap-3 font-display text-base font-bold tracking-tight text-foreground"
            aria-label="Scrap Auction India home"
          >
            <BrandMark />
            <span className="hidden leading-none sm:inline">
              <span className="block text-[15px] font-black tracking-[-0.01em]">
                Scrap Auction India
              </span>
              <span className="block text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Live auction intelligence
              </span>
            </span>
          </Link>
          <nav
            className="hidden items-center gap-1 lg:flex"
            aria-label="Global"
          >
            {navLinks}
          </nav>
          <div className="flex items-center gap-1">
            {freshnessLabel && (
              <p
                className="mr-2 hidden text-footnote text-muted-foreground xl:block"
                title="Data pipeline freshness"
              >
                {freshnessLabel}
              </p>
            )}
            {onOpenSearch && (
              <button
                type="button"
                onClick={onOpenSearch}
                className="btn-secondary !min-h-[44px] !min-w-[44px] !rounded-full !px-0"
                aria-label="Search auctions"
              >
                <Search className="h-4 w-4" aria-hidden />
              </button>
            )}
            <button
              type="button"
              onClick={toggleTheme}
              className="btn-secondary !min-h-[44px] !min-w-[44px] !rounded-full !px-0"
              aria-label={
                theme === "dark"
                  ? "Switch to light mode"
                  : "Switch to dark mode"
              }
            >
              {theme === "dark" ? (
                <Sun className="h-4 w-4" aria-hidden />
              ) : (
                <Moon className="h-4 w-4" aria-hidden />
              )}
            </button>
            <button
              type="button"
              className="btn-secondary !min-h-[44px] !min-w-[44px] !rounded-full !px-0 lg:hidden"
              aria-label={mobileOpen ? "Close menu" : "Open menu"}
              onClick={() => setMobileOpen((v) => !v)}
            >
              {mobileOpen ? (
                <X className="h-4 w-4" aria-hidden />
              ) : (
                <Menu className="h-4 w-4" aria-hidden />
              )}
            </button>
          </div>
        </div>
        {mobileOpen && (
          <nav
            className="flex max-h-[calc(100dvh-var(--nav-height-regular))] flex-col gap-1 overflow-y-auto border-t border-border bg-card px-[var(--space-16)] py-[var(--space-16)] lg:hidden"
            aria-label="Global mobile"
          >
            {navLinks}
          </nav>
        )}
        <div className="border-t border-border bg-card px-4 py-2 text-center text-footnote text-muted-foreground">
          Official-source discovery for MSTC, GeM Forward, and eAuction.gov.in.
          Always bid on the source portal.
        </div>
      </header>
      <div id="main-content">{children}</div>
    </>
  );
}
