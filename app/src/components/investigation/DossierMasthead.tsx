"use client";

import React from "react";
import type { DossierMastheadProps } from "@/lib/dossier-types";

function formatTimestamp(ts?: string): string {
  if (!ts) return "Recorded";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
}

export function DossierMasthead({ job, graphEntityCount }: DossierMastheadProps) {
  const jobIdBadge = job.job_id ? `${job.job_id.slice(0, 13)}...` : "CASE-ID";
  const completedTime = formatTimestamp(job.completed_at || job.created_at);
  const gtiScoreColor = (job.gti_score ?? 0) >= 50 ? "text-rose-400" : "text-teal-400";

  return (
    <div className="space-y-8">
      {/* 1. Classification & Article Masthead */}
      <div className="space-y-3 border-b border-slate-800/90 pb-6">
        <div className="flex items-center gap-2.5">
          <span
            id="masthead-tlp"
            className="px-2.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider uppercase bg-amber-500/15 text-amber-400 border border-amber-500/30"
          >
            TLP:AMBER
          </span>
          <span
            id="masthead-job-id"
            className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold uppercase bg-slate-800 text-slate-400"
          >
            {jobIdBadge}
          </span>
          <span className="text-xs text-slate-500 font-mono">
            AUTOMATED THREAT SYNTHESIS
          </span>
        </div>

        <h1
          id="masthead-title"
          className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white leading-tight"
        >
          Threat Dossier Synthesis Brief
        </h1>

        <p
          id="masthead-summary"
          className="text-sm text-slate-400 font-normal leading-relaxed"
        >
          Synthesized by Harimau Multi-Agent LangGraph Swarm.
        </p>

        <div className="pt-2 flex flex-wrap items-center justify-between gap-4 text-xs text-slate-400 border-t border-slate-800/60">
          <div className="flex items-center gap-3">
            <span className="w-2 h-2 rounded-full bg-teal-400" />
            <span>
              Synthesized by <strong>Harimau Core Intelligence Swarm</strong>
            </span>
          </div>
          <div className="flex items-center gap-4 text-[11px] font-mono text-slate-500">
            <span>
              Completed:{" "}
              <b className="text-slate-300" id="masthead-completed">
                {completedTime}
              </b>
            </span>
          </div>
        </div>
      </div>

      {/* 2. Executive At-A-Glance Bento Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3.5" id="bento-metrics">
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/90 space-y-1">
          <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 block">
            GTI Score
          </span>
          <div
            className={`text-2xl font-black font-mono flex items-baseline gap-1 ${gtiScoreColor}`}
            id="bento-gti-score"
          >
            {job.gti_score !== null && job.gti_score !== undefined ? job.gti_score : "--"}{" "}
            <span className="text-xs text-slate-500 font-normal">/100</span>
          </div>
          <span className="text-[10px] font-medium block text-slate-300" id="bento-risk-level">
            {job.risk_level || "Risk Assessed"}
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/90 space-y-1">
          <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 block">
            VT Detections
          </span>
          <div
            className="text-xl font-bold font-mono text-rose-400"
            id="bento-vt-detections"
          >
            {job.rich_intel?.malicious_stats !== undefined
              ? `${job.rich_intel.malicious_stats}/${job.rich_intel.total_stats ?? "--"}`
              : "N/A"}
          </div>
          <span className="text-[10px] text-slate-400 truncate block">
            Security Vendors
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/90 space-y-1">
          <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 block">
            Status
          </span>
          <div
            className="text-xl font-bold font-mono uppercase text-teal-400"
            id="bento-status"
          >
            {(job.status || "COMPLETED").toUpperCase()}
          </div>
          <span className="text-[10px] text-slate-400 block">Execution State</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/90 space-y-1">
          <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 block">
            Entity Type
          </span>
          <div
            className="text-base font-bold text-slate-200 truncate uppercase"
            id="bento-ioc-type"
          >
            {(job.ioc_type || "INDICATOR").toUpperCase()}
          </div>
          <span className="text-[10px] text-slate-400 truncate block">
            Primary Classification
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/90 space-y-1">
          <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 block">
            Graph Entities
          </span>
          <div
            className="text-xl font-bold text-teal-300 font-mono"
            id="bento-graph-count"
          >
            {graphEntityCount} Nodes
          </div>
          <span className="text-[10px] text-slate-400 truncate block">
            Pivots &amp; Relationships
          </span>
        </div>
      </div>

      {/* 3. GTI Assessment & Triage Summary Callout (when rich_intel provides description/summary) */}
      {(job.rich_intel?.gti_description || job.rich_intel?.triage_summary) && (
        <div className="p-4 rounded-xl bg-slate-900/60 border border-teal-500/20 space-y-2">
          <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-wider text-teal-400 font-semibold">
            <span className="w-1.5 h-1.5 rounded-full bg-teal-400" />
            <span>GTI Threat Assessment &amp; Triage Context</span>
          </div>
          {job.rich_intel.gti_description && (
            <p className="text-xs text-slate-300 leading-relaxed">
              {job.rich_intel.gti_description}
            </p>
          )}
          {job.rich_intel.triage_summary && (
            <p className="text-xs text-slate-400 leading-relaxed border-t border-slate-800/80 pt-2">
              <strong className="text-slate-300">Triage Summary: </strong>
              {job.rich_intel.triage_summary}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default DossierMasthead;
