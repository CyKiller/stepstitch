"use client";

import { useState } from "react";
import { Copy, Check } from "@phosphor-icons/react";

export function CopyButton({
  text,
  label = "Copy",
  className,
}: {
  text: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable; no-op */
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? "Copied" : label}
      className={`inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium transition-colors hover:border-fg/30 active:scale-[0.98] ${copied ? "text-ok" : "text-muted hover:text-fg"} ${className ?? ""}`}
    >
      {copied ? (
        <Check size={13} weight="bold" />
      ) : (
        <Copy size={13} weight="bold" />
      )}
      {copied ? "Copied" : label}
    </button>
  );
}
