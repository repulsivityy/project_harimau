"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useRef, useMemo, useCallback, ChangeEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type ReactFlowInstance,
  type Node,
  type Edge,
} from "@xyflow/react";
import * as d3 from "d3";
import {
  isTerminalInvestigationStatus,
  reconcileTerminalInvestigationEvent,
  type InvestigationStreamData,
  type TerminalInvestigationStatus,
} from "@/lib/investigation-stream";
import {
  deriveSwimLanes,
  parseDossierReport,
} from "@/lib/dossier-utils";
import type { DossierJob } from "@/lib/dossier-types";
import { DossierMasthead } from "@/components/investigation/DossierMasthead";
import { SpecialistReportsGrid } from "@/components/investigation/SpecialistReportsGrid";
import { DossierCompanionRail } from "@/components/investigation/DossierCompanionRail";
import { AttackFlowSection } from "@/components/investigation/AttackFlowSection";
import { AppendixIocTable } from "@/components/investigation/AppendixIocTable";
import "@xyflow/react/dist/style.css";

// Markdown renderer for prose sections in Threat Dossier
const ThreatDossierMarkdown = ({ content }: { content: string }) => {
  if (!content || !content.trim()) return null;
  return (
    <div className="prose prose-invert max-w-none text-slate-300 text-sm leading-relaxed space-y-4">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ ...props }) => (
            <h1 className="text-2xl font-bold text-white mt-6 mb-3 tracking-tight" {...props} />
          ),
          h2: ({ ...props }) => (
            <h2 className="text-xl font-bold text-teal-300 mt-6 mb-3 border-b border-slate-800 pb-2" {...props} />
          ),
          h3: ({ ...props }) => (
            <h3 className="text-base font-bold text-slate-100 mt-5 mb-2" {...props} />
          ),
          p: ({ ...props }) => <p className="mb-3 leading-relaxed text-slate-300" {...props} />,
          ul: ({ ...props }) => (
            <ul className="list-disc pl-5 mb-4 space-y-1.5 marker:text-teal-400" {...props} />
          ),
          ol: ({ ...props }) => (
            <ol className="list-decimal pl-5 mb-4 space-y-1.5 marker:text-teal-400" {...props} />
          ),
          table: ({ ...props }) => (
            <div className="overflow-x-auto my-4 rounded-xl border border-slate-800 bg-slate-900/60">
              <table className="w-full text-left border-collapse text-xs" {...props} />
            </div>
          ),
          thead: ({ ...props }) => (
            <thead className="bg-slate-950/80 text-slate-400 font-mono uppercase text-[10px]" {...props} />
          ),
          th: ({ ...props }) => (
            <th className="py-2.5 px-4 font-semibold border-b border-slate-800" {...props} />
          ),
          td: ({ ...props }) => (
            <td className="py-2.5 px-4 border-b border-slate-800/60 text-slate-300" {...props} />
          ),
          strong: ({ ...props }) => <strong className="font-semibold text-white" {...props} />,
          code: ({ className, children, ...rest }) => {
            const isInline = !className;
            return isInline ? (
              <code
                className="bg-slate-900 text-teal-300 px-1.5 py-0.5 rounded text-xs font-mono border border-slate-800"
                {...rest}
              >
                {children}
              </code>
            ) : (
              <pre className="bg-slate-950 p-4 rounded-xl border border-slate-800 overflow-x-auto text-xs font-mono text-slate-300 my-3">
                <code className={className} {...rest}>
                  {children}
                </code>
              </pre>
            );
          },
          blockquote: ({ ...props }) => (
            <blockquote
              className="border-l-4 border-teal-500/60 bg-slate-900/50 py-2.5 px-4 my-3 rounded-r-lg italic text-slate-300"
              {...props}
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

const IP_REGEX = /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/;
const HASH_REGEX = /^[a-fA-F0-9]{32,64}$/;

interface BackendNode {
  id: string;
  label: string;
  color?: string;
  entityType: string;
  size: number;
  title?: string;
  isRoot?: boolean;
  isMalicious?: boolean;
  inReport?: boolean;
  threatScore?: number | null;
  verdict?: string | null;
  vendorDetections?: string | null;
}

interface BackendEdge {
  source: string;
  target: string;
  label: string;
}

interface GraphData {
  nodes: BackendNode[];
  edges: BackendEdge[];
}

interface CustomNodeData extends Record<string, unknown> {
  label?: string;
  title?: string;
  isRoot?: boolean;
  isMalicious?: boolean;
  threatScore?: number;
  rawNode?: BackendNode;
}

interface CustomNodeProps {
  data: CustomNodeData;
  style?: { width?: number; height?: number };
}

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  x: number;
  y: number;
  radius: number;
  fx?: number;
  fy?: number;
}

interface TransparencyEntry {
  timestamp?: string;
  tool?: string;
  agent?: string;
}

const CustomNode = ({ data, style }: CustomNodeProps) => {
  let icon = "hub";
  const label = data.label || "";
  const title = data.title || "";

  if (IP_REGEX.test(label)) icon = "router";
  else if (label.startsWith("http")) icon = "link";
  else if (HASH_REGEX.test(label)) icon = "fingerprint";
  else if (label.includes(".")) icon = "language";

  if (title.includes("Specialist") || label.includes("specialist")) icon = "manage_search";
  if (data.isRoot) icon = "my_location";

  const isMalicious = data.isMalicious;
  const isRoot = data.isRoot;
  const nodeSize = style?.width || 48;
  const iconSize = Math.max(14, nodeSize * 0.4);

  const color = isRoot ? "#00f7ff" : isMalicious ? "#f43f5e" : "#94a3b8";

  return (
    <div className="relative group flex flex-col items-center">
      <Handle type="target" position={Position.Top} className="!opacity-0" style={{ left: "50%", top: "50%" }} />
      <Handle type="source" position={Position.Bottom} className="!opacity-0" style={{ left: "50%", top: "50%" }} />

      {isMalicious && (
        <div
          className="absolute -top-2 -right-2 bg-rose-500 text-white p-0.5 rounded-full z-10 flex items-center justify-center"
          style={{ borderRadius: "50%", width: "16px", height: "16px" }}
        >
          <span className="material-symbols-outlined text-[10px]">warning</span>
        </div>
      )}

      <div
        className="transition-all duration-300 flex items-center justify-center rounded-full"
        style={{
          width: nodeSize,
          height: nodeSize,
          background: "#0f172a",
          border: `2px solid ${color}`,
          boxShadow: `0 0 15px ${color}33`,
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: iconSize, color }}>
          {icon}
        </span>
      </div>

      <div className="mt-2 text-[10px] font-mono uppercase tracking-wider text-slate-300 whitespace-nowrap overflow-hidden text-ellipsis max-w-[160px] text-center">
        {label}
      </div>
    </div>
  );
};

const nodeTypes = { custom: CustomNode };

function getSmartLabel(node: BackendNode): string {
  const { label, entityType, id } = node;
  if (node.isRoot) return label;

  switch (entityType) {
    case "file": {
      const parenMatch = label.match(/\(([^)]+)\)/);
      if (parenMatch) return parenMatch[1];
      return id.length > 16 ? `${id.slice(0, 8)}...${id.slice(-6)}` : id;
    }
    case "url": {
      try {
        const url = new URL(label.startsWith("http") ? label : `https://${label}`);
        const path = url.pathname.length > 20 ? url.pathname.slice(0, 18) + "..." : url.pathname;
        return `${url.hostname}${path !== "/" ? path : ""}`;
      } catch {
        return label.length > 40 ? label.slice(0, 38) + "..." : label;
      }
    }
    case "domain":
    case "ip_address":
      return label;
    default:
      return label.length > 30 ? label.slice(0, 28) + "..." : label;
  }
}

export default function InvestigatePage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();

  const [activeView, setActiveView] = useState<"dossier" | "canvas">("dossier");
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<CustomNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [job, setJob] = useState<DossierJob | null>(null);
  const [jobStatus, setJobStatus] = useState<string>("running");
  const [progress, setProgress] = useState<number>(0);
  const [statusMessage, setStatusMessage] = useState<string>("Initializing secure channel...");
  const [activityLog, setActivityLog] = useState<string[]>([]);
  const [recentJobs, setRecentJobs] = useState<DossierJob[]>([]);
  const [showAgentDrawer, setShowAgentDrawer] = useState(false);
  const [copiedToast, setCopiedToast] = useState<string | null>(null);
  const [jumpNotice, setJumpNotice] = useState<string | null>(null);
  const [pendingJumpNodeId, setPendingJumpNodeId] = useState<string | null>(null);

  const reactFlowRef = useRef<ReactFlowInstance<Node<CustomNodeData>, Edge> | null>(null);
  const simulationRef = useRef<d3.Simulation<SimNode, undefined> | null>(null);
  const terminalStatusRef = useRef<TerminalInvestigationStatus | null>(null);
  const terminalSnapshotRef = useRef<{ subtasks?: unknown[]; transparencyLog?: unknown[] } | null>(null);

  const [graphFilters, setGraphFilters] = useState({
    reportOnly: true,
    maliciousOnly: false,
    types: { file: true, domain: true, ip_address: true, url: true, process: true, entity: true } as Record<string, boolean>,
  });
  const rawGraphRef = useRef<GraphData | null>(null);
  const [rawGraphData, setRawGraphData] = useState<GraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<BackendNode | null>(null);

  const lastJobSignatureRef = useRef<string>("");
  const lastGraphSignatureRef = useRef<string>("");
  const lastLogSignatureRef = useRef<string>("");
  const lastPendingJumpRef = useRef<string | null>(null);
  const jumpFilterAttemptsRef = useRef<number>(0);
  const jumpFiltersRelaxedNoticeRef = useRef<boolean>(false);
  const pendingJumpNodeIdRef = useRef<string | null>(null);

  // Switching investigations (e.g. via the Case Switcher) keeps this page
  // mounted with a new `id` — nothing resets automatically, so the previous
  // investigation's job/graph/canvas state would otherwise leak into the new
  // one until fresh data happens to overwrite it. Reset synchronously during
  // render (React's documented pattern for resetting state on a changed prop)
  // rather than in an effect, so the stale state is never even briefly shown.
  const [prevId, setPrevId] = useState(id);
  if (id !== prevId) {
    setPrevId(id);
    setJob(null);
    setJobStatus("running");
    setProgress(0);
    setStatusMessage("Initializing secure channel...");
    setActivityLog([]);
    setRawGraphData(null);
    rawGraphRef.current = null;
    setNodes([]);
    setEdges([]);
    setSelectedNode(null);
    setActiveView("dossier");
    setPendingJumpNodeId(null);
    lastJobSignatureRef.current = "";
    lastGraphSignatureRef.current = "";
    lastLogSignatureRef.current = "";
    lastPendingJumpRef.current = null;
    jumpFilterAttemptsRef.current = 0;
    jumpFiltersRelaxedNoticeRef.current = false;
    pendingJumpNodeIdRef.current = null;
  }

  // <ReactFlow> only mounts in the "canvas" view (see the activeView ternary
  // below); switching away unmounts it without React Flow itself clearing
  // reactFlowRef.current, so the ref would otherwise keep pointing at a
  // disposed instance for any code that later checks `if (reactFlowRef.current)`.
  useEffect(() => {
    if (activeView !== "canvas") {
      reactFlowRef.current = null;
    }
  }, [activeView]);

  const finalReport = job?.final_report || "";
  const jobIoc = job?.ioc || "";
  const jobGtiScore = job?.gti_score;

  // job.graph/investigation_graph get a new object identity on every poll
  // (fresh JSON.parse each time), even when unchanged, so depending on them
  // directly would defeat jobSig's content-gating of setJob. Derive a stable
  // primitive signature instead — cheap to recompute, only changes identity
  // when the fallback graph's shape actually changes.
  const jobGraphSig = useMemo(() => {
    const g = job?.graph || job?.investigation_graph;
    return g ? `${g.nodes?.length ?? 0}:${g.edges?.length ?? 0}` : "";
  }, [job?.graph, job?.investigation_graph]);

  // Parse Dossier Report & Swim Lanes from job.final_report
  const parsedDossier = useMemo(() => {
    return parseDossierReport(
      finalReport,
      job || undefined,
      rawGraphData || job?.graph || job?.investigation_graph
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finalReport, jobIoc, jobGtiScore, rawGraphData, jobGraphSig]);

  const swimLanes = useMemo(() => {
    return deriveSwimLanes(
      parsedDossier.parsedDotGraph,
      jobIoc,
      job || undefined
    );
  }, [parsedDossier.parsedDotGraph, jobIoc, job]);

  // Same fallback chain as parseDossierReport's rawGraphData argument above —
  // when the /graph endpoint hasn't returned data yet (or is failing), fall
  // back to whatever graph is embedded on the job record itself, so the
  // canvas, entity count, and jump-to-node lookups stay consistent with
  // what the Appendix IOC table (fed by the same fallback) is showing.
  // Keyed on jobGraphSig (not job?.graph/job?.investigation_graph directly)
  // so this only gets a new identity when the fallback graph's shape
  // actually changes, not on every poll.
  const effectiveGraphData = useMemo(() => {
    if (rawGraphData) return rawGraphData;
    const fallback = job?.graph || job?.investigation_graph;
    return fallback ? (fallback as GraphData) : null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawGraphData, jobGraphSig]);

  const effectiveGraphRef = useRef<GraphData | null>(null);
  useEffect(() => {
    effectiveGraphRef.current = effectiveGraphData;
  }, [effectiveGraphData]);

  const graphEntityCount = useMemo(() => {
    const rawCount = effectiveGraphData?.nodes?.length || 0;
    const dotCount = parsedDossier.parsedDotGraph.nodes.length;
    return Math.max(rawCount, dotCount);
  }, [effectiveGraphData?.nodes?.length, parsedDossier.parsedDotGraph.nodes.length]);

  const handleCopyIoc = useCallback((value: string) => {
    if (!value) return;
    navigator.clipboard.writeText(value).catch(() => {});
    setCopiedToast(value);
    setTimeout(() => {
      setCopiedToast((prev) => (prev === value ? null : prev));
    }, 2000);
  }, []);

  const handleJumpToNode = useCallback((nodeId: string) => {
    if (!nodeId) return;
    setActiveView("canvas");
    setPendingJumpNodeId(nodeId);
  }, []);

  const showJumpNotice = useCallback((message: string) => {
    setJumpNotice(message);
    setTimeout(() => {
      setJumpNotice((prev) => (prev === message ? null : prev));
    }, 3500);
  }, []);

  // Build / rebuild ReactFlow graph nodes whenever rawGraphRef, parsedDotGraph, or filters change
  const rebuildSpatialGraph = useCallback(
    (backendGraph: GraphData | null) => {
      const dotNodes = parsedDossier.parsedDotGraph.nodes;
      const dotEdges = parsedDossier.parsedDotGraph.edges;

      const mergedNodesMap = new Map<string, BackendNode>();

      if (backendGraph?.nodes) {
        backendGraph.nodes.forEach((n) => {
          mergedNodesMap.set(n.id, n);
        });
      }

      dotNodes.forEach((dn) => {
        if (!mergedNodesMap.has(dn.id)) {
          mergedNodesMap.set(dn.id, {
            id: dn.id,
            label: dn.label || dn.id,
            entityType: dn.entityType || "entity",
            size: dn.isRoot ? 30 : 22,
            isRoot: dn.isRoot,
            isMalicious: dn.isMalicious,
            inReport: true,
            threatScore: dn.threatScore ?? undefined,
            verdict: dn.verdict,
          });
        }
      });

      const allNodes = Array.from(mergedNodesMap.values());
      if (allNodes.length === 0) {
        // A genuinely empty merged graph must still clear the canvas —
        // otherwise the previous investigation's (or previous filter
        // state's) nodes/edges stay rendered indefinitely.
        if (simulationRef.current) {
          simulationRef.current.stop();
          simulationRef.current = null;
        }
        setNodes([]);
        setEdges([]);
        return;
      }

      const allEdges: BackendEdge[] = [...(backendGraph?.edges || [])];
      dotEdges.forEach((de) => {
        const exists = allEdges.some((e) => e.source === de.source && e.target === de.target);
        if (!exists) {
          allEdges.push({ source: de.source, target: de.target, label: de.label });
        }
      });

      const visibleNodes = allNodes.filter((n) => {
        if (n.isRoot) return true;
        if (graphFilters.reportOnly && !n.inReport) return false;
        if (graphFilters.maliciousOnly && !n.isMalicious) return false;
        const typeAllowed = graphFilters.types[n.entityType] ?? true;
        if (!typeAllowed) return false;
        return true;
      });

      const visibleIds = new Set(visibleNodes.map((n) => n.id));
      const visibleEdges = allEdges.filter(
        (e) => visibleIds.has(e.source) && visibleIds.has(e.target)
      );

      if (simulationRef.current) {
        simulationRef.current.stop();
        simulationRef.current = null;
      }

      const simNodes: SimNode[] = visibleNodes.map((n, idx) => {
        const isRoot = n.isRoot === true;
        const angle = (idx / Math.max(1, visibleNodes.length)) * 2 * Math.PI;
        return {
          id: n.id,
          x: isRoot ? 0 : Math.cos(angle) * 220,
          y: isRoot ? 0 : Math.sin(angle) * 220,
          radius: n.size || 24,
          fx: isRoot ? 0 : undefined,
          fy: isRoot ? 0 : undefined,
        };
      });

      const simEdgeData = visibleEdges.map((e) => ({ source: e.source, target: e.target }));
      const simNodeMap = new Map<string, SimNode>(simNodes.map((n) => [n.id, n]));

      const simulation = d3
        .forceSimulation<SimNode>(simNodes)
        .force("link", d3.forceLink<SimNode, d3.SimulationLinkDatum<SimNode>>(simEdgeData).id((d) => d.id).distance(180).strength(0.15))
        .force("charge", d3.forceManyBody().strength(-700).distanceMax(600))
        .force("collide", d3.forceCollide<SimNode>().radius((d) => d.radius + 20).strength(0.9))
        .force("x", d3.forceX(0).strength(0.05))
        .force("y", d3.forceY(0).strength(0.05));

      simulation.stop();
      for (let i = 0; i < 120; i++) simulation.tick();

      setNodes(
        visibleNodes.map((n) => {
          const sim = simNodeMap.get(n.id) || { x: 0, y: 0 };
          const size = n.size || 24;
          return {
            id: n.id,
            type: "custom",
            position: { x: sim.x, y: sim.y },
            data: {
              label: getSmartLabel(n),
              title: n.title,
              isRoot: n.isRoot,
              isMalicious: n.isMalicious,
              threatScore: n.threatScore ?? undefined,
              rawNode: n,
            },
            style: {
              background: "transparent",
              border: "none",
              padding: 0,
              width: size * 2,
              height: size * 2,
              overflow: "visible",
            },
          };
        })
      );

      setEdges(
        visibleEdges.map((e, index) => ({
          id: `e-${index}-${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          label: e.label,
          animated: true,
          style: { stroke: "#38bdf8", strokeWidth: 1.5, opacity: 0.65 },
          labelStyle: { fill: "#94a3b8", fontSize: 10, fontFamily: "monospace" },
        }))
      );
    },
    [parsedDossier.parsedDotGraph, graphFilters, setNodes, setEdges]
  );

  // Mirror the latest `rebuildSpatialGraph` into a ref so the long-lived
  // SSE/polling effect can invoke it without taking a dependency on its
  // (intentionally unstable) identity.
  const rebuildRef = useRef(rebuildSpatialGraph);
  useEffect(() => {
    rebuildRef.current = rebuildSpatialGraph;
  }, [rebuildSpatialGraph]);

  // Execute pending node focus when switching to canvas
  useEffect(() => {
    if (activeView !== "canvas" || !pendingJumpNodeId) {
      lastPendingJumpRef.current = null;
      jumpFilterAttemptsRef.current = 0;
      jumpFiltersRelaxedNoticeRef.current = false;
      return;
    }

    if (pendingJumpNodeId !== lastPendingJumpRef.current) {
      lastPendingJumpRef.current = pendingJumpNodeId;
      jumpFilterAttemptsRef.current = 0;
      jumpFiltersRelaxedNoticeRef.current = false;
    }

    const targetLower = pendingJumpNodeId.toLowerCase();
    const targetRfNode = nodes.find(
      (n) => n.id === pendingJumpNodeId || n.id.toLowerCase() === targetLower
    );

    if (targetRfNode) {
      const raw =
        targetRfNode.data?.rawNode ||
        effectiveGraphRef.current?.nodes.find(
          (rn) => rn.id === targetRfNode.id || rn.id.toLowerCase() === targetLower
        );
      if (raw) setSelectedNode(raw);

      setTimeout(() => {
        if (reactFlowRef.current) {
          reactFlowRef.current.setCenter(
            targetRfNode.position.x,
            targetRfNode.position.y,
            { zoom: 1.35, duration: 500 }
          );
        }
      }, 100);
      setPendingJumpNodeId(null);
      lastPendingJumpRef.current = null;
      jumpFilterAttemptsRef.current = 0;
      return;
    }

    // Target node was not found in visible `nodes`. Check full unfiltered node sets.
    const rawMatch = effectiveGraphRef.current?.nodes?.find(
      (rn) => rn.id === pendingJumpNodeId || rn.id.toLowerCase() === targetLower
    );
    const dotMatch = !rawMatch
      ? parsedDossier.parsedDotGraph.nodes.find(
          (dn) => dn.id === pendingJumpNodeId || dn.id.toLowerCase() === targetLower
        )
      : null;

    const fullNode = rawMatch || dotMatch;

    if (fullNode) {
      const entityType = fullNode.entityType || "entity";
      const isFilteredOut =
        !fullNode.isRoot &&
        ((graphFilters.reportOnly && !("inReport" in fullNode && fullNode.inReport)) ||
          (graphFilters.maliciousOnly && !fullNode.isMalicious) ||
          graphFilters.types[entityType] === false);

      if (isFilteredOut) {
        if (!jumpFiltersRelaxedNoticeRef.current) {
          jumpFiltersRelaxedNoticeRef.current = true;
          showJumpNotice(`Adjusted graph filters to reveal "${pendingJumpNodeId}"`);
        }
        setGraphFilters((prev) => ({
          ...prev,
          reportOnly: false,
          maliciousOnly: false,
          types: {
            ...prev.types,
            [entityType]: true,
          },
        }));
        // Keep pendingJumpNodeId set until graph rebuilds with relaxed filters
        return;
      }

      // If filters are already relaxed, give rebuildSpatialGraph up to 3 render passes to populate `nodes`
      jumpFilterAttemptsRef.current += 1;
      if (jumpFilterAttemptsRef.current > 3) {
        const raw: BackendNode =
          "size" in fullNode
            ? (fullNode as BackendNode)
            : {
                id: fullNode.id,
                label: fullNode.label || fullNode.id,
                entityType,
                size: fullNode.isRoot ? 30 : 22,
                isRoot: fullNode.isRoot,
                isMalicious: fullNode.isMalicious,
                threatScore: fullNode.threatScore ?? undefined,
                verdict: fullNode.verdict,
              };
        setSelectedNode(raw);
        showJumpNotice(`"${pendingJumpNodeId}" isn't rendered on the canvas — showing details in the inspector only.`);
        setPendingJumpNodeId(null);
        lastPendingJumpRef.current = null;
        jumpFilterAttemptsRef.current = 0;
      }
      return;
    }

    // If the node truly does not exist in either effectiveGraphRef.current or parsedDotGraph.nodes,
    // synthesize a temporary selected node for the inspector.
    setSelectedNode({
      id: pendingJumpNodeId,
      label: pendingJumpNodeId,
      entityType: "entity",
      size: 24,
      threatScore: undefined,
    });
    showJumpNotice(`"${pendingJumpNodeId}" was not found in this investigation's graph.`);
    setPendingJumpNodeId(null);
    lastPendingJumpRef.current = null;
    jumpFilterAttemptsRef.current = 0;
  }, [
    activeView,
    pendingJumpNodeId,
    nodes,
    graphFilters,
    parsedDossier.parsedDotGraph,
    showJumpNotice,
  ]);

  // Mirror pendingJumpNodeId into a ref so the watchdog below can check the
  // latest value from inside a plain setTimeout without doing side effects
  // inside a setState updater (updaters run during React's render phase and
  // are double-invoked under StrictMode).
  useEffect(() => {
    pendingJumpNodeIdRef.current = pendingJumpNodeId;
  }, [pendingJumpNodeId]);

  // Mirror parsedDossier.parsedDotGraph into a ref so the watchdog's timer
  // doesn't restart every time the dossier recomputes (e.g. while specialist
  // markdown is still streaming in) — a restart on every poll could starve
  // the watchdog for the entire duration of a live investigation.
  const parsedDotGraphRef = useRef(parsedDossier.parsedDotGraph);
  useEffect(() => {
    parsedDotGraphRef.current = parsedDossier.parsedDotGraph;
  }, [parsedDossier.parsedDotGraph]);

  // Watchdog: guarantee a jump request always resolves even if rebuildSpatialGraph
  // never repopulates `nodes` (e.g. an empty merged graph keeps the effect above
  // from re-firing enough times to hit its own attempt-count escape hatch).
  useEffect(() => {
    if (activeView !== "canvas" || !pendingJumpNodeId) return;
    const targetId = pendingJumpNodeId;
    const timer = setTimeout(() => {
      if (pendingJumpNodeIdRef.current !== targetId) return;

      const targetLower = targetId.toLowerCase();
      const fallback =
        effectiveGraphRef.current?.nodes?.find(
          (n) => n.id === targetId || n.id.toLowerCase() === targetLower
        ) ||
        parsedDotGraphRef.current.nodes.find(
          (n) => n.id === targetId || n.id.toLowerCase() === targetLower
        );
      setSelectedNode(
        fallback
          ? "size" in fallback
            ? (fallback as BackendNode)
            : {
                id: fallback.id,
                label: fallback.label || fallback.id,
                entityType: fallback.entityType || "entity",
                size: fallback.isRoot ? 30 : 22,
                isRoot: fallback.isRoot,
                isMalicious: fallback.isMalicious,
                threatScore: fallback.threatScore ?? undefined,
                verdict: fallback.verdict,
              }
          : { id: targetId, label: targetId, entityType: "entity", size: 24, threatScore: undefined }
      );
      showJumpNotice(`Couldn't focus "${targetId}" on the canvas — showing details in the inspector only.`);
      lastPendingJumpRef.current = null;
      jumpFilterAttemptsRef.current = 0;
      jumpFiltersRelaxedNoticeRef.current = false;
      setPendingJumpNodeId(null);
    }, 4000);
    return () => clearTimeout(timer);
  }, [activeView, pendingJumpNodeId, showJumpNotice]);

  // Re-render the spatial graph whenever the parsed DOT graph, raw graph data, or filters change.
  useEffect(() => {
    rebuildSpatialGraph(effectiveGraphData);
  }, [rebuildSpatialGraph, effectiveGraphData]);

  useEffect(() => {
    if (!id) return;

    fetch("/api/investigations")
      .then((r) => r.json())
      .then((jobs) => setRecentJobs(Array.isArray(jobs) ? jobs : []))
      .catch(() => setRecentJobs([]));

    let pollInterval: ReturnType<typeof setInterval> | null = null;
    let eventSource: EventSource | null = null;
    terminalStatusRef.current = null;
    terminalSnapshotRef.current = null;

    const formatTransparencyLog = (entries: unknown[]) =>
      entries
        .slice(-25)
        .reverse()
        .map((rawEntry) => {
          const entry = rawEntry as TransparencyEntry;
          const time = entry?.timestamp
            ? new Date(entry.timestamp).toLocaleTimeString()
            : new Date().toLocaleTimeString();
          const icon = entry?.tool ? "TOOL" : "THOUGHT";
          return `[${time}] ${icon} ${entry?.agent || "system"}: ${
            entry?.tool ? `EXECUTING_${entry.tool}` : "ANALYZING_DATA"
          }`;
        });

    const applyTerminalUpdate = (
      status: TerminalInvestigationStatus,
      data: InvestigationStreamData,
      eventType: string
    ) => {
      const update = reconcileTerminalInvestigationEvent(eventType, data);
      if (!update) return;

      terminalStatusRef.current = status;
      terminalSnapshotRef.current = {
        subtasks: update.subtasks,
        transparencyLog: update.transparencyLog,
      };
      setJobStatus(status);
      setProgress(update.progress);
      setStatusMessage(update.message);
      setJob((previous) =>
        previous
          ? {
              ...previous,
              status,
              ...(update.subtasks ? { subtasks: update.subtasks as DossierJob["subtasks"] } : {}),
            }
          : previous
      );
      if (update.transparencyLog) setActivityLog(formatTransparencyLog(update.transparencyLog));
      if (pollInterval) clearInterval(pollInterval);
      eventSource?.close();
    };

    const refetch = async (): Promise<string> => {
      try {
        const [graphRes, jobRes] = await Promise.all([
          fetch(`/api/investigations/${id}/graph`),
          fetch(`/api/investigations/${id}`),
        ]);

        if (!jobRes.ok) throw new Error("Failed to fetch job details");

        const jobData: DossierJob = await jobRes.json();
        // Normalized once here so every downstream comparison (including the
        // render's case-sensitive `jobStatus === "failed"` checks) stays
        // correct even if the backend ever returns non-lowercase status.
        const fetchedStatus = (jobData.status ?? "running").toLowerCase();
        const terminalFromRest =
          !terminalStatusRef.current && isTerminalInvestigationStatus(fetchedStatus);
        const effectiveStatus = terminalStatusRef.current ?? fetchedStatus;

        const hasTerminalReconciliation = Boolean(
          terminalStatusRef.current && !isTerminalInvestigationStatus(fetchedStatus)
        );
        const resolvedJob: DossierJob = hasTerminalReconciliation
          ? {
              ...jobData,
              status: terminalStatusRef.current!,
              ...(terminalSnapshotRef.current?.subtasks
                ? { subtasks: terminalSnapshotRef.current.subtasks as DossierJob["subtasks"] }
                : {}),
              ...(terminalSnapshotRef.current?.transparencyLog
                ? { transparency_log: terminalSnapshotRef.current.transparencyLog }
                : {}),
            }
          : jobData;

        const sr =
          resolvedJob.specialist_reports ||
          resolvedJob.specialist_results ||
          resolvedJob.metadata?.specialist_results ||
          {};
        // Resolve each specialist as one whole object (matching
        // SpecialistReportsGrid's `sr.malware_specialist || sr.malware`
        // convention) rather than per-field, so a signature never blends
        // fields from two different report objects.
        const malwareReport = sr.malware_specialist || sr.malware;
        const infraReport = sr.infrastructure_specialist || sr.infrastructure;
        const specialistContentSig = [malwareReport, infraReport].map((report) =>
          report
            ? [
                report.verdict,
                (report.markdown_report || "").length,
                (report.summary || "").length,
              ]
            : null
        );

        const jobSig = JSON.stringify({
          status: effectiveStatus,
          reportLen: resolvedJob.final_report?.length ?? 0,
          reportHash:
            (resolvedJob.final_report?.slice(0, 120) ?? "") +
            (resolvedJob.final_report?.slice(-120) ?? ""),
          subtaskStatuses: (resolvedJob.subtasks || []).map(
            (t) => `${t.agent ?? ""}:${t.status ?? ""}:${t.timestamp ?? ""}:${(t.task ?? "").length}`
          ),
          gti: resolvedJob.gti_score,
          risk: resolvedJob.risk_level,
          srKeys: Object.keys(sr),
          specialistContentSig,
        });

        if (jobSig !== lastJobSignatureRef.current || hasTerminalReconciliation) {
          lastJobSignatureRef.current = jobSig;
          setJob(resolvedJob);
        }
        setJobStatus(effectiveStatus);

        if (terminalFromRest) {
          applyTerminalUpdate(
            fetchedStatus,
            jobData as unknown as InvestigationStreamData,
            "investigation_snapshot"
          );
        }

        const durableTransparencyLog =
          resolvedJob?.transparency_log ?? resolvedJob?.metadata?.transparency_log;
        if (Array.isArray(durableTransparencyLog) && durableTransparencyLog.length > 0) {
          const lastEntry = durableTransparencyLog[durableTransparencyLog.length - 1] as
            | TransparencyEntry
            | undefined;
          const logSig = `${durableTransparencyLog.length}:${lastEntry?.timestamp ?? ""}`;
          if (logSig !== lastLogSignatureRef.current) {
            lastLogSignatureRef.current = logSig;
            setActivityLog(formatTransparencyLog(durableTransparencyLog));
          }
        }

        if (graphRes.ok) {
          const graphData: GraphData = await graphRes.json();
          const graphSig = `${graphData.nodes?.length ?? 0}:${graphData.edges?.length ?? 0}:${graphData.nodes?.map((n) => n.id).join(",") ?? ""}`;
          if (graphSig !== lastGraphSignatureRef.current) {
            lastGraphSignatureRef.current = graphSig;
            rawGraphRef.current = graphData;
            setRawGraphData(graphData);
          }
        }
        return effectiveStatus;
      } catch (e) {
        console.error(e);
        return terminalStatusRef.current ?? "running";
      }
    };

    refetch();

    eventSource = new EventSource(`/api/investigations/${id}/stream`);

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const eventType = payload.event || "message";
        const data = payload.data || {};

        if (data.progress !== undefined) setProgress(data.progress);
        if (data.message) setStatusMessage(data.message);

        if (eventType === "transparency_event" && data.entry) {
          const entry = data.entry;
          const time = entry.timestamp
            ? new Date(entry.timestamp).toLocaleTimeString()
            : new Date().toLocaleTimeString();
          const line = `[${time}] ${entry.tool ? "TOOL" : "THOUGHT"} ${entry.agent || "system"}: ${
            entry.tool ? `EXECUTING_${entry.tool}` : "ANALYZING_DATA"
          }`;
          setActivityLog((prev) => [line, ...prev.slice(0, 24)]);
        }

        const terminalStatus = isTerminalInvestigationStatus(data.status)
          ? data.status
          : eventType === "investigation_completed"
            ? "completed"
            : eventType === "investigation_failed"
              ? "failed"
              : eventType === "investigation_cancelled"
                ? "cancelled"
                : null;

        if (terminalStatus) {
          applyTerminalUpdate(terminalStatus, data, eventType);
          refetch();
        }
      } catch {
        // Ignore unparseable stream frames
      }
    };

    pollInterval = setInterval(async () => {
      const currentStatus = await refetch();
      if (isTerminalInvestigationStatus(currentStatus)) {
        if (pollInterval) clearInterval(pollInterval);
      }
    }, 4000);

    return () => {
      if (pollInterval) clearInterval(pollInterval);
      eventSource?.close();
    };
    // NOTE: intentionally keyed on `id` only. Including `rebuildSpatialGraph`
    // here would re-create the EventSource and polling interval on every job
    // poll and every graph-filter toggle (its identity changes with
    // `parsedDossier.parsedDotGraph` and `graphFilters`), which self-feeds into
    // an unbounded refetch loop. The graph is re-rendered separately by the
    // dedicated `rebuildSpatialGraph` effect above.
  }, [id]);

  return (
    <div className="dossier-surface bg-slate-950 text-slate-200 font-sans min-h-screen flex flex-col selection:bg-teal-500 selection:text-slate-950">
      {/* Sticky Top Header Bar */}
      <header className="sticky top-0 w-full z-50 bg-slate-950/90 backdrop-blur-xl border-b border-slate-800/80 px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <Link href="/" className="flex items-center gap-2 shrink-0">
            <span className="w-2.5 h-2.5 rounded-full bg-teal-400 shadow-[0_0_8px_#2dd4bf]" />
            <span className="font-bold tracking-wider text-sm text-white uppercase font-mono">
              HARIMAU
            </span>
          </Link>

          <div className="h-4 w-px bg-slate-800 hidden sm:block" />

          <div className="hidden sm:flex items-center gap-2 min-w-0">
            <span className="text-[11px] font-mono text-slate-400 truncate max-w-[220px]">
              {job?.ioc || id}
            </span>
            {job?.risk_level && (
              <span
                className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                  job.risk_level.toUpperCase().includes("MALICIOUS")
                    ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                    : job.risk_level.toUpperCase().includes("SUSPICIOUS")
                      ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                      : "bg-teal-500/20 text-teal-300 border-teal-500/40"
                }`}
              >
                {job.risk_level.toUpperCase()}{" "}
                {job.gti_score !== null && job.gti_score !== undefined
                  ? `${job.gti_score}/100`
                  : ""}
              </span>
            )}
          </div>
        </div>

        {/* Center Workbench Switcher Tabs: Threat Dossier vs Spatial Canvas */}
        <div className="flex items-center bg-slate-900/90 p-1 rounded-xl border border-slate-800">
          <button
            onClick={() => setActiveView("dossier")}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeView === "dossier"
                ? "bg-teal-500/20 text-teal-300 border border-teal-500/40 shadow-sm"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <span>📑 Threat Dossier</span>
          </button>
          <button
            onClick={() => setActiveView("canvas")}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeView === "canvas"
                ? "bg-teal-500/20 text-teal-300 border border-teal-500/40 shadow-sm"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <span>🕸️ Spatial Topology Canvas</span>
            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-teal-300">
              {graphEntityCount}
            </span>
          </button>
        </div>

        {/* Right Controls: Case Switcher & Agent Log Drawer */}
        <div className="flex items-center gap-2.5">
          {recentJobs.length > 0 && (
            <select
              className="hidden xl:block bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-1.5 font-mono outline-none cursor-pointer"
              value={id}
              onChange={(e: ChangeEvent<HTMLSelectElement>) => {
                if (e.target.value && e.target.value !== id) {
                  router.push(`/investigate/${e.target.value}`);
                }
              }}
            >
              <option value={id}>Switch Case ({id.slice(0, 8)}...)</option>
              {recentJobs.map((j) => (
                <option key={j.job_id} value={j.job_id}>
                  {j.ioc} ({j.status})
                </option>
              ))}
            </select>
          )}

          <button
            onClick={() => setShowAgentDrawer((prev) => !prev)}
            className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 text-xs font-mono flex items-center gap-1.5 transition-colors"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="hidden md:inline">Agent Log</span>
          </button>
        </div>
      </header>

      {/* Copied Toast Notification */}
      {copiedToast && (
        <div className="fixed bottom-5 right-5 z-50 bg-slate-900 border border-teal-500/50 text-teal-300 px-4 py-2.5 rounded-xl shadow-2xl text-xs font-mono flex items-center gap-2">
          <span>✔ Copied indicator to clipboard:</span>
          <strong className="text-white truncate max-w-[240px]">{copiedToast}</strong>
        </div>
      )}

      {/* Jump-to-Canvas Notice */}
      {jumpNotice && (
        <div
          className={`fixed right-5 z-50 bg-slate-900 border border-amber-500/50 text-amber-300 px-4 py-2.5 rounded-xl shadow-2xl text-xs font-mono flex items-center gap-2 max-w-sm ${
            copiedToast ? "bottom-16" : "bottom-5"
          }`}
        >
          <span>{jumpNotice}</span>
        </div>
      )}

      {/* Main Content Area */}
      {jobStatus === "running" && !job?.final_report ? (
        <main className="flex-1 flex flex-col items-center justify-center p-6 max-w-2xl mx-auto w-full space-y-8">
          <div className="w-full space-y-2">
            <div className="flex justify-between font-mono text-xs uppercase tracking-wider">
              <span className="text-teal-400">Harimau Multi-Agent Swarm Active</span>
              <span className="text-white font-bold">{progress}%</span>
            </div>
            <div className="w-full h-1.5 bg-slate-900 rounded-full overflow-hidden border border-slate-800">
              <div
                className="h-full bg-teal-400 transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          <div className="w-full rounded-2xl bg-slate-900/80 border border-slate-800 p-6 space-y-4 shadow-xl">
            <div className="flex items-center gap-3">
              <span className="w-2.5 h-2.5 rounded-full bg-teal-400 animate-ping" />
              <p className="font-mono text-sm font-semibold text-white">{statusMessage}</p>
            </div>

            <div className="space-y-1.5 max-h-56 overflow-y-auto font-mono text-xs text-slate-400 border-t border-slate-800/80 pt-3">
              {activityLog.map((log, idx) => (
                <div key={idx} className="truncate">
                  {log}
                </div>
              ))}
              {activityLog.length === 0 && (
                <div className="text-slate-500 italic">Waiting for agent telemetry stream...</div>
              )}
            </div>
          </div>
        </main>
      ) : jobStatus === "failed" || jobStatus === "cancelled" ? (
        <main className="flex-1 flex items-center justify-center p-6">
          <div className="w-full max-w-2xl rounded-2xl border border-rose-500/40 bg-slate-900/90 p-8 space-y-6 shadow-2xl">
            <div className="space-y-1">
              <span className="text-xs font-mono uppercase tracking-widest text-rose-400">
                Terminal Investigation State
              </span>
              <h2 className="text-2xl font-bold text-white">
                {jobStatus === "cancelled" ? "Investigation Cancelled" : "Investigation Failed"}
              </h2>
            </div>
            <p className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-4 font-mono text-xs text-rose-200">
              {job?.metadata?.error || statusMessage}
            </p>
            <Link
              href="/"
              className="inline-flex items-center gap-2 rounded-xl bg-teal-500/20 border border-teal-500/40 px-4 py-2 text-xs font-semibold text-teal-200 hover:bg-teal-500/30 transition-colors"
            >
              Start New Investigation
            </Link>
          </div>
        </main>
      ) : activeView === "dossier" ? (
        /* ================================================================= */
        /* VIEW 1: THREAT DOSSIER WORKBENCH (~75% Fluid Viewport Layout)     */
        /* ================================================================= */
        <div className="w-full sm:w-[92%] md:w-[88%] lg:w-[82%] xl:w-[75%] mx-auto min-w-0 px-4 sm:px-6 xl:px-8 py-10 flex gap-8 xl:gap-10 transition-[width] duration-150">
          {/* Left/Center Column: Publication Article Body (Fluid Width, No max-w-1020px constraint) */}
          <article className="flex-1 min-w-0 space-y-8 pb-24 font-sans text-slate-300 text-sm leading-relaxed">
            {job && (
              <DossierMasthead job={job} graphEntityCount={graphEntityCount} />
            )}

            {/* Optional Preamble before Section 1 */}
            {parsedDossier.preamble && (
              <ThreatDossierMarkdown content={parsedDossier.preamble} />
            )}

            {/* Strict 1-7 Dossier Sections */}
            {parsedDossier.sections.map((sec) => {
              const hasComponent = sec.number === 3 || sec.number === 6 || sec.number === 7;
              const hasSubtasksTimeline =
                sec.number === 4 && Array.isArray(job?.subtasks) && job.subtasks.length > 0;
              const isEmptyProse = !sec.markdownBody && !hasComponent && !hasSubtasksTimeline;

              return (
                <section key={sec.id} id={sec.id} className="scroll-mt-20 space-y-4">
                  <h3 className="text-xl font-bold text-white tracking-tight border-b border-slate-800/80 pb-2">
                    {sec.title}
                  </h3>

                  {/* Section 3: Autonomous Specialist Reports Grid */}
                  {sec.number === 3 && job && (
                    <SpecialistReportsGrid
                      job={job}
                      onJumpToNode={handleJumpToNode}
                      onCopyIoc={handleCopyIoc}
                    />
                  )}

                  {/* Section Markdown Narrative Body */}
                  {sec.markdownBody && (
                    <ThreatDossierMarkdown content={sec.markdownBody} />
                  )}

                  {/* Section 4 Structured Timeline Fallback / Supplement from job.subtasks */}
                  {sec.number === 4 && hasSubtasksTimeline && !sec.markdownBody && (
                    <div className="space-y-2.5 my-4">
                      {job?.subtasks?.map((task, idx) => (
                        <div
                          key={idx}
                          className="p-3.5 rounded-xl bg-slate-900/70 border border-slate-800/90 flex items-start justify-between gap-4"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-teal-950 text-teal-300 border border-teal-800/60">
                                {task.agent || "AGENT"}
                              </span>
                              {task.timestamp && (
                                <span className="text-[11px] font-mono text-slate-500">
                                  {new Date(task.timestamp).toLocaleTimeString()}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-200 leading-relaxed">{task.task}</p>
                          </div>
                          <span className="text-[10px] font-mono uppercase text-slate-400 shrink-0">
                            {task.status || "COMPLETED"}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Empty Prose Section Fallback (prevents bare headings while preserving ToC anchors) */}
                  {isEmptyProse && (
                    <p className="text-xs font-mono text-slate-500 italic py-2">
                      No additional narrative synthesized for this section.
                    </p>
                  )}

                  {/* Section 6: Interactive Attack Flow Workbench & Dynamic Swim Lanes */}
                  {sec.number === 6 && job && (
                    <AttackFlowSection
                      job={job}
                      rawDotCode={parsedDossier.rawDotCode}
                      parsedGraph={parsedDossier.parsedDotGraph}
                      swimLanes={swimLanes}
                      onJumpToNode={handleJumpToNode}
                      onCopyIoc={handleCopyIoc}
                      onExploreInCanvas={() => setActiveView("canvas")}
                    />
                  )}

                  {/* Section 7: Consolidated Indicators of Compromise Table */}
                  {sec.number === 7 && (
                    <AppendixIocTable
                      iocs={parsedDossier.appendixIocs}
                      onJumpToNode={handleJumpToNode}
                      onCopyIoc={handleCopyIoc}
                    />
                  )}
                </section>
              );
            })}
          </article>

          {/* Right Column: Sticky Companion Rail */}
          {job && (
            <DossierCompanionRail
              job={job}
              onOpenCanvasTab={() => setActiveView("canvas")}
              onToggleAgentLog={() => setShowAgentDrawer((prev) => !prev)}
              onJumpToNode={handleJumpToNode}
              onCopyIoc={handleCopyIoc}
            />
          )}
        </div>
      ) : (
        /* ================================================================= */
        /* VIEW 2: SPATIAL TOPOLOGY CANVAS WORKBENCH (@xyflow/react)         */
        /* ================================================================= */
        <div className="relative flex-1 w-full h-[calc(100vh-3.5rem)] overflow-hidden bg-slate-950">
          {/* Top-Left Floating Dossier Brief HUD */}
          <div className="absolute top-4 left-6 z-20 w-80 rounded-2xl bg-slate-900/90 backdrop-blur-md border border-slate-800 p-4 shadow-2xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-teal-400" />
                <h3 className="font-bold text-xs text-white uppercase tracking-wider font-mono">
                  Threat Dossier Brief
                </h3>
              </div>
              <button
                onClick={() => setActiveView("dossier")}
                className="px-2.5 py-1 rounded-lg bg-teal-500/20 hover:bg-teal-500/30 border border-teal-500/40 text-teal-200 text-xs font-semibold transition-all"
              >
                Threat Dossier ➔
              </button>
            </div>
            <p className="text-xs text-slate-400 line-clamp-3">
              {job?.rich_intel?.triage_summary ||
                job?.rich_intel?.gti_description ||
                "Click any entity node on the spatial canvas to inspect telemetry attributes and relationships."}
            </p>
          </div>

          {/* Top-Right Filter Pills HUD */}
          <div className="absolute top-4 right-6 z-20 flex flex-wrap items-center gap-3 bg-slate-900/90 backdrop-blur-md border border-slate-800 px-3.5 py-2 rounded-xl text-xs shadow-2xl">
            <label className="flex items-center gap-1.5 cursor-pointer text-slate-300 select-none">
              <input
                type="checkbox"
                checked={graphFilters.reportOnly}
                onChange={(e) =>
                  setGraphFilters((f) => ({ ...f, reportOnly: e.target.checked }))
                }
                className="accent-teal-400 rounded cursor-pointer"
              />
              <span className="text-[11px] font-medium">Relevant</span>
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer text-slate-300 select-none">
              <input
                type="checkbox"
                checked={graphFilters.maliciousOnly}
                onChange={(e) =>
                  setGraphFilters((f) => ({ ...f, maliciousOnly: e.target.checked }))
                }
                className="accent-rose-500 rounded cursor-pointer"
              />
              <span className="text-[11px] font-medium">Malicious Only</span>
            </label>

            <div className="h-3.5 w-px bg-slate-800 hidden sm:block" />

            {(["file", "domain", "ip_address", "url"] as const).map((entityType) => (
              <label
                key={entityType}
                className="flex items-center gap-1 cursor-pointer text-slate-300 select-none"
              >
                <input
                  type="checkbox"
                  checked={graphFilters.types[entityType] ?? true}
                  onChange={(e) =>
                    setGraphFilters((f) => ({
                      ...f,
                      types: { ...f.types, [entityType]: e.target.checked },
                    }))
                  }
                  className="accent-teal-400 rounded cursor-pointer"
                />
                <span className="text-[10px] font-mono uppercase">
                  {entityType === "ip_address" ? "IP" : entityType}
                </span>
              </label>
            ))}
          </div>

          {/* ReactFlow Canvas */}
          <div className="w-full h-full">
            <ReactFlow
              onInit={(instance) => {
                reactFlowRef.current = instance;
              }}
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              fitView
              onNodeClick={(_event, node) => {
                const raw =
                  node.data?.rawNode ||
                  effectiveGraphRef.current?.nodes.find((n) => n.id === node.id);
                if (raw) setSelectedNode(raw);
              }}
            >
              <Background
                color="#1e293b"
                gap={24}
                size={1}
                variant={BackgroundVariant.Dots}
              />
              <Controls className="!bg-slate-900 !border-slate-800 !text-slate-300" />
              <MiniMap
                className="!bg-slate-900 !border-slate-800"
                maskColor="rgba(2, 6, 23, 0.75)"
                nodeColor={(n: Node<CustomNodeData>) =>
                  n.data?.isMalicious ? "#f43f5e" : n.data?.isRoot ? "#00f7ff" : "#64748b"
                }
              />
            </ReactFlow>
          </div>

          {/* Slide-In Right Node Inspector */}
          {selectedNode && (
            <div className="absolute top-4 right-6 bottom-6 w-80 rounded-2xl bg-slate-900/95 backdrop-blur-xl border border-slate-800 z-30 flex flex-col shadow-2xl overflow-hidden animate-slide-in-right">
              <div className="p-4 border-b border-slate-800 flex items-center justify-between">
                <span className="text-xs font-mono uppercase text-teal-400 font-bold">
                  {selectedNode.entityType || "Entity"} Inspector
                </span>
                <button
                  onClick={() => setSelectedNode(null)}
                  className="text-slate-400 hover:text-white text-xs font-mono px-2 py-0.5 rounded hover:bg-slate-800"
                >
                  ✕
                </button>
              </div>

              <div className="flex-1 p-4 overflow-y-auto space-y-4 text-xs">
                {/* Status Badges */}
                <div className="flex flex-wrap gap-1.5">
                  {selectedNode.isRoot && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                      Root IOC
                    </span>
                  )}
                  {selectedNode.isMalicious && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-rose-500/20 text-rose-300 border border-rose-500/40">
                      Malicious
                    </span>
                  )}
                  {selectedNode.inReport && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-teal-500/20 text-teal-300 border border-teal-500/40">
                      In Report
                    </span>
                  )}
                </div>

                <div>
                  <span className="text-[10px] font-mono text-slate-400 uppercase block mb-1">
                    Indicator Value
                  </span>
                  <div className="font-mono text-white break-all bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                    {selectedNode.id}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] font-mono text-slate-400 uppercase block">
                      Verdict
                    </span>
                    <span className="font-mono font-bold text-slate-200">
                      {selectedNode.verdict || (selectedNode.isMalicious ? "MALICIOUS" : "ANALYZED")}
                    </span>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] font-mono text-slate-400 uppercase block">
                      Threat Score
                    </span>
                    <span className="font-mono font-bold text-teal-300">
                      {selectedNode.threatScore !== null && selectedNode.threatScore !== undefined
                        ? `${selectedNode.threatScore}/100`
                        : "N/A"}
                    </span>
                  </div>
                </div>

                {selectedNode.vendorDetections && (
                  <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] font-mono text-slate-400 uppercase block mb-1">
                      Vendor Detections
                    </span>
                    <span className="font-mono font-bold text-rose-400">
                      {selectedNode.vendorDetections}
                    </span>
                  </div>
                )}

                {selectedNode.title && (
                  <div>
                    <span className="text-[10px] font-mono text-slate-400 uppercase block mb-1">
                      Analysis Details
                    </span>
                    <pre className="font-mono text-[11px] text-slate-300 whitespace-pre-wrap bg-slate-950 p-3 rounded-lg border border-slate-800 overflow-x-auto max-h-48">
                      {selectedNode.title}
                    </pre>
                  </div>
                )}
              </div>

              <div className="p-3 border-t border-slate-800 bg-slate-950/80 flex gap-2">
                <button
                  onClick={() => handleCopyIoc(selectedNode.id)}
                  className="flex-1 py-1.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs transition-colors"
                >
                  Copy IOC
                </button>
                <button
                  onClick={() => setActiveView("dossier")}
                  className="flex-1 py-1.5 px-3 rounded-lg bg-teal-500/20 hover:bg-teal-500/30 border border-teal-500/40 text-teal-200 font-semibold text-xs transition-colors"
                >
                  View in Threat Dossier
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Agent Orchestration Drawer Modal */}
      {showAgentDrawer && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-md bg-slate-900 border-l border-slate-800 h-full flex flex-col shadow-2xl">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-teal-400" />
                <h3 className="font-bold text-sm text-white font-mono uppercase">
                  Agent Orchestration & Telemetry Log
                </h3>
              </div>
              <button
                onClick={() => setShowAgentDrawer(false)}
                className="text-slate-400 hover:text-white text-xs font-mono px-2 py-1 rounded hover:bg-slate-800"
              >
                Close ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3 font-mono text-xs">
              {job?.subtasks && job.subtasks.length > 0 && (
                <div className="space-y-2 pb-4 border-b border-slate-800">
                  <span className="text-[10px] uppercase text-teal-400 font-semibold block">
                    Completed Subtasks
                  </span>
                  {job.subtasks.map((task, i) => (
                    <div key={i} className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                      <div className="flex justify-between text-[10px] text-slate-400">
                        <span className="text-teal-300 font-bold uppercase">{task.agent}</span>
                        <span>{task.status}</span>
                      </div>
                      <p className="text-slate-300 text-xs">{task.task}</p>
                    </div>
                  ))}
                </div>
              )}

              <div className="space-y-2">
                <span className="text-[10px] uppercase text-slate-400 font-semibold block">
                  Live Stream Activity
                </span>
                {activityLog.map((log, i) => (
                  <div key={i} className="p-2 rounded bg-slate-950/60 border border-slate-800/60 text-slate-300 text-[11px]">
                    {log}
                  </div>
                ))}
                {activityLog.length === 0 && (
                  <p className="text-slate-500 italic">No activity events recorded.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
