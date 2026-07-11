"use client";

import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import { Chip } from "@/components/ui/primitives";
import { SiteDisclaimer } from "@/components/site-disclaimer";
import { trackEvent, trackPageView } from "@/lib/analytics";
import { loadAuctionsExport } from "@/lib/load-auctions";
import { loadImportHistory } from "@/lib/load-import-history";
import { formatDateTime, resolvePublicUrl } from "@/lib/utils";
import type { AuctionsExport, DailyImportSummaryRow } from "@/types/auction";

const SOURCE_LABELS: Record<string, string> = {
  mstc: "MSTC",
  gem_forward: "GeM Forward",
  eauction: "eAuction",
};

function totalLots(exportData: AuctionsExport): number {
  const fromStats = exportData.stats?.total_lots_in_export;
  if (typeof fromStats === "number") return fromStats;
  return exportData.auctions.reduce((sum, a) => sum + (a.lots?.length ?? 0), 0);
}

function StatusTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: (string | number | null | undefined)[][];
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-border bg-muted text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border last:border-0">
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2 text-muted-foreground">
                  {cell ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function StatusPageApp() {
  const [exportData, setExportData] = useState<AuctionsExport | null>(null);
  const [history, setHistory] = useState<DailyImportSummaryRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    trackPageView("/auctions/status/");
    trackEvent("status_page_view");
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([loadAuctionsExport(), loadImportHistory()])
      .then(([data, hist]) => {
        if (!cancelled) {
          setExportData(data);
          setHistory(hist.length ? hist : (data.daily_import_summary ?? []));
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load status data",
          );
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
          <p className="text-headline text-foreground">Could not load status</p>
          <p className="mt-2 text-body text-muted-foreground">{error}</p>
        </main>
      </AppShell>
    );
  }

  if (!exportData) {
    return (
      <AppShell>
        <main className="container-marketplace py-section text-center text-muted-foreground">
          Loading import status…
        </main>
      </AppShell>
    );
  }

  const lots = totalLots(exportData);
  const sources = exportData.sources ?? {};
  const importTracking = (exportData.stats?.import_tracking ?? {}) as Record<
    string,
    number
  >;
  const documentsStats = (exportData.stats?.documents ?? {}) as Record<
    string,
    unknown
  >;
  const failedByReason = (documentsStats.failed_by_reason ?? {}) as Record<
    string,
    number
  >;
  const failedByType = (documentsStats.failed_by_doc_type ?? {}) as Record<
    string,
    number
  >;
  const documentsFailed =
    typeof documentsStats.failed === "number" ? documentsStats.failed : 0;
  const aiEnrichment = (exportData.stats?.ai_enrichment ?? {}) as Record<
    string,
    number
  >;
  const aiReadyCount = aiEnrichment.ready ?? 0;
  const dailyRows = [...history].sort((a, b) =>
    (b.automation_ran_at || "").localeCompare(a.automation_ran_at || ""),
  );
  const latestDaily = dailyRows[0];
  const docFailureRows = [
    ...Object.entries(failedByReason).map(([reason, count]) => [
      reason,
      count,
      "—",
    ]),
    ...Object.entries(failedByType).map(([type, count]) => ["—", count, type]),
  ];

  const automationMs = exportData.automation_ran_at
    ? Date.parse(exportData.automation_ran_at)
    : NaN;
  const staleHours = !Number.isNaN(automationMs)
    ? (Date.now() - automationMs) / (1000 * 60 * 60)
    : null;
  const isStale = staleHours != null && staleHours > 36;

  const sourceRows = Object.entries(sources).map(([key, meta]) => [
    SOURCE_LABELS[key] ?? key,
    meta.count ?? 0,
    meta.lots ?? 0,
    meta.documents_downloaded != null ? String(meta.documents_downloaded) : "—",
    meta.status ?? "—",
    exportData.automation_ran_at
      ? formatDateTime(exportData.automation_ran_at)
      : "—",
  ]);

  const historyRows = dailyRows.map((row) => [
    row.date,
    row.mstc_auctions,
    row.gem_forward_auctions,
    row.eauction_auctions,
    row.total_auctions,
    row.new_auctions_first_seen,
    row.removed_auctions,
    row.total_lots,
    row.status,
  ]);

  return (
    <AppShell>
      <main className="container-marketplace space-y-6 py-section">
      <header className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-display text-foreground">
              Import &amp; run status
            </h1>
            <p className="mt-1 text-body text-muted-foreground">
              Automation history, source counts, and daily import summary.
            </p>
          </div>
          {exportData.automation_ran_at && (
            <Chip className="border-border bg-muted text-muted-foreground normal-case tracking-normal">
              <Clock className="mr-1 inline h-3 w-3" />
              Automation ran: {formatDateTime(exportData.automation_ran_at)}
            </Chip>
          )}
        </div>
      </header>

      {isStale && (
        <section className="rounded-xl border border-border bg-muted p-4 text-body-sm text-foreground">
          <p className="font-semibold">Data freshness warning</p>
          <p className="mt-1">
            Automation last ran {staleHours!.toFixed(0)} hours ago (threshold
            36h). Verify the refresh pipeline or check production deployment.
          </p>
        </section>
      )}

      {latestDaily && (
        <section className="space-y-2">
          <h2 className="text-headline text-foreground">
            Latest run / deploy
          </h2>
          <StatusTable
            headers={[
              "Date",
              "Status",
              "Total",
              "New",
              "Removed",
              "Lots",
              "Automation ran",
            ]}
            rows={[
              [
                latestDaily.date,
                latestDaily.status,
                latestDaily.total_auctions,
                latestDaily.new_auctions_first_seen,
                latestDaily.removed_auctions,
                latestDaily.total_lots,
                latestDaily.automation_ran_at
                  ? formatDateTime(latestDaily.automation_ran_at)
                  : "—",
              ],
            ]}
          />
          {importTracking.new_auctions != null && (
            <p className="text-sm text-muted-foreground">
              Import tracking: {importTracking.new_auctions} new,{" "}
              {importTracking.removed_auctions ?? 0} removed in last tracked
              run.
            </p>
          )}
        </section>
      )}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="surface-elevated p-[var(--space-16)]">
          <p className="text-footnote font-medium uppercase tracking-wide text-muted-foreground">
            Total auctions
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-foreground">
            {exportData.count}
          </p>
        </div>
        <div className="surface-elevated p-[var(--space-16)]">
          <p className="text-footnote font-medium uppercase tracking-wide text-muted-foreground">
            Total lots
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-foreground">
            {lots}
          </p>
        </div>
        <div className="surface-elevated p-[var(--space-16)]">
          <p className="text-footnote font-medium uppercase tracking-wide text-muted-foreground">
            Export generated
          </p>
          <p className="mt-1 text-body-sm font-semibold tabular-nums text-foreground">
            {formatDateTime(
              exportData.export_generated_at ?? exportData.generated_at,
            )}
          </p>
        </div>
        <div className="surface-elevated p-[var(--space-16)]">
          <p className="text-footnote font-medium uppercase tracking-wide text-muted-foreground">
            Run ID
          </p>
          <p className="mt-1 truncate text-body-sm tabular-nums text-muted-foreground">
            {exportData.run_id ?? "—"}
          </p>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-headline text-foreground">
          Sources (current export)
        </h2>
        <StatusTable
          headers={[
            "Source",
            "Auctions",
            "Lots",
            "Documents",
            "Status",
            "Last run",
          ]}
          rows={sourceRows}
        />
      </section>

      <section className="space-y-2">
        <h2 className="text-headline text-foreground">AI enrichment</h2>
        <p className="text-body-sm text-muted-foreground">
          Buyer-facing AI headings and summaries are optional. Parser fields
          remain the source of truth.
        </p>
        <StatusTable
          headers={["Status", "Count"]}
          rows={[
            ["Ready (in export)", aiReadyCount],
            ["Missing cache", aiEnrichment.missing ?? "—"],
            ["Rejected", aiEnrichment.rejected ?? "—"],
            ["Failed", aiEnrichment.failed ?? "—"],
          ]}
        />
      </section>

      <section className="space-y-2">
        <h2 className="text-headline text-foreground">
          Daily import summary
        </h2>
        <StatusTable
          headers={[
            "Date",
            "MSTC",
            "GeM",
            "eAuction",
            "Total",
            "New",
            "Removed",
            "Lots",
            "Status",
          ]}
          rows={historyRows}
        />
      </section>

      {docFailureRows.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-headline text-foreground">
            Document / PDF failures
          </h2>
          <StatusTable
            headers={["Reason", "Count", "Doc type"]}
            rows={docFailureRows}
          />
        </section>
      )}

      <section className="space-y-2 rounded-xl border border-border bg-muted p-4 text-body-sm text-foreground">
        <h2 className="font-semibold">Operations</h2>
        <p>
          <a href={resolvePublicUrl("launch-readiness/")} className="link-action">
            Launch readiness dashboard
          </a>{" "}
          (noindex) — machine-checkable gates for staged launch. Linked here for ops only, not
          buyer marketing.
        </p>
      </section>

      <section className="space-y-2 rounded-xl border border-border bg-muted p-4 text-body-sm text-foreground">
        <h2 className="font-semibold">Notes</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            eAuction listings reflect the public ByDate visible window only —
            counts may be lower than the full catalogue.
          </li>
          {documentsFailed ? (
            <li>
              Document downloads failed in last run: {documentsFailed} (see
              batch stats).
            </li>
          ) : null}
          {importTracking.new_auctions != null ? (
            <li>
              Last tracked run: {importTracking.new_auctions} new auction(s),{" "}
              {importTracking.removed_auctions ?? 0} removed from export.
            </li>
          ) : null}
          <li>
            <code className="rounded bg-card px-1">listed_at</code> is source
            publish date when available;{" "}
            <code className="rounded bg-card px-1">imported_at</code> is when we
            first saw the auction in our dataset.
          </li>
        </ul>
      </section>

      <SiteDisclaimer />
      </main>
      <SiteFooter automationRanAt={exportData.automation_ran_at ?? undefined} />
    </AppShell>
  );
}
