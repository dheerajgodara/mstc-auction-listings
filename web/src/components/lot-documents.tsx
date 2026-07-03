"use client";

import { useState } from "react";
import { ExternalLink, FileText } from "lucide-react";
import { Chip } from "@/components/ui/primitives";
import { resolvePublicUrl } from "@/lib/utils";
import type { LotDocument, LotRecord } from "@/types/auction";

function docOpenUrl(doc: LotDocument): string | null {
  const path = doc.cached_url || doc.source_url;
  return path ? resolvePublicUrl(path) : null;
}

function docTypeLabel(type: LotDocument["type"]): string {
  if (type === "photo") return "Photo";
  if (type === "annexure") return "Annexure";
  if (type === "document") return "Document";
  return "File";
}

function ThumbnailButton({
  src,
  href,
  label,
}: {
  src: string;
  href: string;
  label: string;
}) {
  const [broken, setBroken] = useState(false);
  if (broken) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="group relative block aspect-[4/3] w-20 shrink-0 overflow-hidden rounded-lg border border-white/70 bg-white/60 shadow-sm"
      title={label}
    >
      <img
        src={src}
        alt={label}
        loading="lazy"
        className="h-full w-full object-cover transition group-hover:scale-105"
        onError={() => setBroken(true)}
      />
    </a>
  );
}

export function LotPreviewStrip({
  lots,
  max = 3,
}: {
  lots: LotRecord[];
  max?: number;
}) {
  const items: { thumb: string; href: string; label: string }[] = [];
  for (const lot of lots) {
    for (const doc of lot.documents || []) {
      if (doc.thumbnail_url && doc.status === "thumbnail_ready") {
        const href = docOpenUrl(doc) || resolvePublicUrl(doc.thumbnail_url);
        items.push({
          thumb: resolvePublicUrl(doc.thumbnail_url),
          href,
          label: `${docTypeLabel(doc.type)} ${doc.filename}`,
        });
      }
    }
    if (items.length >= max + 3) break;
  }
  if (items.length === 0) {
    for (const lot of lots) {
      for (const thumb of lot.preview_images || []) {
        items.push({
          thumb: resolvePublicUrl(thumb),
          href: resolvePublicUrl(thumb),
          label: lot.item_title,
        });
      }
      if (items.length >= max + 3) break;
    }
  }
  if (items.length === 0) return null;

  const visible = items.slice(0, max);
  const extra = items.length - visible.length;

  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-2">
        {visible.map((item) => (
          <ThumbnailButton
            key={`${item.thumb}-${item.label}`}
            src={item.thumb}
            href={item.href}
            label={item.label}
          />
        ))}
      </div>
      {extra > 0 && (
        <span className="text-xs font-medium text-slate-500">+{extra}</span>
      )}
    </div>
  );
}

export function LotDocumentsPanel({ lot }: { lot: LotRecord }) {
  const docs = lot.documents || [];
  if (docs.length === 0) return null;

  const thumbs = docs.filter(
    (d) => d.thumbnail_url && d.status === "thumbnail_ready",
  );
  const chips = docs.filter(
    (d) => !d.thumbnail_url || d.status !== "thumbnail_ready",
  );

  return (
    <div className="mt-3 border-t border-white/50 pt-3">
      <h5 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
        Photos &amp; Documents
      </h5>
      {thumbs.length > 0 && (
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {thumbs.map((doc) => {
            const href = docOpenUrl(doc) || resolvePublicUrl(doc.thumbnail_url!);
            return (
              <ThumbnailCard key={doc.filename} doc={doc} href={href} />
            );
          })}
        </div>
      )}
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {chips.map((doc) => {
            const href = docOpenUrl(doc);
            return (
              <div
                key={doc.filename}
                className="flex min-w-0 flex-col gap-1 rounded-lg border border-white/60 bg-white/55 p-2"
              >
                <Chip className="w-fit border-slate-200/80 bg-white/70 text-slate-700 normal-case tracking-normal">
                  {docTypeLabel(doc.type)}
                </Chip>
                <span className="break-all text-xs text-slate-700">{doc.filename}</span>
                {doc.status === "failed" || doc.status === "thumbnail_failed" ? (
                  <span className="text-[11px] text-amber-800">
                    {doc.error || doc.status}
                  </span>
                ) : null}
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-glass inline-flex w-fit items-center gap-1 px-2 py-1 text-xs"
                  >
                    <ExternalLink className="h-3 w-3" />
                    Open original
                  </a>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                    <FileText className="h-3 w-3" />
                    Not cached
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ThumbnailCard({ doc, href }: { doc: LotDocument; href: string }) {
  const [broken, setBroken] = useState(false);
  const thumb = resolvePublicUrl(doc.thumbnail_url!);
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="block overflow-hidden rounded-lg border border-white/70 bg-white/60"
    >
      {!broken ? (
        <img
          src={thumb}
          alt={doc.filename}
          loading="lazy"
          className="aspect-[4/3] w-full object-cover"
          onError={() => setBroken(true)}
        />
      ) : (
        <div className="flex aspect-[4/3] items-center justify-center bg-slate-100 text-xs text-slate-500">
          Preview unavailable
        </div>
      )}
      <div className="border-t border-white/60 px-2 py-1 text-[11px] text-slate-700">
        <span className="font-medium">{docTypeLabel(doc.type)}</span>
        <span className="block truncate">{doc.filename}</span>
      </div>
    </a>
  );
}
