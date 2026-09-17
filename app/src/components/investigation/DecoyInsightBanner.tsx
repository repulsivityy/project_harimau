"use client";

import React from "react";
import type { DecoyInsightBannerProps } from "@/lib/dossier-types";

export function DecoyInsightBanner({ decoyCount }: DecoyInsightBannerProps) {
  if (decoyCount <= 0) {
    return null;
  }

  return (
    <div className="p-4 rounded-xl bg-teal-950/30 border border-teal-500/40 flex items-start gap-3.5">
      <div className="w-7 h-7 rounded-lg bg-teal-500/20 text-teal-300 flex items-center justify-center shrink-0 mt-0.5 font-bold">
        <svg
          className="w-4 h-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      </div>
      <div>
        <div className="text-xs font-bold text-teal-300 flex flex-wrap items-center gap-2">
          <span>Observed Anti-Analysis &amp; Decoy Infrastructure</span>
          <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-teal-900/80 text-teal-200 border border-teal-700/60 font-semibold">
            T1036 Evasion
          </span>
          <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-teal-950/80 text-teal-300 border border-teal-800/60 font-semibold">
            {decoyCount} {decoyCount === 1 ? "Decoy Node" : "Decoy Nodes"}
          </span>
        </div>
        <p className="text-[11px] text-teal-200/80 mt-1.5 leading-relaxed">
          The threat actor incorporates authentic, legitimate services (e.g. downloading signed runtime from official repository, or redirecting user to genuine login portals) to bypass detection and prevent victims from realizing an attack occurred.
        </p>
      </div>
    </div>
  );
}

export default DecoyInsightBanner;
