"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, Clock } from "lucide-react";
import { Chip } from "@/components/ui/primitives";
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
    <div className="overflow-x-auto rounded-xl border border-slate-200/80 bg-white/80">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50/90 text-xs uppercase tracking-wide text-slate-500">
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
            <tr key={i} className="border-b border-slate-100 last:border-0">
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2 text-slate-700">
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
    let cancelled = false;
    Promise.all([loadAuctionsExport(), loadImportHistory()])
      .then(([data, hist]) => {
        if (!cancelled) {
          setExportData(data);
          setHistory(hist.length ? hist : data.daily_import_summary ?? []);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load status data");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const homeHref = resolvePublicUrl("");

  if (error) {
    return (
      <div className="mx-auto max-w-3xl p-8 text-center">
        <p className="text-lg font-semibold text-rose-800">Could not load status</p>
        <p className="mt-2 text-sm text-slate-600">{error}</p>
      </div>
    );
  }

  if (!exportData) {
    return (
      <div className="mx-auto max-w-3xl p-12 text-center text-slate-600">
        Loading import status…
      </div>
    );
  }

  const lots = totalLots(exportData);
  const sources = exportData.sources ?? {};
  const importTracking = (exportData.stats?.import_tracking ?? {}) as Record<string, number>;
  const documents = (exportData.stats?.documents ?? {}) as Record<string, number>;
  const dailyRows = [...history].sort(
    (a, b) => (b.automation_ran_at || "").localeCompare(a.automation_ran_at || ""),
  );

  const sourceRows = Object.entries(sources).map(([key, meta]) => [
    SOURCE_LABELS[key] ?? key,
    meta.count ?? 0,
    meta.lots ?? 0,
    meta.documents_downloaded != null ? String(meta.documents_downloaded) : "—",
    meta.status ?? "—",
    exportData.automation_ran_at ? formatDateTime(exportData.automation_ran_at) : "—",
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
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6">
      <header className="space-y-3">
        <a
          href={homeHref}
          className="inline-flex items-center gap-1 text-sm font-medium text-cyan-800 hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to listings
        </a>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">Import &amp; run status</h1>
            <p className="mt-1 text-sm text-slate-600">
              Automation history, source counts, and daily import summary.
            </p>
          </div>
          {exportData.automation_ran_at && (
            <Chip className="border-violet-200/80 bg-violet-50/90 text-violet-900 normal-case tracking-normal">
              <Clock className="mr-1 inline h-3 w-3" />
              Automation ran: {formatDateTime(exportData.automation_ran_at)}
            </Chip>
          )}
        </div>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-200/80 bg-white/80 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Total auctions</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">{exportData.count}</p>
        </div>
        <div className="rounded-xl border border-slate-200/80 bg-white/80 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Total lots</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">{lots}</p>
        </div>
        <div className="rounded-xl border border-slate-200/80 bg-white/80 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Export generated</p>
          <p className="mt-1 text-sm font-semibold text-slate-800">
            {formatDateTime(exportData.export_generated_at ?? exportData.generated_at)}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200/80 bg-white/80 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Run ID</p>
          <p className="mt-1 truncate text-sm font-mono text-slate-700">{exportData.run_id ?? "—"}</p>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">Sources (current export)</h2>
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
        <h2 className="text-lg font-semibold text-slate-900">Daily import summary</h2>
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

      <section className="space-y-2 rounded-xl border border-amber-200/70 bg-amber-50/50 p-4 text-sm text-amber-950">
        <h2 className="font-semibold">Notes</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            eAuction listings reflect the public ByDate visible window only — counts may be lower
            than the full catalogue.
          </li>
          {documents.failed ? (
            <li>Document downloads failed in last run: {documents.failed} (see batch stats).</li>
          ) : null}
          {importTracking.new_auctions != null ? (
            <li>
              Last tracked run: {importTracking.new_auctions} new auction(s),{" "}
              {importTracking.removed_auctions ?? 0} removed from export.
            </li>
          ) : null}
          <li>
            <code className="rounded bg-white/70 px-1">listed_at</code> is source publish date when
            available; <code className="rounded bg-white/70 px-1">imported_at</code> is when we
            first saw the auction in our dataset.
          </li>
        </ul>
      </section>
    </div>
  );
}
