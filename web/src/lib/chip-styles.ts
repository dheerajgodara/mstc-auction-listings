export function confidenceChipClass(confidence?: string | null): string {
  switch (confidence) {
    case "high":
      return "bg-[#e7f7f4] text-[#006c67] border-[#b8e6df]";
    case "medium":
      return "bg-[#fff4e8] text-[#9a4d13] border-[#ffd8ad]";
    case "low":
    case "minimal":
      return "bg-[#fff0f3] text-[#b00033] border-[#ffc7d2]";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

export function priceStatusChipClass(status?: string | null): string {
  switch (status) {
    case "numeric":
    case "range":
      return "bg-[#e7f7f4] text-[#006c67] border-[#b8e6df]";
    case "percentage_based":
      return "bg-[#fff4e8] text-[#9a4d13] border-[#ffd8ad]";
    case "not_disclosed":
      return "bg-muted text-muted-foreground border-border";
    case "missing":
      return "bg-muted text-muted-foreground border-border";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

export function emdStatusChipClass(status?: string | null): string {
  switch (status) {
    case "auction_wise":
    case "item_wise":
      return "bg-[#fff0f3] text-[#b00033] border-[#ffc7d2]";
    case "not_required":
      return "bg-muted text-foreground border-border";
    case "missing":
      return "bg-muted text-muted-foreground border-border";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

export function regionChipClass(): string {
  return "bg-muted text-foreground border-border";
}

export function lotTypeChipClass(): string {
  return "bg-muted text-muted-foreground border-border";
}

export function formatChipLabel(value: string): string {
  return value.replace(/_/g, " ");
}
