"use client";
import { useEffect } from "react";
import { resolvePublicUrl } from "@/lib/utils";
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator))
      return;
    const swUrl = resolvePublicUrl("sw.js");
    navigator.serviceWorker.register(swUrl).catch(() => {
      /* optional offline shell */
    });
  }, []);
  return null;
}
