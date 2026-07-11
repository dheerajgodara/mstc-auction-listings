"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleDashed, ShieldAlert } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { Chip } from "@/components/ui/primitives";
import { SiteDisclaimer } from "@/components/site-disclaimer";
import { trackLaunchReadinessPageView, trackPageView } from "@/lib/analytics";
import {
  GATE_STATUS_ICON_STYLES,
  GATE_STATUS_LABELS,
  GATE_STATUS_STYLES,
  LAUNCH_STAGES,
  countGatesByStatus,
  groupSummary,
  loadLaunchReadinessReport,
  stageRecommendationNote,
  type GateStatus,
  type LaunchGateGroup,
  type LaunchReadinessReport,
} from "@/lib/launch-readiness";
import { formatDateTime } from "@/lib/utils";

function StatusIcon({ status }: { status: GateStatus }) {
  const iconClass = `h-4 w-4 ${GATE_STATUS_ICON_STYLES[status]}`;
  if (status === "pass") return <CheckCircle2 className={iconClass} aria-hidden />;
  if (status === "manual") return <CircleDashed className={iconClass} aria-hidden />;
  if (status === "warn") return <AlertTriangle className={iconClass} aria-hidden />;
  return <ShieldAlert className={iconClass} aria-hidden />;
}

function GateGroupCard({ group }: { group: LaunchGateGroup }) {
  const summary = groupSummary(group);
  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-headline text-foreground">{group.title}</h2>
        <Chip className={GATE_STATUS_STYLES[summary]}>{GATE_STATUS_LABELS[summary]}</Chip>
      </div>
      <ul className="space-y-2">
        {group.gates.map((g) => (
          <li
            key={g.id}
            className="flex items-start gap-2 rounded-lg border border-border/60 px-3 py-2 text-sm"
          >
            <StatusIcon status={g.status} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-foreground">{g.title}</span>
                <Chip className={GATE_STATUS_STYLES[g.status]}>{GATE_STATUS_LABELS[g.status]}</Chip>
                {g.manual ? (
                  <span className="text-footnote text-muted-foreground">Manual</span>
                ) : null}
                {g.blocker ? (
                  <span className="text-footnote font-medium text-foreground">Blocker</span>
                ) : null}
              </div>
              {g.detail ? (
                <p className="mt-1 text-footnote text-muted-foreground">{g.detail}</p>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function LaunchReadinessPageApp() {
  const [report, setReport] = useState<LaunchReadinessReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    trackPageView("/auctions/launch-readiness/");
    trackLaunchReadinessPageView();
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadLaunchReadinessReport()
      .then((data) => {
        if (!cancelled) setReport(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load launch report");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <AppShell>
        <main className="container-marketplace py-section text-center">
          <p className="text-headline text-foreground">Launch readiness unavailable</p>
          <p className="mt-2 text-body text-muted-foreground">{error}</p>
          <p className="mt-4 text-footnote text-muted-foreground">
            Run <code className="rounded bg-muted px-1">pnpm run build:prod</code> to generate the
            report.
          </p>
        </main>
      </AppShell>
    );
  }

  if (!report) {
    return (
      <AppShell>
        <main className="container-marketplace py-section">
          <p className="text-body text-muted-foreground">Loading launch readiness…</p>
        </main>
      </AppShell>
    );
  }

  const passCount = countGatesByStatus(report, "pass");
  const warnCount = countGatesByStatus(report, "warn");
  const failCount = countGatesByStatus(report, "fail") + countGatesByStatus(report, "blocked");
  const manualCount = countGatesByStatus(report, "manual");
  const stageLabel =
    LAUNCH_STAGES.find((s) => s.id === report.current_stage_recommendation)?.label ??
    report.current_stage_recommendation;

  return (
    <AppShell>
      <main className="container-marketplace py-section">
        <header className="mb-8 max-w-3xl">
          <p className="text-footnote font-medium uppercase tracking-wide text-muted-foreground">
            Internal · Noindex
          </p>
          <h1 className="mt-2 text-title-1 text-foreground">Launch readiness</h1>
          <p className="mt-3 text-body text-muted-foreground">
            Machine-checkable gates for staged launch. Score is informational only — public launch
            and live billing require explicit owner approval.
          </p>
          {stageRecommendationNote(report.current_stage_recommendation) ? (
            <p className="mt-3 rounded-xl border border-border bg-muted p-4 text-body-sm text-foreground">
              {stageRecommendationNote(report.current_stage_recommendation)}
            </p>
          ) : null}
        </header>

        <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-footnote text-muted-foreground">Readiness score</p>
            <p className="mt-1 text-title-2 text-foreground">{report.readiness_score}%</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-footnote text-muted-foreground">Recommended stage</p>
            <p className="mt-1 text-title-3 text-foreground">{stageLabel}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-footnote text-muted-foreground">Launch approved</p>
            <p className="mt-1 text-title-3 text-foreground">No</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-footnote text-muted-foreground">Report generated</p>
            <p className="mt-1 text-sm text-foreground">{formatDateTime(report.generated_at)}</p>
          </div>
        </div>

        <div className="mb-8 grid gap-4 lg:grid-cols-2">
          <section className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-headline text-foreground">Data freshness</h2>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Automation ran</dt>
                <dd className="text-foreground">
                  {report.freshness.automation_ran_at
                    ? formatDateTime(report.freshness.automation_ran_at)
                    : "—"}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Age (hours)</dt>
                <dd className="text-foreground">{report.freshness.age_hours ?? "—"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Threshold</dt>
                <dd className="text-foreground">{report.freshness.threshold_hours}h</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Within threshold</dt>
                <dd className="text-foreground">
                  {report.freshness.within_threshold == null
                    ? "Unknown"
                    : report.freshness.within_threshold
                      ? "Yes"
                      : "No"}
                </dd>
              </div>
            </dl>
          </section>

          <section className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-headline text-foreground">Source counts</h2>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Total auctions</dt>
                <dd className="text-foreground">{report.total_auctions}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">MSTC</dt>
                <dd className="text-foreground">{report.source_counts.mstc}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">GeM Forward</dt>
                <dd className="text-foreground">{report.source_counts.gem_forward}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">eAuction</dt>
                <dd className="text-foreground">{report.source_counts.eauction}</dd>
              </div>
            </dl>
          </section>
        </div>

        <div className="mb-8 flex flex-wrap gap-2">
          <Chip className={GATE_STATUS_STYLES.pass}>{passCount} pass</Chip>
          <Chip className={GATE_STATUS_STYLES.warn}>{warnCount} warn</Chip>
          <Chip className={GATE_STATUS_STYLES.fail}>{failCount} fail</Chip>
          <Chip className={GATE_STATUS_STYLES.manual}>{manualCount} manual</Chip>
        </div>

        {report.hard_blockers.length > 0 ? (
          <section className="mb-8 rounded-xl border border-border bg-muted p-4">
            <h2 className="text-headline text-foreground">Hard blockers</h2>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {report.hard_blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {report.manual_gates.length > 0 ? (
          <section className="mb-8 rounded-xl border border-border bg-muted p-4">
            <h2 className="text-headline text-foreground">Manual gates</h2>
            <p className="mt-2 text-footnote text-muted-foreground">
              Required before paid beta or public launch. They do not block soft launch with known
              buyers when automated hard blockers are clear.
            </p>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {report.manual_gates.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className="mb-8 rounded-xl border border-border bg-card p-4">
          <h2 className="text-headline text-foreground">Next steps</h2>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
            {report.next_steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </section>

        <section className="mb-8">
          <h2 className="mb-4 text-headline text-foreground">Launch stages</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {LAUNCH_STAGES.map((stage) => (
              <div
                key={stage.id}
                className={`rounded-xl border p-4 ${
                  stage.id === report.current_stage_recommendation
                    ? "border-primary bg-primary/5"
                    : "border-border bg-card"
                }`}
              >
                <p className="font-medium text-foreground">{stage.label}</p>
                <p className="mt-1 text-footnote text-muted-foreground">{stage.description}</p>
              </div>
            ))}
          </div>
        </section>

        <div className="space-y-6">
          {report.groups.map((group) => (
            <GateGroupCard key={group.id} group={group} />
          ))}
        </div>

        <div className="mt-10">
          <SiteDisclaimer />
        </div>
      </main>
      <SiteFooter automationRanAt={report.freshness.automation_ran_at} />
    </AppShell>
  );
}
