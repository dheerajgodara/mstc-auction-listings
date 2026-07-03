export function confidenceChipClass(confidence?: string | null): string {
  switch (confidence) {
    case "high":
      return "bg-emerald-50 text-emerald-800 border-emerald-200/80";
    case "medium":
      return "bg-amber-50 text-amber-800 border-amber-200/80";
    case "low":
    case "minimal":
      return "bg-rose-50 text-rose-800 border-rose-200/80";
    default:
      return "bg-slate-50 text-slate-600 border-slate-200/80";
  }
}

export function priceStatusChipClass(status?: string | null): string {
  switch (status) {
    case "numeric":
    case "range":
      return "bg-emerald-50 text-emerald-800 border-emerald-200/80";
    case "percentage_based":
      return "bg-violet-50 text-violet-800 border-violet-200/80";
    case "not_disclosed":
      return "bg-amber-50 text-amber-800 border-amber-200/80";
    case "missing":
      return "bg-rose-50 text-rose-800 border-rose-200/80";
    default:
      return "bg-slate-50 text-slate-600 border-slate-200/80";
  }
}

export function emdStatusChipClass(status?: string | null): string {
  switch (status) {
    case "auction_wise":
    case "item_wise":
      return "bg-cyan-50 text-cyan-800 border-cyan-200/80";
    case "not_required":
      return "bg-emerald-50 text-emerald-800 border-emerald-200/80";
    case "missing":
      return "bg-rose-50 text-rose-800 border-rose-200/80";
    default:
      return "bg-slate-50 text-slate-600 border-slate-200/80";
  }
}

export function regionChipClass(): string {
  return "bg-cyan-50 text-cyan-900 border-cyan-200/80";
}

export function lotTypeChipClass(): string {
  return "bg-violet-50 text-violet-800 border-violet-200/80";
}

export function formatChipLabel(value: string): string {
  return value.replace(/_/g, " ");
}
