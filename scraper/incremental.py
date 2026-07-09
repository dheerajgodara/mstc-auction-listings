from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

IST = ZoneInfo("Asia/Kolkata")

DecisionStatus = Literal["new", "unchanged", "changed", "removed", "needs_repair"]


class ListingSnapshot(BaseModel):
    stable_key: str
    source: str
    source_auction_id: str
    listing_hash: str
    scope: str = "enriched"
    fields: dict[str, Any] = Field(default_factory=dict)


class ChangeDecision(BaseModel):
    stable_key: str
    source: str
    source_auction_id: Optional[str] = None
    status: DecisionStatus
    previous_hash: Optional[str] = None
    current_hash: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)


class IncrementalReport(BaseModel):
    generated_at: str
    counts: dict[str, int]
    decisions: list[ChangeDecision]
    snapshots: list[ListingSnapshot]


def load_export(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_report(path: Path, report: IncrementalReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def write_export(path: Path, export: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(export, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def stable_listing_key(record: dict[str, Any]) -> str:
    source = _clean_source(record.get("source") or "mstc")
    raw_id = record.get("source_auction_id") or record.get("id") or record.get("auction_number") or ""
    sid = str(raw_id).strip()
    prefix = f"{source}:"
    if sid.lower().startswith(prefix):
        sid = sid[len(prefix) :]
    return f"{source}:{sid}"


def build_snapshot_index(export: dict[str, Any] | None, *, scope: str = "enriched") -> dict[str, ListingSnapshot]:
    if not export:
        return {}
    return {
        snapshot.stable_key: snapshot
        for snapshot in (build_listing_snapshot(a, scope=scope) for a in export.get("auctions", []))
    }


def build_record_index(export: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not export:
        return {}
    return {stable_listing_key(a): a for a in export.get("auctions", [])}


def compare_exports(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    scope: str = "enriched",
) -> IncrementalReport:
    current_snapshots = [build_listing_snapshot(a, scope=scope) for a in current.get("auctions", [])]
    previous_snapshots = build_snapshot_index(previous, scope=scope)
    previous_records = build_record_index(previous)
    current_keys = {s.stable_key for s in current_snapshots}

    decisions: list[ChangeDecision] = []
    for snapshot in current_snapshots:
        previous_snapshot = previous_snapshots.get(snapshot.stable_key)
        previous_record = previous_records.get(snapshot.stable_key)
        repair_reasons = repair_reasons_for(previous_record)

        if previous_snapshot is None:
            status: DecisionStatus = "new"
            reasons = ["not_seen_before"]
        elif repair_reasons:
            status = "needs_repair"
            reasons = repair_reasons
        elif previous_snapshot.listing_hash != snapshot.listing_hash:
            status = "changed"
            reasons = _changed_fields(previous_snapshot.fields, snapshot.fields)
        else:
            status = "unchanged"
            reasons = []

        decisions.append(
            ChangeDecision(
                stable_key=snapshot.stable_key,
                source=snapshot.source,
                source_auction_id=snapshot.source_auction_id,
                status=status,
                previous_hash=previous_snapshot.listing_hash if previous_snapshot else None,
                current_hash=snapshot.listing_hash,
                reasons=reasons,
            )
        )

    for key, previous_snapshot in previous_snapshots.items():
        if key not in current_keys:
            decisions.append(
                ChangeDecision(
                    stable_key=key,
                    source=previous_snapshot.source,
                    source_auction_id=previous_snapshot.source_auction_id,
                    status="removed",
                    previous_hash=previous_snapshot.listing_hash,
                    current_hash=None,
                    reasons=["not_in_current_discovery"],
                )
            )

    counts: dict[str, int] = {status: 0 for status in ("new", "unchanged", "changed", "removed", "needs_repair")}
    for decision in decisions:
        counts[decision.status] = counts.get(decision.status, 0) + 1
    counts["total_current"] = len(current_snapshots)
    counts["total_previous"] = len(previous_snapshots)
    counts["total_decisions"] = len(decisions)

    return IncrementalReport(
        generated_at=datetime.now(IST).isoformat(),
        counts=counts,
        decisions=decisions,
        snapshots=current_snapshots,
    )


def merge_reusing_unchanged_records(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> tuple[dict[str, Any], IncrementalReport]:
    """Return current export with healthy unchanged records replaced by previous enriched records.

    This is the safe Phase B bridge: the candidate export remains authoritative for membership,
    ordering, and changed/new/repair records. Only records classified as `unchanged` are reused
    from the previous export, preserving expensive parsed documents, thumbnails, AI fields, and
    other enrichment that does not need to be regenerated.
    """
    report = compare_exports(current, previous)
    if not previous:
        merged = copy.deepcopy(current)
        _attach_incremental_stats(merged, report, reused_count=0)
        return merged, report

    previous_records = build_record_index(previous)
    decisions_by_key = {decision.stable_key: decision for decision in report.decisions}

    merged_auctions: list[dict[str, Any]] = []
    reused_count = 0
    for auction in current.get("auctions", []):
        key = stable_listing_key(auction)
        decision = decisions_by_key.get(key)
        previous_record = previous_records.get(key)
        if decision and decision.status == "unchanged" and previous_record:
            reused_count += 1
            merged_auctions.append(copy.deepcopy(previous_record))
        else:
            merged_auctions.append(copy.deepcopy(auction))

    merged = copy.deepcopy(current)
    merged["auctions"] = merged_auctions
    merged["count"] = len(merged_auctions)
    _attach_incremental_stats(merged, report, reused_count=reused_count)
    return merged, report


def _attach_incremental_stats(export: dict[str, Any], report: IncrementalReport, *, reused_count: int) -> None:
    stats = dict(export.get("stats") or {})
    stats["incremental"] = {
        "phase": "B",
        "enabled": True,
        "reused_unchanged_records": reused_count,
        "current_candidate_records": int(report.counts.get("total_current", 0)),
        "previous_records": int(report.counts.get("total_previous", 0)),
        "new_records": int(report.counts.get("new", 0)),
        "changed_records": int(report.counts.get("changed", 0)),
        "needs_repair_records": int(report.counts.get("needs_repair", 0)),
        "removed_records": int(report.counts.get("removed", 0)),
        "unchanged_records": int(report.counts.get("unchanged", 0)),
        "decision_report_generated_at": report.generated_at,
    }
    export["stats"] = stats


def build_listing_snapshot(record: dict[str, Any], *, scope: str = "enriched") -> ListingSnapshot:
    source = _clean_source(record.get("source") or "mstc")
    source_auction_id = _source_auction_id(record, source)
    fields = listing_fingerprint_fields(record, source=source, source_auction_id=source_auction_id, scope=scope)
    listing_hash = sha256_json(fields)
    return ListingSnapshot(
        stable_key=f"{source}:{source_auction_id}",
        source=source,
        source_auction_id=source_auction_id,
        listing_hash=listing_hash,
        scope=scope,
        fields=fields,
    )


def listing_fingerprint_fields(
    record: dict[str, Any],
    *,
    source: str,
    source_auction_id: str,
    scope: str = "enriched",
) -> dict[str, Any]:
    lots = record.get("lots") or []
    fields = {
        "source": source,
        "source_auction_id": source_auction_id,
        "auction_number": _norm_auction_number(record.get("auction_number"), source_auction_id),
        "opening": _norm_dt(record.get("opening")),
        "closing": _norm_dt(record.get("closing")),
        "listed_at": _norm_dt(record.get("listed_at")),
        "detail_url": _norm_url(record.get("detail_url") or record.get("mstc_html_url")),
    }
    if scope == "enriched":
        fields.update(
            {
                "item_summary": _norm(record.get("item_summary") or record.get("display_title")),
                "seller": _norm(record.get("seller")),
                "location": _norm(record.get("location")),
                "state": _norm(record.get("state")),
                "pdf_url": _norm_url(record.get("pdf_url") or record.get("source_pdf_url")),
                "document_urls": sorted(_norm_url(u) for u in (record.get("document_urls") or []) if u),
                "lot_count": _lot_count(record, lots),
                "lot_signature": _lot_signature(lots),
                "min_start_price": _norm_number(record.get("min_start_price")),
                "max_start_price": _norm_number(record.get("max_start_price")),
                "price_parse_status": _norm(record.get("price_parse_status")),
                "emd_parse_status": _norm(record.get("emd_parse_status")),
            }
        )
    elif scope != "listing":
        raise ValueError(f"Unknown snapshot scope: {scope}")
    elif source != "mstc":
        fields.update(
            {
                "item_summary": _norm(record.get("item_summary") or record.get("display_title")),
                "seller": _norm(record.get("seller")),
                "location": _norm(record.get("location")),
                "state": _norm(record.get("state")),
                "document_urls": sorted(_norm_url(u) for u in (record.get("document_urls") or []) if u),
            }
        )
    else:
        fields["lot_types"] = sorted(_norm(v) for v in (record.get("lot_types") or []) if v)
    return fields


def repair_reasons_for(record: dict[str, Any] | None) -> list[str]:
    if not record:
        return []

    reasons: list[str] = []
    lots = record.get("lots") or []
    status = str(record.get("status") or "").lower()
    confidence = str(record.get("parse_confidence") or "").lower()
    missing_fields = set(record.get("missing_fields") or [])

    if status in {"failed", "partial", "listing_only"}:
        reasons.append(f"status_{status}")
    if confidence in {"low", "minimal"}:
        reasons.append(f"parse_confidence_{confidence}")
    if not lots:
        reasons.append("missing_lots")
    if record.get("errors"):
        reasons.append("has_errors")
    if "lots" in missing_fields:
        reasons.append("missing_field_lots")
    if "start_price" in missing_fields and record.get("price_parse_status") == "missing":
        reasons.append("missing_price")

    return sorted(set(reasons))


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _changed_fields(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    changed = [key for key in sorted(set(previous) | set(current)) if previous.get(key) != current.get(key)]
    return [f"changed_{key}" for key in changed] or ["listing_hash_changed"]


def _source_auction_id(record: dict[str, Any], source: str) -> str:
    raw = record.get("source_auction_id") or record.get("id") or record.get("auction_number") or ""
    sid = str(raw).strip()
    prefix = f"{source}:"
    if sid.lower().startswith(prefix):
        sid = sid[len(prefix) :]
    return sid


def _clean_source(value: Any) -> str:
    return str(value or "mstc").strip().lower()


def _norm(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text.lower() or None


def _norm_auction_number(value: Any, source_auction_id: str) -> str | None:
    text = _norm(value)
    if not text:
        return None
    sid = re.escape(str(source_auction_id).strip().lower())
    if sid:
        text = re.sub(rf"\[{sid}\]\s*$", "", text).strip()
    return text or None


def _norm_url(value: Any) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", "", str(value)).strip() or None


def _norm_dt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return _norm(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST).isoformat()


def _norm_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _lot_count(record: dict[str, Any], lots: list[dict[str, Any]]) -> int:
    raw_total = record.get("total_lots")
    if raw_total not in (None, ""):
        try:
            return int(raw_total)
        except (TypeError, ValueError):
            pass
    return len(lots)


def _lot_signature(lots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signature: list[dict[str, Any]] = []
    for lot in lots[:25]:
        signature.append(
            {
                "lot_id": _norm(lot.get("lot_id")),
                "title": _norm(lot.get("item_title")),
                "quantity": _norm(lot.get("quantity")),
                "unit": _norm(lot.get("unit")),
                "start_price": _norm_number(lot.get("start_price_inr") or lot.get("start_price")),
                "documents": sorted(
                    _norm(d.get("filename")) for d in (lot.get("documents") or []) if isinstance(d, dict) and d.get("filename")
                ),
            }
        )
    return signature


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare current auction export with previous export.")
    parser.add_argument("--current", type=Path, required=True, help="Current candidate export JSON")
    parser.add_argument("--previous", type=Path, help="Previous production export JSON")
    parser.add_argument("--out", type=Path, required=True, help="Incremental decision report JSON")
    parser.add_argument("--merged-out", type=Path, help="Optional merged export with unchanged records reused")
    parser.add_argument("--scope", choices=("enriched", "listing"), default="enriched")
    args = parser.parse_args(argv)

    current = load_export(args.current)
    previous = load_export(args.previous) if args.previous and args.previous.is_file() else None
    if args.merged_out:
        merged, report = merge_reusing_unchanged_records(current, previous)
        write_export(args.merged_out, merged)
    else:
        report = compare_exports(current, previous, scope=args.scope)
    write_report(args.out, report)
    print(json.dumps(report.counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
