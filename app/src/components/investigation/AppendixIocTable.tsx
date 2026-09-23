"use client";

import { useState } from "react";
import type { AppendixIocTableProps, IocEntry } from "@/lib/dossier-types";

/**
 * Security Note:
 * - All untrusted indicator data (IOC values, types, attribution notes, confidence levels)
 *   is rendered strictly via React JSX auto-escaping.
 * - Strictly NO dangerouslySetInnerHTML or direct DOM innerHTML manipulation is used.
 */

function getTypeBadgeClasses(type: string): string {
  const normalized = (type || "").toLowerCase().trim();

  if (normalized.includes("domain") || normalized.includes("host")) {
    return "bg-sky-500/20 text-sky-300 border border-sky-500/30";
  }
  if (normalized === "ip" || normalized.includes("ip address") || normalized.includes("ipv4") || normalized.includes("ipv6")) {
    return "bg-purple-500/20 text-purple-300 border border-purple-500/30";
  }
  if (normalized.includes("file") || normalized.includes("hash") || normalized.includes("sha") || normalized.includes("md5")) {
    return "bg-amber-500/20 text-amber-300 border border-amber-500/30";
  }
  if (normalized.includes("url") || normalized.includes("uri")) {
    return "bg-teal-500/20 text-teal-300 border border-teal-500/30";
  }
  return "bg-slate-800/80 text-slate-300 border border-slate-700/50";
}

function getConfidenceBadgeClasses(confidence: string): string {
  const normalized = (confidence || "").toUpperCase().trim();

  if (normalized === "HIGH" || normalized === "CRITICAL") {
    return "bg-rose-500/20 text-rose-300 border border-rose-500/30";
  }
  if (normalized === "MEDIUM") {
    return "bg-amber-500/20 text-amber-300 border border-amber-500/30";
  }
  return "bg-slate-800 text-slate-400 border border-slate-700";
}

export function AppendixIocTable({
  iocs,
  onJumpToNode,
  onCopyIoc,
}: AppendixIocTableProps) {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const safeIocs: IocEntry[] = Array.isArray(iocs) ? iocs : [];

  const handleCopy = (value: string, index: number) => {
    onCopyIoc(value);
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(value).catch(() => {
        // Ignore clipboard errors if already handled by parent callback
      });
    }
    setCopiedIndex(index);
    setTimeout(() => {
      setCopiedIndex((prev) => (prev === index ? null : prev));
    }, 2000);
  };

  return (
    <div className="my-8 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl overflow-hidden not-prose">
      <div id="section-iocs" className="scroll-mt-20" />

      {/* Header bar */}
      <div className="p-4 border-b border-slate-800 bg-slate-950/80 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-teal-500/20 text-teal-400 flex items-center justify-center font-bold shrink-0">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="w-4 h-4"
              aria-hidden="true"
            >
              <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
              <path d="M12 8v4" />
              <path d="M12 16h.01" />
            </svg>
          </div>
          <div>
            <h4 className="font-bold text-sm text-white flex items-center gap-2 flex-wrap">
              <span>Appendix: Consolidated Indicators of Compromise (IOCs)</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-teal-950 text-teal-300 border border-teal-800/60 font-semibold uppercase">
                {safeIocs.length} Verified Indicators
              </span>
            </h4>
            <p className="text-[11px] text-slate-400">
              Structured intelligence indicators with analyst attribution context and confidence scoring
            </p>
          </div>
        </div>
      </div>

      {/* Table or Empty State */}
      {safeIocs.length === 0 ? (
        <div className="p-8 text-center">
          <p className="text-xs font-mono text-slate-400">
            No verified Indicators of Compromise (IOCs) available for this threat dossier.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/70 text-slate-400 font-mono uppercase text-[10px]">
                <th className="py-3 px-4">Indicator (IOC)</th>
                <th className="py-3 px-4">Type</th>
                <th className="py-3 px-4">Context / Attribution Notes</th>
                <th className="py-3 px-4">Confidence</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono" id="ioc-table-body">
              {safeIocs.map((ioc, index) => {
                const isCopied = copiedIndex === index;
                const displayType = (ioc.type || "IOC").toUpperCase();
                const displayConfidence = (ioc.confidence || "LOW").toUpperCase();
                const displayNotes = ioc.notes && ioc.notes.trim() ? ioc.notes : "--";

                return (
                  <tr
                    key={`${ioc.value}-${index}`}
                    className="hover:bg-slate-900/50 transition-colors"
                  >
                    <td className="py-3 px-4 font-semibold text-slate-200 break-all">
                      {ioc.value}
                    </td>
                    <td className="py-3 px-4 text-[10px]">
                      <span
                        className={`px-2 py-0.5 rounded uppercase font-semibold inline-block ${getTypeBadgeClasses(
                          ioc.type
                        )}`}
                      >
                        {displayType}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-300 text-xs font-sans">
                      {displayNotes}
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold inline-block ${getConfidenceBadgeClasses(
                          ioc.confidence
                        )}`}
                      >
                        {displayConfidence}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => onJumpToNode(ioc.value)}
                          title="Inspect on Canvas"
                          className="p-1 rounded hover:bg-slate-800 text-teal-400 hover:text-teal-300 transition-colors flex items-center gap-1 text-[11px] cursor-pointer"
                        >
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            className="w-3.5 h-3.5"
                            aria-hidden="true"
                          >
                            <rect x="16" y="16" width="6" height="6" rx="1" />
                            <rect x="2" y="16" width="6" height="6" rx="1" />
                            <rect x="9" y="2" width="6" height="6" rx="1" />
                            <path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3" />
                            <path d="M12 12V8" />
                          </svg>
                          <span className="hidden sm:inline">Canvas</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleCopy(ioc.value, index)}
                          title={isCopied ? "Copied!" : "Copy Indicator"}
                          className={`p-1 rounded hover:bg-slate-800 transition-colors flex items-center gap-1 cursor-pointer ${
                            isCopied
                              ? "text-emerald-400"
                              : "text-slate-400 hover:text-white"
                          }`}
                        >
                          {isCopied ? (
                            <>
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                className="w-3.5 h-3.5"
                                aria-hidden="true"
                              >
                                <path d="M20 6 9 17l-5-5" />
                              </svg>
                              <span className="text-[10px] font-mono">Copied</span>
                            </>
                          ) : (
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              className="w-3.5 h-3.5"
                              aria-hidden="true"
                            >
                              <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
                              <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
                            </svg>
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default AppendixIocTable;
