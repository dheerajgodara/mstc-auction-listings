"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Bell,
  Bookmark,
  CheckCircle2,
  ExternalLink,
  Search,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { SiteDisclaimer } from "@/components/site-disclaimer";
import { SiteFooter } from "@/components/site-footer";
import { trackAppInstallClick, trackAppPageView } from "@/lib/analytics";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

const APP_VALUE = [
  {
    title: "Watchlist first",
    body: "Keep buyer targets on one screen and return quickly before closing.",
    icon: Bookmark,
  },
  {
    title: "Saved-search workflow",
    body: "Reopen material, source, quantity, and location filters from mobile.",
    icon: Search,
  },
  {
    title: "Official source actions",
    body: "Open MSTC, GeM Forward, and eAuction source pages for bidding and verification.",
    icon: ExternalLink,
  },
  {
    title: "Alert-ready foundation",
    body: "The app shell is prepared for future saved-search and closing reminders.",
    icon: Bell,
  },
] as const;

const MANUAL_STEPS = [
  "Open this page in Safari or Chrome on your phone.",
  "Use Share or browser menu.",
  "Choose Add to Home Screen or Install app when available.",
  "Open Scrap Auction India from your phone home screen.",
] as const;

export function AppInstallPageApp() {
  const [installPrompt, setInstallPrompt] =
    useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    trackAppPageView();
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    };
    const onInstalled = () => {
      setInstalled(true);
      setInstallPrompt(null);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const install = async () => {
    trackAppInstallClick(installPrompt ? "browser_prompt" : "manual");
    if (!installPrompt) return;
    await installPrompt.prompt();
    await installPrompt.userChoice.catch(() => null);
    setInstallPrompt(null);
  };

  return (
    <AppShell>
      <main className="container-marketplace space-y-10 py-section">
        <section className="mx-auto grid max-w-6xl gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <p className="text-footnote font-medium uppercase tracking-wide text-muted-foreground">
              Phase 7 app foundation
            </p>
            <h1 className="mt-3 text-display text-foreground">
              Install Scrap Auction India for faster buyer follow-up
            </h1>
            <p className="mt-4 max-w-2xl text-body text-muted-foreground">
              Use the site like an app for discovery, watchlists, saved searches,
              documents, and official source links. Native app-store releases and
              push alerts remain downstream of paid website validation.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                className="btn-primary inline-flex items-center gap-2 text-sm"
                onClick={install}
              >
                <Smartphone className="h-4 w-4" aria-hidden />
                {installPrompt ? "Install app" : "Show install steps"}
              </button>
              <Link
                href={resolveAppPath("watchlist/")}
                className="btn-secondary inline-flex text-sm"
              >
                Open watchlist
              </Link>
            </div>
            {installed ? (
              <p className="mt-4 inline-flex items-center gap-2 rounded-full bg-success-soft px-3 py-1 text-footnote font-medium text-success">
                <CheckCircle2 className="h-4 w-4" aria-hidden />
                App installed on this device
              </p>
            ) : null}
          </div>
          <div className="surface-elevated p-5">
            <div className="rounded-[2rem] border border-border bg-card p-4 shadow-listing-card">
              <div className="rounded-[1.5rem] bg-muted p-4">
                <div className="mb-4 flex items-center justify-between">
                  <span className="text-footnote font-medium text-muted-foreground">
                    Scrap Auction India
                  </span>
                  <span className="rounded-full bg-card px-2 py-1 text-[11px] text-muted-foreground">
                    App mode
                  </span>
                </div>
                <div className="space-y-3">
                  <div className="rounded-2xl bg-card p-4">
                    <p className="text-title text-foreground">Watchlist</p>
                    <p className="mt-1 text-footnote text-muted-foreground">
                      Saved auctions, closing dates, source links.
                    </p>
                  </div>
                  <div className="rounded-2xl bg-card p-4">
                    <p className="text-title text-foreground">Saved searches</p>
                    <p className="mt-1 text-footnote text-muted-foreground">
                      Material, state, quantity, and source filters.
                    </p>
                  </div>
                  <div className="rounded-2xl bg-card p-4">
                    <p className="text-title text-foreground">Official portals</p>
                    <p className="mt-1 text-footnote text-muted-foreground">
                      Bid only on MSTC, GeM Forward, or eAuction.gov.in.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {APP_VALUE.map(({ title, body, icon: Icon }) => (
            <article key={title} className="surface-elevated p-5">
              <Icon className="h-5 w-5 text-action" aria-hidden />
              <h2 className="mt-4 text-headline text-foreground">{title}</h2>
              <p className="mt-2 text-body-sm text-muted-foreground">{body}</p>
            </article>
          ))}
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <div className="surface-elevated p-6">
            <h2 className="text-headline text-foreground">Install manually</h2>
            <ol className="mt-4 space-y-3 text-body-sm text-muted-foreground">
              {MANUAL_STEPS.map((step, index) => (
                <li key={step} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-footnote font-semibold text-foreground">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>

          <div className="surface-elevated p-6">
            <h2 className="text-headline text-foreground">Current limits</h2>
            <ul className="mt-4 space-y-3 text-body-sm text-muted-foreground">
              <li className="flex gap-3">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-action" />
                No in-app bidding or payment collection.
              </li>
              <li className="flex gap-3">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-action" />
                Watchlist and saved searches are stored on this device until
                accounts go live.
              </li>
              <li className="flex gap-3">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-action" />
                Push alerts are planned after website revenue proof and buyer
                feedback.
              </li>
            </ul>
          </div>
        </section>

        <section className="surface-elevated p-6">
          <SiteDisclaimer />
        </section>

        <SiteFooter />
      </main>
    </AppShell>
  );
}
