"use client";

import { useEffect, useState } from "react";
import { Modal } from "@/components/ui/modal";
import { loadEmdBalance, saveEmdBalance } from "@/lib/emd-calculator";
import { formatInr } from "@/lib/utils";

export function EmdCalculatorModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [balance, setBalance] = useState(0);
  const [draft, setDraft] = useState("");
  useEffect(() => {
    if (open) {
      const b = loadEmdBalance();
      setBalance(b);
      setDraft(b > 0 ? String(b) : "");
    }
  }, [open]);

  return (
    <Modal open={open} onClose={onClose} title="EMD capacity calculator">
      <p className="text-body-sm text-muted-foreground">
        Enter your available EMD balance to filter lots you can bid on. Stored
        on this device only.
      </p>
      <label className="mt-4 block text-body-sm font-medium text-foreground">
        My EMD balance (₹)
        <input
          type="number"
          min={0}
          className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2 tabular-nums"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
      </label>
      {balance > 0 && (
        <p className="mt-2 text-body-sm text-muted-foreground">
          Current saved balance:{" "}
          <span className="tabular-nums font-medium text-foreground">
            {formatInr(balance)}
          </span>
        </p>
      )}
      <p className="mt-3 text-footnote text-muted-foreground">
        EMD deposits are made on official source portals — this tool only helps
        discovery filtering.
      </p>
      <div className="mt-6 flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={() => {
            const n = Number(draft) || 0;
            saveEmdBalance(n);
            setBalance(n);
            onClose();
            window.location.reload();
          }}
        >
          Save & apply filter
        </button>
      </div>
    </Modal>
  );
}
