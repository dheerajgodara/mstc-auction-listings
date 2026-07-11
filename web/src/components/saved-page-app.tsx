"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { SiteFooter } from "@/components/site-footer";
import {
  deleteSavedSearch,
  loadSavedSearches,
  type SavedSearch,
} from "@/lib/saved-searches";
import { buildUrlState } from "@/lib/url-state";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";
export function SavedPageApp() {
  const [saved, setSaved] = useState<SavedSearch[]>([]);
  useEffect(() => {
    setSaved(loadSavedSearches());
  }, []);
  const openSearch = (s: SavedSearch) => {
    const qs = buildUrlState({
      query: s.query,
      sourceFilter: s.sourceFilter,
      assetCategory: s.assetCategory,
      stateFilter: s.stateFilter,
      regionFilter: s.regionFilter,
      sortBy: s.sortBy,
      watchlistOnly: s.watchlistOnly,
    });
    window.location.href = `${resolvePublicUrl("")}${qs}`;
  };
  return (
    <AppShell>
      {" "}
      <main className="container-marketplace space-y-4 py-section">
        {" "}
        <h1 className="text-display text-foreground">Saved searches</h1>{" "}
        <p className="text-body-sm">Stored locally on this browser.</p>{" "}
        {saved.length === 0 ? (
          <div className="surface-elevated p-8 text-center">
            <p className="text-title text-foreground">No saved searches</p>
            <p className="mt-2 text-body-sm text-muted-foreground">
              Save a search from Discover to reopen it quickly.
            </p>
            <Link
              href={resolveAppPath("")}
              className="btn-primary mt-6 inline-flex text-sm"
            >
              Go to Discover
            </Link>
          </div>
        ) : (
          <ul className="space-y-2">
            {" "}
            {saved.map((s) => (
              <li
                key={s.id}
                className="surface-elevated flex flex-wrap items-center justify-between gap-2 p-4"
              >
                {" "}
                <div>
                  {" "}
                  <p className="font-medium text-foreground">{s.name}</p>{" "}
                  <p className="text-caption">
                    {" "}
                    {new Date(s.createdAt).toLocaleString("en-IN")}{" "}
                  </p>{" "}
                </div>{" "}
                <div className="flex gap-2">
                  {" "}
                  <button
                    type="button"
                    onClick={() => openSearch(s)}
                    className="btn-primary text-sm"
                  >
                    {" "}
                    Open{" "}
                  </button>{" "}
                  <button
                    type="button"
                    onClick={() => setSaved(deleteSavedSearch(s.id))}
                    className="btn-secondary text-sm text-muted-foreground"
                  >
                    {" "}
                    Delete{" "}
                  </button>{" "}
                </div>{" "}
              </li>
            ))}{" "}
          </ul>
        )}{" "}
        <SiteFooter />{" "}
      </main>{" "}
    </AppShell>
  );
}
