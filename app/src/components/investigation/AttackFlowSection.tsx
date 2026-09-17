"use client";

import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import * as d3 from "d3";
import { graphviz } from "d3-graphviz";
import type { AttackFlowSectionProps } from "@/lib/dossier-types";
import { DecoyInsightBanner } from "./DecoyInsightBanner";
import { TacticalSwimLanes } from "./TacticalSwimLanes";

type AttackFlowViewMode = "unified" | "diagram" | "sequence";
type DotOrientation = "LR" | "TB";

function buildAdaptedDot(rawDot: string | null, ori: DotOrientation): string {
  const baseDot =
    rawDot && rawDot.trim().length > 0
      ? rawDot
      : `digraph AttackFlow {\n  rankdir=${ori};\n  bgcolor="transparent";\n  node [shape=box, style="rounded,filled", fillcolor="#0f172a", color="#334155", fontcolor="#e2e8f0", fontname="monospace"];\n  "Target" [label="No DOT Graph Available"];\n}`;

  let adapted = baseDot;
  if (/rankdir\s*=\s*[A-Za-z]+/i.test(adapted)) {
    adapted = adapted.replace(/rankdir\s*=\s*[A-Za-z]+/gi, `rankdir=${ori}`);
  } else if (/digraph\s+[^{]*\{/i.test(adapted)) {
    adapted = adapted.replace(/(digraph\s+[^{]*\{)/i, `$1\n  rankdir=${ori};`);
  } else {
    adapted = `digraph G {\n  rankdir=${ori};\n${adapted}\n}`;
  }

  adapted = adapted.replace(
    /bgcolor\s*=\s*"[^"]*"/gi,
    'bgcolor="transparent"'
  );
  if (!/bgcolor\s*=/i.test(adapted) && /digraph\s+[^{]*\{/i.test(adapted)) {
    adapted = adapted.replace(
      /(digraph\s+[^{]*\{)/i,
      `$1\n  bgcolor="transparent";`
    );
  }

  return adapted;
}

export function AttackFlowSection({
  job,
  rawDotCode,
  parsedGraph,
  swimLanes,
  onJumpToNode,
  onCopyIoc,
  onExploreInCanvas,
}: AttackFlowSectionProps) {
  const [viewMode, setViewMode] = useState<AttackFlowViewMode>("unified");
  const [orientation, setOrientation] = useState<DotOrientation>(() =>
    rawDotCode?.includes("rankdir=TB") ? "TB" : "LR"
  );
  const [showDotSource, setShowDotSource] = useState<boolean>(false);
  const [isRendering, setIsRendering] = useState<boolean>(true);
  const [renderError, setRenderError] = useState<string | null>(null);

  const diagramContainerRef = useRef<HTMLDivElement>(null);
  const gvInstanceRef = useRef<any>(null);

  // Sync orientation if rawDotCode changes externally
  useEffect(() => {
    if (rawDotCode) {
      setOrientation(rawDotCode.includes("rankdir=TB") ? "TB" : "LR");
    }
  }, [rawDotCode]);

  const decoyCount = useMemo(() => {
    const fromGraph =
      parsedGraph?.nodes?.filter((n) => Boolean(n.isDecoy)).length ?? 0;
    if (fromGraph > 0) return fromGraph;
    const decoyStage = swimLanes?.find(
      (s) => s.category === "decoy" || s.id === "decoy"
    );
    return decoyStage?.nodes?.length ?? 0;
  }, [parsedGraph, swimLanes]);

  const adaptedDotString = useMemo(
    () => buildAdaptedDot(rawDotCode, orientation),
    [rawDotCode, orientation]
  );

  const handleZoomIn = useCallback(() => {
    const gv = gvInstanceRef.current;
    if (!gv || !diagramContainerRef.current) return;
    const zoom = gv.zoomBehavior();
    const svg = d3
      .select(diagramContainerRef.current)
      .select<SVGSVGElement>("svg");
    if (zoom && !svg.empty()) {
      svg.transition().duration(250).call(zoom.scaleBy as any, 1.3);
    }
  }, []);

  const handleZoomOut = useCallback(() => {
    const gv = gvInstanceRef.current;
    if (!gv || !diagramContainerRef.current) return;
    const zoom = gv.zoomBehavior();
    const svg = d3
      .select(diagramContainerRef.current)
      .select<SVGSVGElement>("svg");
    if (zoom && !svg.empty()) {
      svg.transition().duration(250).call(zoom.scaleBy as any, 0.75);
    }
  }, []);

  const handleFitAll = useCallback(() => {
    const gv = gvInstanceRef.current;
    if (!gv || !diagramContainerRef.current) return;
    try {
      gv.resetZoom(d3.transition().duration(400) as any);
    } catch {
      const zoom = gv.zoomBehavior();
      const svg = d3
        .select(diagramContainerRef.current)
        .select<SVGSVGElement>("svg");
      if (zoom && !svg.empty()) {
        svg
          .transition()
          .duration(400)
          .call(zoom.transform as any, d3.zoomIdentity);
      }
    }
  }, []);

  const handleCenterRoot = useCallback(() => {
    const gv = gvInstanceRef.current;
    if (!gv || !diagramContainerRef.current) return;
    const zoom = gv.zoomBehavior();
    const svg = d3
      .select(diagramContainerRef.current)
      .select<SVGSVGElement>("svg");
    if (!zoom || svg.empty()) return;

    const rootId =
      job?.ioc ||
      parsedGraph?.nodes?.find((n) => n.isRoot)?.id ||
      parsedGraph?.nodes?.[0]?.id;

    let targetNodeEl: SVGGElement | null = null;
    svg.selectAll<SVGGElement, unknown>(".node").each(function () {
      const titleText = this.querySelector("title")?.textContent?.trim();
      if (rootId && titleText === rootId) {
        targetNodeEl = this;
      } else if (!targetNodeEl) {
        targetNodeEl = this;
      }
    });

    const graphG = svg.select<SVGGElement>("g.graph").node();
    if (targetNodeEl && graphG) {
      try {
        const bbox = (targetNodeEl as SVGGElement).getBBox();
        const cx = bbox.x + bbox.width / 2;
        const cy = bbox.y + bbox.height / 2;

        const viewBoxAttr = svg.attr("viewBox");
        let centerX = (diagramContainerRef.current.clientWidth || 800) / 2;
        let centerY = (diagramContainerRef.current.clientHeight || 520) / 2;
        if (viewBoxAttr) {
          const parts = viewBoxAttr.split(/\s+/).map(Number);
          if (parts.length === 4 && !parts.some(isNaN)) {
            centerX = parts[0] + parts[2] / 2;
            centerY = parts[1] + parts[3] / 2;
          }
        }

        const origDatum = d3.select(graphG).datum() as any;
        const baseScale = origDatum?.scale || 1;
        const targetScale = Math.max(baseScale * 1.25, 1.1);
        const tx = centerX - cx * targetScale;
        const ty = centerY - cy * targetScale;

        const transform = d3.zoomIdentity.translate(tx, ty).scale(targetScale);
        svg.transition().duration(400).call(zoom.transform as any, transform);
        return;
      } catch {
        // Fallback to resetZoom
      }
    }

    try {
      gv.resetZoom(d3.transition().duration(400) as any);
    } catch {
      // Ignore fallback error
    }
  }, [job?.ioc, parsedGraph?.nodes]);

  const showDiagramStage = viewMode === "unified" || viewMode === "diagram";
  const showSequenceStage = viewMode === "unified" || viewMode === "sequence";

  useEffect(() => {
    if (!showDiagramStage || !diagramContainerRef.current) return;

    const container = diagramContainerRef.current;
    setIsRendering(true);
    setRenderError(null);

    let isCancelled = false;

    try {
      const width = container.clientWidth || 800;
      const height = container.clientHeight || 520;

      const gv = graphviz(container, { useWorker: false })
        .width(width)
        .height(height)
        .fit(true)
        .zoom(true)
        .zoomScaleExtent([0.1, 6])
        .onerror((err: any) => {
          if (!isCancelled) {
            setRenderError(String(err || "Graphviz render error"));
            setIsRendering(false);
          }
        });

      gvInstanceRef.current = gv;

      gv.renderDot(adaptedDotString, () => {
        if (isCancelled) return;
        setIsRendering(false);

        const svg = d3.select(container).select<SVGSVGElement>("svg");
        if (!svg.empty()) {
          svg.attr("width", "100%").attr("height", "100%");

          // Make SVG nodes clickable to inspect in Spatial Canvas
          svg.selectAll<SVGGElement, unknown>(".node").each(function () {
            const nodeSelection = d3.select(this);
            const titleEl = this.querySelector("title");
            const nodeId = titleEl?.textContent?.trim();
            if (nodeId) {
              nodeSelection
                .attr(
                  "title",
                  `Click to inspect [${nodeId}] on Spatial Canvas`
                )
                .style("cursor", "pointer")
                .on("click", (event: any) => {
                  event.stopPropagation();
                  onJumpToNode(nodeId);
                });
            }
          });
        }
      });
    } catch (err: any) {
      if (!isCancelled) {
        setRenderError(
          err instanceof Error ? err.message : "Diagram rendering error"
        );
        setIsRendering(false);
      }
    }

    return () => {
      isCancelled = true;
    };
  }, [adaptedDotString, showDiagramStage, onJumpToNode]);

  return (
    <div className="my-8 rounded-2xl bg-slate-900/95 border border-slate-800 shadow-2xl overflow-hidden not-prose">
      {/* Top Control Bar */}
      <div className="p-4 border-b border-slate-800 bg-slate-950/80 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-teal-500/20 text-teal-400 flex items-center justify-center font-bold shadow-md shadow-teal-500/10">
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
              <circle cx="18" cy="18" r="3" />
              <circle cx="6" cy="6" r="3" />
              <path d="M6 21V9a9 9 0 0 0 9 9" />
            </svg>
          </div>
          <div>
            <h3 className="font-bold text-sm text-white flex items-center gap-2">
              <span>Attack Flow &amp; Behavioral Progression</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-teal-950 text-teal-300 border border-teal-800/60 font-semibold uppercase">
                Report Grounded
              </span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Chronological execution flow, tool transfers, decoy redirects, and
              command-and-control paths
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* Mode Switcher */}
          <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs font-mono">
            <button
              type="button"
              onClick={() => setViewMode("unified")}
              className={`px-2.5 py-1 rounded text-[11px] transition-all border ${
                viewMode === "unified"
                  ? "font-semibold bg-teal-500/20 text-teal-300 border-teal-500/40"
                  : "text-slate-400 hover:text-white border-transparent"
              }`}
            >
              🔗 Unified Flow &amp; Sequence
            </button>
            <button
              type="button"
              onClick={() => setViewMode("diagram")}
              className={`px-2.5 py-1 rounded text-[11px] transition-all border ${
                viewMode === "diagram"
                  ? "font-semibold bg-teal-500/20 text-teal-300 border-teal-500/40"
                  : "text-slate-400 hover:text-white border-transparent"
              }`}
            >
              🗺️ Flow Diagram Only
            </button>
            <button
              type="button"
              onClick={() => setViewMode("sequence")}
              className={`px-2.5 py-1 rounded text-[11px] transition-all border ${
                viewMode === "sequence"
                  ? "font-semibold bg-teal-500/20 text-teal-300 border-teal-500/40"
                  : "text-slate-400 hover:text-white border-transparent"
              }`}
            >
              📋 Telemetry Sequence
            </button>
          </div>

          {/* Orientation Switcher */}
          <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs font-mono">
            <span className="text-[10px] text-slate-500 px-1 font-sans">
              Layout:
            </span>
            <button
              type="button"
              onClick={() => setOrientation("LR")}
              className={`px-2 py-1 rounded text-[11px] transition-all border ${
                orientation === "LR"
                  ? "font-bold bg-teal-500/20 text-teal-300 border-teal-500/40"
                  : "text-slate-400 hover:text-white border-transparent"
              }`}
            >
              ↔ LR
            </button>
            <button
              type="button"
              onClick={() => setOrientation("TB")}
              className={`px-2 py-1 rounded text-[11px] transition-all border ${
                orientation === "TB"
                  ? "font-bold bg-teal-500/20 text-teal-300 border-teal-500/40"
                  : "text-slate-400 hover:text-white border-transparent"
              }`}
            >
              ↕ TB
            </button>
          </div>

          {/* Explore in Spatial Canvas Button */}
          <button
            type="button"
            onClick={() => onExploreInCanvas?.()}
            className="px-3 py-1.5 rounded-lg bg-teal-500/20 hover:bg-teal-500/30 text-teal-200 border border-teal-500/40 font-semibold flex items-center gap-1.5 transition-all shadow-sm"
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
              <rect x="16" y="16" width="6" height="6" rx="1" />
              <rect x="2" y="16" width="6" height="6" rx="1" />
              <rect x="9" y="2" width="6" height="6" rx="1" />
              <path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3" />
              <path d="M12 12V8" />
            </svg>
            <span>Explore in Spatial Canvas ➔</span>
          </button>

          {/* View DOT Toggle Button */}
          <button
            type="button"
            onClick={() => setShowDotSource((prev) => !prev)}
            className={`px-2.5 py-1.5 rounded-lg font-mono text-[11px] flex items-center gap-1 transition-colors border ${
              showDotSource
                ? "bg-teal-500/20 text-teal-300 border-teal-500/40"
                : "bg-slate-800 hover:bg-slate-700 text-slate-300 border-transparent"
            }`}
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
              <polyline points="16 18 22 12 16 6" />
              <polyline points="8 6 2 12 8 18" />
            </svg>
            <span>View DOT</span>
          </button>
        </div>
      </div>

      {/* DIAGRAM STAGE: Graphviz SVG Viewport */}
      {showDiagramStage && (
        <div className="relative w-full h-[520px] lg:h-[560px] bg-slate-950/90 overflow-hidden cursor-grab active:cursor-grabbing flex items-center justify-center border-b border-slate-800/80">
          {isRendering && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/60 text-xs text-slate-400 font-mono gap-2 pointer-events-none">
              <span className="w-2 h-2 rounded-full bg-teal-400 animate-ping" />
              <span>Rendering Attack Flow Vector...</span>
            </div>
          )}

          {renderError && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/80 text-xs text-rose-400 font-mono px-4 text-center">
              <span>
                Diagram rendering fallback ({renderError}). Click &quot;Explore
                in Spatial Canvas&quot; above to inspect graph entities.
              </span>
            </div>
          )}

          <div
            ref={diagramContainerRef}
            className="w-full h-full flex items-center justify-center"
          />

          {/* Floating Bottom-Right Zoom Controls */}
          <div className="absolute bottom-3 right-3 flex items-center gap-1 bg-slate-900/80 backdrop-blur-md p-1 rounded-lg border border-slate-800 z-10">
            <button
              type="button"
              onClick={handleZoomIn}
              title="Zoom In"
              className="w-7 h-7 rounded flex items-center justify-center text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
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
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
            <button
              type="button"
              onClick={handleZoomOut}
              title="Zoom Out"
              className="w-7 h-7 rounded flex items-center justify-center text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
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
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
            <button
              type="button"
              onClick={handleCenterRoot}
              title="Center on Root Node"
              className="px-2 h-7 rounded flex items-center justify-center text-xs text-teal-300 bg-teal-500/10 hover:bg-teal-500/20 transition-colors font-mono gap-1"
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
                <circle cx="12" cy="12" r="10" />
                <line x1="22" y1="12" x2="18" y2="12" />
                <line x1="6" y1="12" x2="2" y2="12" />
                <line x1="12" y1="6" x2="12" y2="2" />
                <line x1="12" y1="22" x2="12" y2="18" />
              </svg>
              <span>Center</span>
            </button>
            <button
              type="button"
              onClick={handleFitAll}
              title="Fit Entire Graph"
              className="px-2 h-7 rounded flex items-center justify-center text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition-colors font-mono gap-1"
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
                <polyline points="15 3 21 3 21 9" />
                <polyline points="9 21 3 21 3 15" />
                <line x1="21" y1="3" x2="14" y2="10" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
              <span>Fit All</span>
            </button>
          </div>
        </div>
      )}

      {/* TACTICAL SEQUENCE STAGE: Observed Telemetry & Evasion Insights */}
      {showSequenceStage && (
        <div className="p-6 bg-slate-950/60 space-y-5">
          <DecoyInsightBanner decoyCount={decoyCount} />
          <TacticalSwimLanes
            activeStages={swimLanes}
            onJumpToNode={onJumpToNode}
            onCopyIoc={onCopyIoc}
          />
        </div>
      )}

      {/* Collapsible DOT Source View */}
      {showDotSource && (
        <div className="p-4 bg-slate-950 border-t border-slate-800 max-h-72 overflow-y-auto font-mono text-xs text-slate-400">
          <pre className="whitespace-pre-wrap">
            {rawDotCode || "No DOT source available."}
          </pre>
        </div>
      )}
    </div>
  );
}

export default AttackFlowSection;
