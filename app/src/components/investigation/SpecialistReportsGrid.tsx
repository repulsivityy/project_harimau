"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  SpecialistReportsGridProps,
  SpecialistReportData,
  MitreTechnique,
} from "@/lib/dossier-types";

function CpuIcon({ className }: { className?: string }) {
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
      <rect width="16" height="16" x="4" y="4" rx="2" />
      <rect width="6" height="6" x="9" y="9" rx="1" />
      <path d="M15 2v2" />
      <path d="M15 20v2" />
      <path d="M2 15h2" />
      <path d="M2 9h2" />
      <path d="M20 15h2" />
      <path d="M20 9h2" />
      <path d="M9 2v2" />
      <path d="M9 20v2" />
    </svg>
  );
}

function BinaryIcon({ className }: { className?: string }) {
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
      <rect x="14" y="14" width="4" height="6" rx="2" />
      <rect x="6" y="4" width="4" height="6" rx="2" />
      <path d="M6 20h4" />
      <path d="M14 10h4" />
      <path d="M6 14h2v6" />
      <path d="M14 4h2v6" />
    </svg>
  );
}

function GlobeIcon({ className }: { className?: string }) {
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
      <circle cx="12" cy="12" r="10" />
      <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
      <path d="M2 12h20" />
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

function RadioIcon({ className }: { className?: string }) {
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
      <path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9" />
      <path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5" />
      <circle cx="12" cy="12" r="2" />
      <path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5" />
      <path d="M19.1 4.9C23 8.8 23 15.1 19.1 19" />
    </svg>
  );
}

function FileCodeIcon({ className }: { className?: string }) {
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
      <path d="M10 12.5 8 15l2 2.5" />
      <path d="m14 12.5 2 2.5-2 2.5" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z" />
    </svg>
  );
}

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

function ArrowUpRightIcon({ className }: { className?: string }) {
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
      <path d="M7 7h10v10" />
      <path d="M7 17 17 7" />
    </svg>
  );
}

function renderMitreChips(mitre?: MitreTechnique[]) {
  if (!mitre || !Array.isArray(mitre) || mitre.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 pt-1">
      {mitre.map((m, idx) => {
        const truncatedName = m.name
          ? m.name.length > 28
            ? `${m.name.slice(0, 26)}...`
            : m.name
          : "";
        return (
          <span
            key={`${m.id}-${idx}`}
            className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400 font-medium"
            title={m.name || ""}
          >
            <b className="text-teal-400 font-semibold">{m.id}</b> {truncatedName}
          </span>
        );
      })}
    </div>
  );
}

function renderFindings(findings?: string[]) {
  if (!findings || !Array.isArray(findings) || findings.length === 0)
    return null;
  return (
    <div className="pt-2">
      <span className="text-[10px] font-mono text-slate-500 uppercase font-semibold block mb-1.5">
        Key Findings &amp; Discoveries:
      </span>
      <ul className="space-y-1.5 text-xs text-slate-300 list-disc list-inside">
        {findings.map((finding, idx) => (
          <li key={idx} className="leading-relaxed text-slate-300/90">
            {finding}
          </li>
        ))}
      </ul>
    </div>
  );
}

function renderTargetChips(
  targets?: Array<string | { id?: string; value?: string }>,
  onJumpToNode?: (nodeId: string) => void,
  onCopyIoc?: (ioc: string) => void
) {
  if (!targets || !Array.isArray(targets) || targets.length === 0) return null;
  return (
    <div className="pt-2">
      <span className="text-[10px] font-mono text-slate-500 uppercase font-semibold block mb-1.5">
        Investigated Targets &amp; Artifacts:
      </span>
      <div className="flex flex-wrap gap-1.5">
        {targets.map((t, idx) => {
          const val =
            typeof t === "string"
              ? t
              : t.id || t.value || JSON.stringify(t);
          return (
            <span
              key={`${val}-${idx}`}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-950/80 border border-slate-800 text-xs font-mono text-slate-300"
            >
              <span
                className="truncate max-w-[180px] xl:max-w-[240px]"
                title={val}
              >
                {val}
              </span>
              {onCopyIoc && (
                <button
                  type="button"
                  onClick={() => onCopyIoc(val)}
                  title="Copy"
                  className="hover:text-white p-0.5 text-slate-500 transition-colors"
                >
                  <CopyIcon className="w-3 h-3" />
                </button>
              )}
              {onJumpToNode && (
                <button
                  type="button"
                  onClick={() => onJumpToNode(val)}
                  title="View in Canvas"
                  className="hover:text-teal-400 p-0.5 text-slate-500 transition-colors"
                >
                  <ArrowUpRightIcon className="w-3 h-3" />
                </button>
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export type SpecialistTheme = "amber" | "teal" | "sky";

export interface SpecialistThemeStyles {
  border: string;
  iconContainer: string;
  badge: string;
  verdictCol: string;
  accentText: string;
}

export const SPECIALIST_THEMES: Record<SpecialistTheme, SpecialistThemeStyles> = {
  amber: {
    border: "border-amber-500/30",
    iconContainer:
      "bg-amber-500/15 text-amber-400 border border-amber-500/30 shadow-amber-500/10",
    badge: "bg-amber-950 text-amber-300 border border-amber-800/60",
    verdictCol: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    accentText: "text-amber-400",
  },
  sky: {
    border: "border-sky-500/30",
    iconContainer:
      "bg-sky-500/15 text-sky-400 border border-sky-500/30 shadow-sky-500/10",
    badge: "bg-sky-950 text-sky-300 border border-sky-800/60",
    verdictCol: "bg-sky-500/20 text-sky-300 border-sky-500/40",
    accentText: "text-sky-400",
  },
  teal: {
    border: "border-teal-500/30",
    iconContainer:
      "bg-teal-500/15 text-teal-400 border border-teal-500/30 shadow-teal-500/10",
    badge: "bg-teal-950 text-teal-300 border border-teal-800/60",
    verdictCol: "bg-teal-500/20 text-teal-300 border-teal-500/40",
    accentText: "text-teal-400",
  },
};

export interface SpecialistCardProps {
  theme: SpecialistTheme;
  icon: React.ReactNode;
  title: string;
  agentBadge: string;
  subtitle: string;
  synthesisIcon: React.ReactNode;
  defaultSummary?: string;
  report?: SpecialistReportData | null;
  reportData?: SpecialistReportData | null;
  expanded?: boolean;
  isExpanded?: boolean;
  toggleExpanded?: () => void;
  onToggleExpanded?: () => void;
  expandButtonIcon: React.ReactNode;
  expandButtonLabel: string;
  targets?: Array<string | { id?: string; value?: string }>;
  onJumpToNode: (nodeId: string) => void;
  onCopyIoc: (ioc: string) => void;
}

export function SpecialistCard({
  theme,
  icon,
  title,
  agentBadge,
  subtitle,
  synthesisIcon,
  defaultSummary = "Analysis completed.",
  report,
  reportData,
  expanded,
  isExpanded,
  toggleExpanded,
  onToggleExpanded,
  expandButtonIcon,
  expandButtonLabel,
  targets = [],
  onJumpToNode,
  onCopyIoc,
}: SpecialistCardProps) {
  const currentReport = report || reportData;
  if (!currentReport) return null;

  const styles = SPECIALIST_THEMES[theme] || SPECIALIST_THEMES.amber;
  const isMal = (currentReport.verdict || "")
    .toUpperCase()
    .includes("MALICIOUS");
  const verdictCol = isMal
    ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
    : styles.verdictCol;

  const isCardExpanded = Boolean(expanded ?? isExpanded);
  const handleToggle = toggleExpanded || onToggleExpanded || (() => {});

  return (
    <div
      className={`rounded-2xl bg-gradient-to-b from-slate-900/90 to-slate-950 border ${styles.border} p-5 space-y-4 shadow-xl flex flex-col justify-between`}
    >
      <div className="space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 pb-3 border-b border-slate-800/80">
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-xl ${styles.iconContainer} flex items-center justify-center font-bold shadow-md shrink-0`}
            >
              {icon}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="font-bold text-sm text-white">{title}</h4>
                <span
                  className={`text-[9px] font-mono px-2 py-0.5 rounded ${styles.badge} font-semibold`}
                >
                  {agentBadge}
                </span>
              </div>
              <p className="text-[11px] text-slate-400">{subtitle}</p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <span
              className={`text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full border ${verdictCol}`}
            >
              {currentReport.verdict || "ANALYZED"}
            </span>
            {currentReport.confidence && (
              <span className="text-[9px] font-mono text-slate-500 uppercase">
                {currentReport.confidence} CONFIDENCE
              </span>
            )}
          </div>
        </div>

        {/* Specialist Synthesis Box */}
        <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/90 text-xs text-slate-300 leading-relaxed font-sans">
          <div
            className={`flex items-center gap-1.5 ${styles.accentText} font-semibold text-[11px] mb-1 font-mono uppercase`}
          >
            {synthesisIcon}
            <span>Specialist Synthesis:</span>
          </div>
          {currentReport.summary || defaultSummary}
        </div>

        {renderMitreChips(currentReport.mitre_attack)}
        {renderFindings(currentReport.key_findings)}
        {renderTargetChips(targets, onJumpToNode, onCopyIoc)}
      </div>

      {/* Expandable Detailed Technical Report */}
      {currentReport.markdown_report && (
        <div className="pt-3 border-t border-slate-800/60 mt-2">
          <button
            type="button"
            onClick={handleToggle}
            className="w-full py-2 px-3 rounded-lg bg-slate-800/80 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold flex items-center justify-between transition-colors"
          >
            <span className="flex items-center gap-2 font-mono">
              {expandButtonIcon}
              <span>{expandButtonLabel}</span>
            </span>
            <span className="text-[11px] text-slate-400 font-mono">
              {isCardExpanded ? "Hide Report ▴" : "View Report ▾"}
            </span>
          </button>
          {isCardExpanded && (
            <div className="mt-3 p-4 rounded-xl bg-slate-950 border border-slate-800/90 threat-dossier-prose text-xs text-slate-300 max-h-[500px] overflow-y-auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {currentReport.markdown_report}
              </ReactMarkdown>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function SpecialistReportsGrid({
  job,
  onJumpToNode,
  onCopyIoc,
}: SpecialistReportsGridProps) {
  const [malwareExpanded, setMalwareExpanded] = useState(false);
  const [infraExpanded, setInfraExpanded] = useState(false);

  const sr =
    job?.specialist_reports ||
    job?.specialist_results ||
    job?.metadata?.specialist_results ||
    {};

  const malware: SpecialistReportData | null =
    sr.malware_specialist || sr.malware || null;
  const infra: SpecialistReportData | null =
    sr.infrastructure_specialist || sr.infrastructure || null;

  if (!malware && !infra) {
    return (
      <div className="my-8 space-y-4 not-prose">
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/60 text-xs text-slate-400 font-mono">
          Autonomous specialist deep-dives (Malware / Network analysis) were not
          triggered for this indicator classification.
        </div>
      </div>
    );
  }

  return (
    <div className="my-8 space-y-4 not-prose">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-teal-500/20 text-teal-400 flex items-center justify-center font-bold shadow-md shadow-teal-500/10">
            <CpuIcon className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
              Specialist Reports: Malware &amp; Infrastructure Analysis
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-teal-950 text-teal-300 border border-teal-800/60 font-semibold uppercase">
                Swarm Sub-Agents
              </span>
            </h4>
            <p className="text-xs text-slate-400">
              Technical evaluations authored by Harimau&apos;s specialized
              investigation agents
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-4">
        {malware && (
          <SpecialistCard
            theme="amber"
            icon={<BinaryIcon className="w-5 h-5" />}
            title="Malware Analysis Specialist"
            agentBadge="AGENT-01"
            subtitle="Binary disassembly, LOLBin execution, living-off-the-land & script analysis"
            synthesisIcon={<TerminalIcon className="w-3.5 h-3.5" />}
            defaultSummary="Malware analysis completed."
            report={malware}
            expanded={malwareExpanded}
            onToggleExpanded={() => setMalwareExpanded((prev) => !prev)}
            expandButtonIcon={
              <FileCodeIcon className="w-3.5 h-3.5 text-amber-400" />
            }
            expandButtonLabel="Technical Reverse-Engineering Teardown"
            targets={malware.analyzed_targets || malware.iocs_extracted || []}
            onJumpToNode={onJumpToNode}
            onCopyIoc={onCopyIoc}
          />
        )}

        {infra && (
          <SpecialistCard
            theme="sky"
            icon={<GlobeIcon className="w-5 h-5" />}
            title="Infrastructure & Network Specialist"
            agentBadge="AGENT-02"
            subtitle="Passive DNS, registrar profiling, ASN routing, TLS fingerprints & C2 pivoting"
            synthesisIcon={<RadioIcon className="w-3.5 h-3.5" />}
            defaultSummary="Infrastructure analysis completed."
            report={infra}
            expanded={infraExpanded}
            onToggleExpanded={() => setInfraExpanded((prev) => !prev)}
            expandButtonIcon={
              <NetworkIcon className="w-3.5 h-3.5 text-sky-400" />
            }
            expandButtonLabel="Technical Infrastructure Teardown"
            targets={infra.analyzed_targets || infra.iocs_extracted || []}
            onJumpToNode={onJumpToNode}
            onCopyIoc={onCopyIoc}
          />
        )}
      </div>
    </div>
  );
}

export default SpecialistReportsGrid;
