"use client";

import React, { useState } from "react";
import type {
  TacticalSwimLanesProps,
  SwimLaneStage,
  ParsedDotNode,
} from "@/lib/dossier-types";

function StageIcon({ icon }: { icon: string }) {
  switch (icon) {
    case "download-cloud":
      return (
        <svg
          className="w-4 h-4 shrink-0"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" />
          <path d="M12 12v9" />
          <path d="m8 17 4 4 4-4" />
        </svg>
      );
    case "terminal":
      return (
        <svg
          className="w-4 h-4 shrink-0"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polyline points="4 17 10 11 4 5" />
          <line x1="12" x2="20" y1="19" y2="19" />
        </svg>
      );
    case "shield":
      return (
        <svg
          className="w-4 h-4 shrink-0"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
        </svg>
      );
    case "file-output":
      return (
        <svg
          className="w-4 h-4 shrink-0"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M14 2v4a2 2 0 0 0 2 2h4" />
          <path d="M4 7V4a2 2 0 0 1 2-2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-3" />
          <path d="M5 14h6" />
          <path d="m8 11 3 3-3 3" />
        </svg>
      );
    case "radio":
    default:
      return (
        <svg
          className="w-4 h-4 shrink-0"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9" />
          <path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5" />
          <circle cx="12" cy="12" r="2" />
          <path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5" />
          <path d="M19.1 4.9C23 8.8 23 15.1 19.1 19" />
        </svg>
      );
  }
}

function SwimLaneItemCard({
  item,
  stage,
  onCopyIoc,
  onJumpToNode,
}: {
  item: ParsedDotNode;
  stage: SwimLaneStage;
  onCopyIoc: (value: string) => void;
  onJumpToNode: (nodeId: string) => void;
}) {
  const [copied, setCopied] = useState(false);

  const isDecoy = Boolean(item.isDecoy);
  const scoreVal = item.threatScore ?? null;
  const scoreColor = isDecoy
    ? "text-teal-400"
    : scoreVal !== null && scoreVal >= 70
      ? "text-rose-400"
      : scoreVal !== null && scoreVal >= 40
        ? "text-amber-400"
        : "text-slate-400";

  const scoreDisplay = isDecoy
    ? "LEGITIMATE"
    : scoreVal !== null && scoreVal !== undefined
      ? `${scoreVal}/100`
      : item.verdict || "";

  const displayLabel = item.friendlyName || item.label || item.id;
  const showUnderlyingId = Boolean(
    item.friendlyName && item.id !== item.friendlyName
  );

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    onCopyIoc(item.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleJump = (e: React.MouseEvent) => {
    e.stopPropagation();
    onJumpToNode(item.id);
  };

  return (
    <div
      className={`group p-3.5 rounded-xl bg-slate-900/70 hover:bg-slate-900 border ${
        isDecoy
          ? "border-teal-500/40 border-dashed"
          : "border-slate-800 hover:border-slate-700"
      } transition-all shadow-sm min-w-0 w-full`}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5 min-w-0">
        <span
          className={`text-[9px] font-mono px-2 py-0.5 rounded ${stage.itemBadgeStyle} uppercase font-semibold tracking-wide truncate min-w-0`}
        >
          {stage.itemRoleLabel || item.entityType || "Indicator"}
        </span>
        <span className={`text-[10px] font-mono font-bold ${scoreColor} shrink-0`}>
          {scoreDisplay}
        </span>
      </div>

      <div
        className="text-xs font-mono font-semibold text-slate-200 truncate group-hover:text-white mt-1 min-w-0"
        title={item.id}
      >
        {displayLabel}
      </div>

      {showUnderlyingId && (
        <div
          className="text-[10px] font-mono text-slate-500 truncate mt-0.5 min-w-0"
          title={item.id}
        >
          {item.id}
        </div>
      )}

      <div className="flex items-center justify-between gap-1 mt-2.5 pt-2 border-t border-slate-800/60 text-[11px] min-w-0">
        <span
          className={`text-[10px] font-mono ${
            isDecoy ? "text-teal-400 font-semibold" : "text-slate-400"
          } truncate min-w-0`}
        >
          {item.entityType || "entity"}
        </span>
        <div className="flex items-center gap-1.5 opacity-80 group-hover:opacity-100 shrink-0">
          <button
            type="button"
            onClick={handleCopy}
            title="Copy IOC"
            className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
          >
            {copied ? (
              <svg
                className="w-3.5 h-3.5 text-teal-400"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              <svg
                className="w-3.5 h-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
                <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
              </svg>
            )}
          </button>
          <button
            type="button"
            onClick={handleJump}
            title="Inspect on Canvas"
            className={`p-1 rounded hover:bg-slate-800 ${
              isDecoy ? "text-teal-400" : "text-amber-400"
            } hover:text-white transition-colors`}
          >
            <svg
              className="w-3.5 h-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M7 7h10v10" />
              <path d="M7 17 17 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

export function TacticalSwimLanes({
  activeStages,
  onJumpToNode,
  onCopyIoc,
}: TacticalSwimLanesProps) {
  const numStages = activeStages.length;

  return (
    <div className="space-y-4 w-full">
      {/* Swim Lanes Pipeline Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs pb-1 border-b border-slate-800/60">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
            <svg
              className="w-3.5 h-3.5 text-teal-400"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z" />
              <path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65" />
              <path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65" />
            </svg>
            Attack Progression Swim Lanes
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-semibold border border-slate-700/50">
            {numStages} Stages Active
          </span>
        </div>
        <div className="hidden sm:flex items-center gap-2 text-[10px] font-mono text-slate-500">
          <span>
            Execution Flow: Stage 1 ➔ Stage {Math.max(1, numStages)}
          </span>
        </div>
      </div>

      {/* Dynamic Width-Aligned Swim Lanes Grid */}
      <div
        style={
          {
            "--num-stages": Math.max(1, activeStages.length),
          } as React.CSSProperties
        }
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[repeat(var(--num-stages),minmax(0,1fr))] gap-4 w-full items-stretch"
      >
        {activeStages.map((stage, idx) => (
          <div
            key={stage.id || idx}
            className={`rounded-xl bg-slate-900/50 border ${stage.cardBorder} p-4 flex flex-col justify-between h-full min-w-0 w-full transition-all shadow-sm`}
          >
            <div className="flex-1 flex flex-col min-w-0">
              <div className="flex items-center justify-between gap-2 pb-2 mb-3 border-b border-slate-800/80 min-w-0">
                <div
                  className={`flex items-center gap-1.5 ${stage.headerColor} font-bold text-xs truncate min-w-0`}
                >
                  <span
                    className={`px-1.5 h-5 rounded-full ${stage.numBg} flex items-center justify-center text-[10px] font-mono shrink-0 font-bold`}
                  >
                    #{idx + 1}
                  </span>
                  <StageIcon icon={stage.icon} />
                  <span className="truncate">{stage.title}</span>
                </div>
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${stage.badgeBg} font-semibold shrink-0`}
                >
                  {stage.badgeText}
                </span>
              </div>
              <div className="space-y-2.5 max-h-[440px] overflow-y-auto pr-1 flex-1 min-w-0">
                {stage.nodes.map((node) => (
                  <SwimLaneItemCard
                    key={node.id}
                    item={node}
                    stage={stage}
                    onCopyIoc={onCopyIoc}
                    onJumpToNode={onJumpToNode}
                  />
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default TacticalSwimLanes;
