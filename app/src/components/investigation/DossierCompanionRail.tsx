"use client";

import React from "react";
import type { DossierCompanionRailProps } from "@/lib/dossier-types";

function NetworkIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="16" y="16" width="6" height="6" rx="1" />
      <rect x="2" y="16" width="6" height="6" rx="1" />
      <rect x="9" y="2" width="6" height="6" rx="1" />
      <path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3" />
      <path d="M12 12V8" />
    </svg>
  );
}

function ArrowRightIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  );
}

function CopyIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
    </svg>
  );
}

function TerminalIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" x2="20" y1="19" y2="19" />
    </svg>
  );
}

function formatCreatedTime(ts?: string): string {
  if (!ts) return "--";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleTimeString();
}

export function DossierCompanionRail({
  job,
  onOpenCanvasTab,
  onCopyIoc,
  onToggleAgentLog,
}: DossierCompanionRailProps) {
  const createdTime = formatCreatedTime(job.created_at);

  return (
    <aside className="hidden lg:block w-80 shrink-0">
      <div className="sticky top-20 space-y-6">
        {/* Card 1: Jump to Canvas Card */}
        <div className="p-4 rounded-2xl bg-gradient-to-br from-slate-900 to-slate-950 border border-teal-500/30 space-y-3 shadow-xl">
          <div className="flex items-center gap-2 text-teal-300 font-semibold text-xs">
            <NetworkIcon className="w-4 h-4" />
            <span>Explore Topology in Canvas</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            Visualize the full relationship graph, pivoting hops, and entity
            linkages in the D3 workspace.
          </p>
          <button
            type="button"
            onClick={onOpenCanvasTab}
            className="w-full py-2 px-3 rounded-lg bg-teal-500/20 hover:bg-teal-500/30 text-teal-200 border border-teal-500/40 text-xs font-semibold flex items-center justify-center gap-2 transition-all"
          >
            <span>Open Canvas Tab</span>
            <ArrowRightIcon className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Card 2: Threat Dossier Quick Jump Table of Contents */}
        <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-2.5 text-xs">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
            Threat Dossier Contents
          </span>
          <nav className="space-y-1 font-mono text-[11px]">
            <a
              href="#section-1-executive-summary"
              className="flex items-center gap-2.5 p-1.5 rounded hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
            >
              <span className="w-4 h-4 rounded bg-slate-800 text-teal-400 flex items-center justify-center text-[10px] font-bold shrink-0">
                1
              </span>
              <span className="truncate">Executive Summary</span>
            </a>
            <a
              href="#section-2-attack-narrative"
              className="flex items-center gap-2.5 p-1.5 rounded hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
            >
              <span className="w-4 h-4 rounded bg-slate-800 text-teal-400 flex items-center justify-center text-[10px] font-bold shrink-0">
                2
              </span>
              <span className="truncate">Attack Narrative</span>
            </a>
            <a
              href="#section-3-specialist-reports"
              className="flex items-center gap-2.5 p-1.5 rounded hover:bg-slate-800 text-amber-300/90 hover:text-amber-200 transition-colors"
            >
              <span className="w-4 h-4 rounded bg-amber-950/80 border border-amber-800/60 text-amber-400 flex items-center justify-center text-[10px] font-bold shrink-0">
                3
              </span>
              <span className="truncate">Specialist Reports</span>
            </a>
            <a
              href="#section-4-investigation-timeline"
              className="flex items-center gap-2.5 p-1.5 rounded hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
            >
              <span className="w-4 h-4 rounded bg-slate-800 text-teal-400 flex items-center justify-center text-[10px] font-bold shrink-0">
                4
              </span>
              <span className="truncate">Investigation Timeline</span>
            </a>
            <a
              href="#section-5-technical-analysis"
              className="flex items-center gap-2.5 p-1.5 rounded hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
            >
              <span className="w-4 h-4 rounded bg-slate-800 text-teal-400 flex items-center justify-center text-[10px] font-bold shrink-0">
                5
              </span>
              <span className="truncate">Technical Analysis</span>
            </a>
            <a
              href="#section-6-attack-flow-diagram"
              className="flex items-center gap-2.5 p-1.5 rounded hover:bg-slate-800 text-teal-300 hover:text-teal-200 transition-colors"
            >
              <span className="w-4 h-4 rounded bg-teal-950/80 border border-teal-800/60 text-teal-400 flex items-center justify-center text-[10px] font-bold shrink-0">
                6
              </span>
              <span className="truncate">Attack Flow Diagram</span>
            </a>
            <a
              href="#section-7-appendix"
              className="flex items-center gap-2.5 p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            >
              <span className="w-4 h-4 rounded bg-slate-800 text-slate-400 flex items-center justify-center text-[10px] font-bold shrink-0">
                7
              </span>
              <span className="truncate">Appendix (IOCs)</span>
            </a>
          </nav>
        </div>

        {/* Card 3: Target IOC Card */}
        <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
              Target IOC
            </span>
            <button
              type="button"
              onClick={() => onCopyIoc(job.ioc)}
              title="Copy IOC"
              className="flex items-center gap-1 text-[10px] font-mono text-slate-400 hover:text-white transition-colors px-1.5 py-0.5 rounded hover:bg-slate-800"
            >
              <CopyIcon className="w-3 h-3" />
              <span>Copy</span>
            </button>
          </div>
          <div
            onClick={() => onCopyIoc(job.ioc)}
            title="Click to copy IOC"
            className="font-mono text-white text-xs break-all bg-slate-950 p-2 rounded border border-slate-800 cursor-pointer hover:border-teal-500/40 transition-colors"
            id="rail-ioc"
          >
            {job.ioc || "--"}
          </div>
          <div className="flex justify-between text-[11px] text-slate-400 pt-1">
            <span>Created:</span>
            <span id="rail-created" className="font-mono text-slate-300">
              {createdTime}
            </span>
          </div>
        </div>

        {/* Card 4: Agent Orchestration Card */}
        <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-2">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
            Agent Orchestration
          </span>
          <p className="text-xs text-slate-400">
            Inspect the chronological agent subtasks, tool execution timestamps,
            and checkpoints.
          </p>
          <button
            type="button"
            onClick={() => onToggleAgentLog?.()}
            className="w-full py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium flex items-center justify-center gap-1.5 transition-colors"
          >
            <TerminalIcon className="w-3.5 h-3.5 text-teal-400" />
            <span>View Agent Log</span>
          </button>
        </div>
      </div>
    </aside>
  );
}

export default DossierCompanionRail;
