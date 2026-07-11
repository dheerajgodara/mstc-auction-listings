"use client";

import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";

export function LegalPageApp({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <AppShell>
      <main className="container-marketplace space-y-6 py-section">
        <h1 className="text-display text-foreground">{title}</h1>
        <section className="surface-elevated space-y-4 p-6 text-body-sm text-muted-foreground">
          {children}
        </section>
        <SiteFooter />
      </main>
    </AppShell>
  );
}
