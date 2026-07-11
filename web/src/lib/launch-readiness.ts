import { resolvePublicUrl } from "@/lib/utils";

/** Launch gate status — informational; approval remains manual. */
export type GateStatus = "pass" | "warn" | "fail" | "blocked" | "manual";

/** Staged launch sequence (Forge 010). */
export type LaunchStage =
  | "internal"
  | "soft_launch"
  | "paid_beta"
  | "public_launch";

export interface LaunchGate {
  id: string;
  title: string;
  status: GateStatus;
  detail?: string;
  manual?: boolean;
  blocker?: boolean;
}

export interface LaunchGateGroup {
  id: string;
  title: string;
  gates: LaunchGate[];
}

export interface LaunchFreshness {
  automation_ran_at?: string;
  age_hours?: number;
  threshold_hours: number;
  within_threshold?: boolean;
}

export interface LaunchReadinessReport {
  generated_at: string;
  phase: "006";
  site_url: string;
  current_stage_recommendation: LaunchStage;
  /** Always false — public launch requires explicit owner approval. */
  launch_approved: false;
  readiness_score: number;
  hard_blockers: string[];
  warnings: string[];
  manual_gates: string[];
  next_steps: string[];
  source_counts: Record<string, number>;
  total_auctions: number;
  freshness: LaunchFreshness;
  groups: LaunchGateGroup[];
}

export const LAUNCH_STAGES: { id: LaunchStage; label: string; description: string }[] = [
  {
    id: "internal",
    label: "Internal",
    description: "Team-only readiness checks and gate automation.",
  },
  {
    id: "soft_launch",
    label: "Soft launch",
    description: "Invite known buyers; collect feedback; no paid conversion yet.",
  },
  {
    id: "paid_beta",
    label: "Paid beta",
    description: "Manual invites with live billing after legal/provider/buyer gates.",
  },
  {
    id: "public_launch",
    label: "Public launch",
    description: "Broader marketing after product proof and support capacity.",
  },
];

export const GATE_STATUS_LABELS: Record<GateStatus, string> = {
  pass: "Pass",
  warn: "Warn",
  fail: "Fail",
  blocked: "Blocked",
  manual: "Manual",
};

/** Airbnb token classes only — no raw emerald/amber/sky/red Tailwind chrome. */
export const GATE_STATUS_STYLES: Record<GateStatus, string> = {
  pass: "bg-muted text-foreground border-border",
  warn: "bg-muted text-muted-foreground border-border",
  fail: "bg-muted text-foreground border-border",
  blocked: "bg-muted text-foreground border-border",
  manual: "bg-muted text-action border-border",
};

export const GATE_STATUS_ICON_STYLES: Record<GateStatus, string> = {
  pass: "text-foreground",
  warn: "text-muted-foreground",
  fail: "text-foreground",
  blocked: "text-foreground",
  manual: "text-action",
};

/** Explains that manual gates block paid/public launch, not soft launch. */
export function stageRecommendationNote(stage: LaunchStage): string {
  if (stage === "soft_launch") {
    return "Soft launch may proceed with known buyers. Paid beta and public launch remain blocked until manual legal, provider, buyer, and launch-approval gates pass.";
  }
  if (stage === "internal") {
    return "Resolve hard blockers before soft launch. Manual gates will still block paid beta and public launch.";
  }
  if (stage === "paid_beta" || stage === "public_launch") {
    return "All automated gates passed; owner must still approve billing and public launch explicitly.";
  }
  return "";
}

export function launchReadinessJsonUrl(): string {
  return resolvePublicUrl("data/launch-readiness.json");
}

export async function loadLaunchReadinessReport(): Promise<LaunchReadinessReport> {
  const response = await fetch(launchReadinessJsonUrl(), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Launch readiness report unavailable (${response.status})`);
  }
  return (await response.json()) as LaunchReadinessReport;
}

export function countGatesByStatus(
  report: LaunchReadinessReport,
  status: GateStatus,
): number {
  return report.groups.reduce(
    (sum, group) => sum + group.gates.filter((g) => g.status === status).length,
    0,
  );
}

export function groupSummary(group: LaunchGateGroup): GateStatus {
  if (group.gates.some((g) => g.status === "fail" || g.status === "blocked")) {
    return "fail";
  }
  if (group.gates.some((g) => g.status === "manual")) return "manual";
  if (group.gates.some((g) => g.status === "warn")) return "warn";
  return "pass";
}
