"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useRef, ChangeEvent } from "react";
import ReactMarkdown from "react-markdown";
import { Background, BackgroundVariant, Controls, MiniMap, ReactFlow, useNodesState, useEdgesState, Handle, Position, MarkerType } from "@xyflow/react";
import { forceSimulation, forceLink, forceManyBody, forceCollide, forceX, forceY } from "d3-force";
import "@xyflow/react/dist/style.css";

// Custom Markdown Renderer for high readability - Adjusted for new design
const MarkdownRenderer = ({ content }: { content: string }) => (
  <ReactMarkdown
    className="font-body text-sm leading-relaxed text-outline space-y-4"
    components={{
      h1: ({ node, ...props }) => <h1 className="text-2xl font-headline font-black text-primary mt-8 mb-4 uppercase tracking-tighter glow-text-primary" {...props} />,
      h2: ({ node, ...props }) => <h2 className="text-xl font-headline font-bold text-secondary mt-8 mb-4 border-b border-secondary/20 pb-2 uppercase tracking-wide" {...props} />,
      h3: ({ node, ...props }) => <h3 className="text-lg font-headline font-bold text-foreground mt-6 mb-3 uppercase" {...props} />,
      p: ({ node, ...props }) => <p className="mb-4" {...props} />,
      ul: ({ node, ...props }) => <ul className="list-disc pl-6 mb-4 space-y-2 marker:text-primary" {...props} />,
      ol: ({ node, ...props }) => <ol className="list-decimal pl-6 mb-4 space-y-2 marker:text-secondary" {...props} />,
      table: ({ node, ...props }) => <div className="overflow-x-auto mb-6 border border-outline-variant/30"><table className="w-full text-left border-collapse text-xs" {...props} /></div>,
      thead: ({ node, ...props }) => <thead className="bg-surface-container-high text-secondary" {...props} />,
      th: ({ node, ...props }) => <th className="p-3 font-semibold tracking-wide border-b border-outline-variant/30 whitespace-nowrap" {...props} />,
      td: ({ node, ...props }) => <td className="p-3 border-b border-surface-container text-outline" {...props} />,
      tr: ({ node, ...props }) => <tr className="hover:bg-surface-container-highest/50 transition-colors" {...props} />,
      strong: ({ node, ...props }) => <strong className="font-bold text-foreground" {...props} />,
      a: ({ node, ...props }) => <a className="text-secondary hover:text-primary underline decoration-secondary/30 underline-offset-2 transition-colors" {...props} />,
      blockquote: ({ node, ...props }) => <blockquote className="border-l-4 border-primary bg-surface-container-low py-3 px-5 mb-4 italic text-outline" {...props} />,
      code(props) {
        const { children, className, node, ...rest } = props;
        const match = /language-(\w+)/.exec(className || '');
        const isInline = !match && !className;
        return isInline ? (
          <code className="bg-surface-container-highest text-primary px-1.5 py-0.5 text-xs font-mono" {...rest}>
            {children}
          </code>
        ) : (
          <div className="relative mb-4 group">
            <pre className="bg-surface-container-lowest p-4 border border-outline-variant/30 overflow-x-auto text-xs font-mono text-secondary/80">
              <code className={className} {...rest}>
                {children}
              </code>
            </pre>
          </div>
        );
      }
    }}
  >
    {content}
  </ReactMarkdown>
);

// Typewriter Component
const Typewriter = ({ text, speed = 1 }: { text: string; speed?: number }) => {
  const [displayedText, setDisplayedText] = useState("");
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (index < text.length) {
      const timeout = setTimeout(() => {
        const chunk = text.slice(index, index + 25);
        setDisplayedText((prev) => prev + chunk);
        setIndex((prev) => prev + 25);
      }, speed);
      return () => clearTimeout(timeout);
    }
  }, [index, text, speed]);

  return <MarkdownRenderer content={displayedText} />;
};

const IP_REGEX = /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/;
const HASH_REGEX = /^[a-fA-F0-9]{32,64}$/;

// Custom Node Component - Wiz Style (Circles)
const CustomNode = ({ data, style }: any) => {
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

  const color = isRoot ? "var(--secondary)" : isMalicious ? "var(--primary)" : "var(--outline)";
  
  return (
    <div className="relative group flex flex-col items-center">
      <Handle type="target" position={Position.Top} className="!opacity-0" style={{ left: "50%", top: "50%" }} />
      <Handle type="source" position={Position.Bottom} className="!opacity-0" style={{ left: "50%", top: "50%" }} />

      {/* Alert Badge (Wiz style) */}
      {isMalicious && (
        <div className="absolute -top-2 -right-2 bg-error text-white p-0.5 rounded-full z-10 flex items-center justify-center" style={{ borderRadius: '50% !important', width: '16px', height: '16px' }}>
          <span className="material-symbols-outlined text-[10px]">warning</span>
        </div>
      )}

      <div
        className={`transition-all duration-300 flex items-center justify-center`}
        style={{
          width: nodeSize,
          height: nodeSize,
          background: "var(--surface-container-high)",
          border: `2px solid ${color}`,
          boxShadow: `0 0 15px ${color}33`,
          borderRadius: '50% !important', // Override global sharp edges
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: iconSize, color: color }}>
          {icon}
        </span>
      </div>

      {/* Label Below (Wiz style) */}
      <div className="mt-2 text-[9px] font-label uppercase tracking-widest text-outline whitespace-nowrap overflow-hidden text-ellipsis max-w-[100px] text-center">
        {label}
      </div>
      
      {/* Title in Tooltip or small text */}
      <div className="text-[7px] text-outline-variant text-center max-w-[100px] truncate">{title}</div>
    </div>
  );
};

const nodeTypes = { custom: CustomNode };

interface BackendNode {
  id: string;
  label: string;
  color: string;
  size: number;
  title?: string;
  isRoot?: boolean;
  isMalicious?: boolean;
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

export default function InvestigatePage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();

  const [expandedTile, setExpandedTile] = useState<number | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<any>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<any>([]);
  const [loading, setLoading] = useState(true);
  const [job, setJob] = useState<any>(null);
  const [jobStatus, setJobStatus] = useState<string>("running");
  const [progress, setProgress] = useState<number>(0);
  const [statusMessage, setStatusMessage] = useState<string>("Initializing secure channel...");
  const [activityLog, setActivityLog] = useState<string[]>([]);
  const [recentJobs, setRecentJobs] = useState<any[]>([]);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [modalContent, setModalContent] = useState<{ title: string; content: string } | null>(null);
  const simulationRef = useRef<any>(null);

  useEffect(() => {
    if (!id) return;

    fetch("/api/investigations")
      .then((r) => r.json())
      .then((jobs) => setRecentJobs(Array.isArray(jobs) ? jobs : []))
      .catch(() => setRecentJobs([]));

    let pollInterval: ReturnType<typeof setInterval> | null = null;
    let eventSource: EventSource | null = null;

    const refetch = async (): Promise<string> => {
      try {
        const [graphRes, jobRes] = await Promise.all([
          fetch(`/api/investigations/${id}/graph`),
          fetch(`/api/investigations/${id}`),
        ]);

        if (!jobRes.ok) throw new Error("Failed to fetch job details");

        const jobData = await jobRes.json();
        setJob(jobData);
        setJobStatus(jobData.status ?? "running");

        if (graphRes.ok) {
          const graphData: GraphData = await graphRes.json();
          if (graphData.nodes?.length > 0) {
            if (simulationRef.current) {
              simulationRef.current.stop();
              simulationRef.current = null;
            }

            setNodes((currentNodes) => {
              const existingPositions = new Map(currentNodes.map((n) => [n.id, n.position]));

              const simNodes: any[] = graphData.nodes.map((n) => {
                const pos = existingPositions.get(n.id);
                const isRoot = n.isRoot === true;
                return {
                  id: n.id,
                  x: pos?.x ?? (Math.random() - 0.5) * 500,
                  y: pos?.y ?? (Math.random() - 0.5) * 500,
                  radius: n.size,
                  fx: isRoot ? 0 : undefined,
                  fy: isRoot ? 0 : undefined,
                };
              });

              const simEdges = graphData.edges.map((e) => ({ source: e.source, target: e.target }));
              const simNodeMap = new Map<string, any>(simNodes.map((n) => [n.id, n]));

              const simulation = forceSimulation(simNodes)
                .force("link", forceLink(simEdges).id((d: any) => d.id).distance(180).strength(0.1))
                .force("charge", forceManyBody().strength(-800).distanceMax(600))
                .force("collide", forceCollide().radius((d: any) => d.radius + 20).strength(0.9))
                .force("x", forceX(0).strength(0.05))
                .force("y", forceY(0).strength(0.05))
                .alphaDecay(0.02)
                .velocityDecay(0.4);

              simulation.stop();
              for (let i = 0; i < 120; i++) simulation.tick();

              simulation.restart();
              simulation.on("tick", () => {
                setNodes((nds) =>
                  nds.map((node) => {
                    const sim = simNodeMap.get(node.id);
                    if (!sim) return node;
                    return { ...node, position: { x: sim.x ?? 0, y: sim.y ?? 0 } };
                  })
                );
              });

              simulationRef.current = simulation;

              return graphData.nodes.map((n) => {
                const sim = simNodeMap.get(n.id)!;
                const isRoot = n.isRoot === true;
                return {
                  id: n.id,
                  type: "custom",
                  position: { x: sim.x, y: sim.y },
                  data: { label: n.label, title: n.title, isRoot, isMalicious: n.isMalicious, accent: n.color },
                  style: {
                    background: "transparent",
                    border: "none",
                    padding: 0,
                    width: n.size * 2,
                    height: n.size * 2,
                    overflow: "visible",
                  },
                };
              });
            });

            const calculatedEdges = graphData.edges.map((edge, index) => ({
              id: `e-${index}`,
              source: edge.source,
              target: edge.target,
              label: edge.label,
              type: "straight",
              style: { stroke: "rgba(0, 251, 251, 0.2)", strokeWidth: 1 },
              labelStyle: { fill: "rgba(255, 124, 245, 0.6)", fontSize: "8px", fontFamily: "var(--font-space-grotesk)", textTransform: "uppercase" },
              labelBgStyle: { fill: "var(--surface-container-lowest)", fillOpacity: 0.8 },
              labelBgPadding: [2, 4] as [number, number],
              markerEnd: { type: MarkerType.ArrowClosed, width: 8, height: 8, color: "rgba(0, 251, 251, 0.4)" },
            }));
            setEdges(calculatedEdges);
          }
        }
        return jobData.status ?? "running";
      } catch (err) {
        console.error("refetch error:", err);
        return "running";
      } finally {
        setLoading(false);
      }
    };

    const startPolling = () => {
      setStatusMessage("Stream failure. Initializing emergency polling...");
      pollInterval = setInterval(async () => {
        const status = await refetch();
        if (status === "completed" || status === "failed") {
          if (pollInterval) clearInterval(pollInterval);
          setProgress(100);
          setStatusMessage(status === "completed" ? "Investigation finalized." : "System error occurred.");
        }
      }, 10_000);
    };

    refetch().then((status) => {
      if (status === "completed" || status === "failed") {
        setProgress(100);
        setStatusMessage(status === "completed" ? "Investigation finalized." : "System error occurred.");
        return;
      }

      eventSource = new EventSource(`/api/investigations/${id}/stream`);

      eventSource.onmessage = async (e: MessageEvent) => {
        try {
          const event = JSON.parse(e.data);
          const eventType: string = event.event_type ?? "";
          const data = event.data ?? {};
          const msg: string = data.message ?? "";
          const agent: string = data.agent ?? "";
          const pct: number = data.progress ?? 0;

          if (pct > 0) setProgress(Math.min(pct, 100));

          if (eventType === "investigation_completed") {
            setProgress(100);
            setStatusMessage("Mission complete.");
            await refetch();
            eventSource?.close();
          } else if (eventType === "investigation_failed") {
            setProgress(100);
            setStatusMessage(`Mission failure: ${data.error ?? "ERR_UNKNOWN"}`);
            await refetch();
            eventSource?.close();
          } else if (eventType === "tool_invocation") {
            setActivityLog((prev) => [`🔧 ${agent}: EXECUTING_${data.tool}`, ...prev].slice(0, 20));
          } else if (eventType === "agent_reasoning") {
            setActivityLog((prev) => [`💭 ${agent}: ANALYZING_DATA`, ...prev].slice(0, 20));
          } else if (eventType.includes("_started")) {
            setStatusMessage(`🤖 ${msg || agent}`);
          } else if (eventType.includes("_completed")) {
            setStatusMessage(`✅ ${msg || agent}`);
            if (agent) setActivityLog((prev) => [`✅ ${agent}: SYNOPSIS_READY`, ...prev].slice(0, 20));
          } else {
            if (msg) setStatusMessage(msg);
          }
        } catch (parseErr) {
          console.warn("SSE parse error:", parseErr);
        }
      };

      eventSource.onerror = () => {
        eventSource?.close();
        startPolling();
      };
    });

    return () => {
      eventSource?.close();
      if (pollInterval) clearInterval(pollInterval);
      simulationRef.current?.stop();
    };
  }, [id]);

  const tiles = [
    {
      id: 1,
      title: "Tactical_Triage",
      icon: "radar",
      size: "col-span-12 lg:col-span-5",
      isTriage: true,
      content: job ? {
            verdict: job.risk_level || "UNKNOWN",
            score: job.gti_score || "0",
            malicious: job.rich_intel?.malicious_stats || 0,
            total: job.rich_intel?.total_stats || 0,
            summary: job.rich_intel?.triage_summary || ""
          } : null,
    },
    {
      id: 2,
      title: "Intelligence_Graph",
      icon: "hub",
      size: "col-span-12 lg:col-span-7 row-span-2",
      isGraph: true,
    },
    {
      id: 3,
      title: "Specialist_Dossiers",
      icon: "reorder",
      size: "col-span-12 lg:col-span-5",
      isReports: true,
    },
    {
      id: 4,
      title: "Final_Intelligence_Synthesis",
      icon: "description",
      size: "col-span-12 lg:col-span-12 h-auto",
      isFinalReport: true,
    },
    {
      id: 5,
      title: "Mission_Timeline",
      icon: "history",
      size: "col-span-12 lg:col-span-6",
      isTimeline: true,
    },
    {
      id: 6,
      title: "Agent_Transparency",
      icon: "terminal",
      size: "col-span-12 lg:col-span-6",
      isTransparency: true,
    },
  ];

  return (
    <div className="bg-[#0e0e10] text-on-surface font-body overflow-hidden h-screen flex flex-col selection:bg-primary selection:text-on-primary">
      {/* TopNavBar */}
      <header className="fixed top-0 w-full z-50 bg-[#0e0e10]/80 backdrop-blur-xl border-b border-slate-800/50 shadow-2xl shadow-cyan-900/10 flex justify-between items-center px-6 h-16">
        <div className="flex items-center gap-8">
          <span className="text-xl font-bold tracking-widest text-[#00f7ff] font-headline uppercase">HARIMAU</span>
          <nav className="hidden md:flex gap-6 font-headline text-sm uppercase tracking-widest">
            <Link href="/" className="text-slate-400 hover:text-white transition-colors">HUNT</Link>
            <Link href="#" className="text-[#00f7ff] border-b-2 border-[#00f7ff] pb-1">INVESTIGATIONS</Link>
            <Link href="#" className="text-slate-400 hover:text-white transition-colors">INTEL</Link>
          </nav>
        </div>
        <div className="flex-grow flex items-center px-8 gap-4 overflow-hidden">
          <div className="text-[10px] font-label text-outline uppercase tracking-widest whitespace-nowrap">MISSION_ID:</div>
          <div className="text-[10px] font-mono text-secondary truncate max-w-[200px]">{id}</div>
          <div className="hidden md:block text-[10px] font-label text-outline uppercase tracking-widest ml-4">IOC:</div>
          <div className="hidden md:block text-[10px] font-mono text-primary font-black">{job?.ioc}</div>
        </div>
        <div className="flex items-center gap-4">
          {/* History Dropdown kept for functionality */}
          <div className="hidden lg:block relative">
            <select
              className="bg-surface-container border-b-2 border-secondary text-secondary text-[10px] px-3 py-1 font-label uppercase outline-none cursor-pointer appearance-none pr-6"
              value={id}
              onChange={(e: ChangeEvent<HTMLSelectElement>) => {
                if (e.target.value && e.target.value !== id)
                  router.push(`/investigate/${e.target.value}`);
              }}
            >
              <option value={id}>
                {recentJobs.length > 0 ? "RECORDS_HISTORY..." : "LOADING_RECORDS..."}
              </option>
              {recentJobs.map((j: any) => (
                <option key={j.job_id} value={j.job_id}>
                  {j.ioc} // {j.status}
                </option>
              ))}
            </select>
            <span className="absolute right-2 top-1.5 text-secondary material-symbols-outlined text-[12px] pointer-events-none">
              arrow_drop_down
            </span>
          </div>
          <button className="text-slate-400 hover:text-[#00f7ff] transition-colors">
            <span className="material-symbols-outlined">settings_input_component</span>
          </button>
          <div className="w-8 h-8 border border-outline-variant bg-surface-container-high">
            <div className="w-full h-full bg-secondary/20"></div>
          </div>
        </div>
      </header>

      <div className="flex flex-1 pt-16 pb-8 overflow-hidden">
        {/* SideNavBar */}
        <aside className={`fixed left-0 top-16 h-full ${isCollapsed ? 'w-16' : 'w-64'} border-r border-slate-800 bg-[#16161a] flex flex-col py-4 z-40 transition-all duration-300`}>
          <button onClick={() => setIsCollapsed(!isCollapsed)} className="absolute top-4 right-2 text-slate-500 hover:text-[#00f7ff] z-50">
            <span className="material-symbols-outlined text-sm">
              {isCollapsed ? 'chevron_right' : 'chevron_left'}
            </span>
          </button>
          <div className="px-4 mb-8">
            <div className="flex items-center gap-3">
              <div className="w-2 h-2 rounded-full bg-[#00f7ff] animate-pulse flex-shrink-0"></div>
              {!isCollapsed && (
                <div>
                  <p className="font-headline text-sm uppercase font-semibold text-[#00f7ff]">HARIMAU</p>
                  <p className="text-[10px] text-slate-500 uppercase tracking-widest">Active Session</p>
                </div>
              )}
            </div>
          </div>
          <nav className="flex-1 space-y-1">
            <a className="flex items-center gap-4 px-4 py-3 bg-cyan-500/10 text-[#00f7ff] border-r-2 border-[#00f7ff] font-headline text-sm uppercase font-semibold" href="#">
              <span className="material-symbols-outlined">folder_open</span>
              {!isCollapsed && <span>Investigation Cases</span>}
            </a>
            <a className="flex items-center gap-4 px-4 py-3 text-slate-500 hover:bg-white/5 hover:text-slate-300 font-headline text-sm uppercase font-semibold transition-all" href="#">
              <span className="material-symbols-outlined">history_edu</span>
              {!isCollapsed && <span>Archived Reports</span>}
            </a>
          </nav>
          <div className="mt-auto border-t border-slate-800 pt-4 space-y-1 mb-20">
            <div className="flex items-center gap-4 px-4 py-2 text-slate-600 font-headline text-[10px] uppercase">
              <span className="material-symbols-outlined text-sm">sensors</span>
              {!isCollapsed && <span>Agent Status: Optimal</span>}
            </div>
            <div className="flex items-center gap-4 px-4 py-2 text-slate-600 font-headline text-[10px] uppercase">
              <span className="material-symbols-outlined text-sm">lan</span>
              {!isCollapsed && <span>Network Health: Secure</span>}
            </div>
          </div>
        </aside>

        {/* Main Dashboard Canvas */}
        <main className={`${isCollapsed ? 'ml-16' : 'ml-64'} flex-1 p-6 grid grid-cols-12 gap-4 overflow-y-auto h-full custom-scrollbar transition-all duration-300`}>
          
          {jobStatus === "running" ? (
            /* Tactical Loading State inside main canvas */
            <div className="col-span-12 flex flex-col items-center justify-center h-[70vh] gap-12 max-w-2xl mx-auto">
              <div className="w-full space-y-2">
                <div className="flex justify-between font-label text-[10px] uppercase tracking-widest">
                  <span className="text-secondary">Decrypting_Neural_Link</span>
                  <span className="text-primary">{progress}%</span>
                </div>
                <div className="w-full h-1 bg-surface-container-highest relative overflow-hidden">
                  <div className="absolute inset-0 bg-primary/20 animate-pulse"></div>
                  <div className="h-full bg-primary transition-all duration-500 shadow-[0_0_10px_var(--primary)]" style={{ width: `${progress}%` }}></div>
                </div>
              </div>

              <div className="bg-surface-container-low border border-outline-variant/30 p-8 w-full relative overflow-hidden glass-panel">
                 <div className="absolute top-0 right-0 p-2 font-mono text-[8px] text-outline/30">SYS_LOG_V2.5</div>
                 <div className="flex items-start gap-4 mb-6">
                   <div className="w-2 h-12 bg-secondary animate-pulse"></div>
                   <p className="font-headline text-xl font-black uppercase text-foreground tracking-tighter italic">{statusMessage}</p>
                 </div>
                 
                 <div className="space-y-2 max-h-48 overflow-y-auto scrollbar-hide">
                   {activityLog.map((log, i) => (
                     <div key={i} className="font-mono text-[10px] text-outline/60 flex gap-3">
                       <span className="text-secondary/40">[{new Date().toLocaleTimeString()}]</span>
                       <span>{log}</span>
                     </div>
                   ))}
                 </div>
              </div>
            </div>
          ) : (
            <>
              {/* Triage Assessment Panel */}
                <section className="col-span-12 lg:col-span-4 bg-[#16161a] border border-slate-800 p-6ß flex flex-col justify-between relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-32 h-32 bg-secondary/5 blur-3xl -mr-16 -mt-16 rounded-full group-hover:bg-secondary/10 transition-all"></div>
                <div>
                  <div className="flex justify-between items-start">
                    <h3 className="font-label text-outline-variant uppercase mb-2 text-xs tracking-widest">Triage Verdict</h3>
                    <button onClick={() => setModalContent({ title: "Triage Verdict", content: job?.rich_intel?.triage_summary || "No summary available." })} className="text-slate-500 hover:text-[#00f7ff]">
                      <span className="material-symbols-outlined text-sm">fullscreen</span>
                    </button>
                  </div>
                  <div className="flex items-end gap-3 mb-4">
                    <span className={`text-3xl font-headline font-black tracking-tighter uppercase ${job?.risk_level === 'MALICIOUS' ? 'text-primary' : 'text-secondary'}`}>{job?.risk_level || "UNKNOWN"}</span>
                    <span className="bg-secondary/10 text-secondary border border-secondary/20 px-2 py-0.5 text-[10px] mb-2">CRITICAL</span>
                  </div>
                </div>
                <div className="space-y-3">
                  <div className="flex justify-between items-center bg-surface-container-low p-2 border border-slate-800/50">
                    <span className="text-xs text-slate-400">Threat Score</span>
                    <span className="font-mono text-[#00f7ff]">{job?.gti_score || "0"}/100</span>
                  </div>
                  <p className="text-xs text-outline/80 font-body leading-relaxed italic">"{job?.rich_intel?.triage_summary || "No summary available."}"</p>
                </div>
              </section>

              {/* Specialist Reports Hub */}
              <section className="col-span-12 lg:col-span-8 flex gap-4">
                {job?.specialist_results ? Object.entries(job.specialist_results).map(([agent, result]: [string, any]) => (
                  <div key={agent} className="flex-1 bg-[#16161a] border border-slate-800 p-4 hover:border-[#00f7ff]/30 transition-all flex flex-col">
                    <div className="flex justify-between items-start mb-4">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-secondary">bug_report</span>
                        <h4 className="font-headline text-sm font-semibold uppercase">{agent.replace('_', ' ')}</h4>
                      </div>
                      <button onClick={() => setModalContent({ title: agent.replace('_', ' '), content: result.summary })} className="text-slate-500 hover:text-[#00f7ff]">
                        <span className="material-symbols-outlined text-sm">fullscreen</span>
                      </button>
                    </div>
                    <div className="flex-1 font-mono text-xs text-slate-400 leading-relaxed bg-[#0e0e10] p-3 border border-slate-800 overflow-y-auto max-h-[150px] custom-scrollbar">
                      <p className="text-secondary/80 mb-2">// Verdict: {result.verdict}</p>
                      <p>{result.summary || "View detailed briefing..."}</p>
                    </div>
                  </div>
                )) : (
                  <div className="flex-1 bg-[#16161a] border border-slate-800 p-4 flex items-center justify-center text-outline/40 italic uppercase tracking-widest text-xs">
                    Awaiting Specialist Inputs...
                  </div>
                )}
              </section>

              {/* Network Graph Visualizer */}
              <section className="col-span-12 lg:col-span-9 bg-[#16161a] border border-slate-800 relative min-h-[400px] overflow-hidden">
                <div className="absolute inset-0 opacity-20 pointer-events-none" style={{ backgroundImage: "radial-gradient(#1e293b 1px, transparent 1px)", backgroundSize: "24px 24px" }}></div>
                <div className="absolute top-4 left-4 right-4 z-10 flex justify-between items-start">
                  <div>
                    <h3 className="font-label text-outline-variant uppercase text-xs tracking-widest">Link Analysis Graph</h3>
                    <p className="text-[10px] text-slate-500">RELATIONSHIP MAPPING [v4.1]</p>
                  </div>
                  <button onClick={() => setModalContent({ title: "Link Analysis Graph", content: "" })} className="text-slate-500 hover:text-[#00f7ff]">
                    <span className="material-symbols-outlined text-sm">fullscreen</span>
                  </button>
                </div>
                <div className="w-full h-full pt-16">
                  {loading ? (
                    <div className="absolute inset-0 flex items-center justify-center font-label text-[10px] text-outline uppercase tracking-widest">Awaiting_Neural_Map...</div>
                  ) : (
                    <ReactFlow
                      edges={edges}
                      fitView
                      nodes={nodes}
                      nodesConnectable={false}
                      nodeTypes={nodeTypes}
                      onEdgesChange={onEdgesChange}
                      onNodesChange={onNodesChange}
                    >
                      <Background color="var(--outline-variant)" gap={20} size={0.5} variant={BackgroundVariant.Lines} />
                      <Controls className="!bg-surface-container-highest !border-outline-variant !shadow-none !rounded-none" />
                      <MiniMap 
                        className="!bg-surface-container-lowest !border-outline-variant !rounded-none" 
                        maskColor="rgba(0,0,0,0.8)" 
                        nodeColor={(n: any) => n.data?.isMalicious ? "var(--primary)" : n.data?.isRoot ? "var(--secondary)" : "var(--outline)"} 
                      />
                    </ReactFlow>
                  )}
                </div>
              </section>

              {/* Agent Activity Log */}
              <section className="col-span-12 lg:col-span-3 bg-[#0e0e10] border border-slate-800 overflow-hidden flex flex-col max-h-[400px]">
                <div className="p-3 border-b border-slate-800 bg-[#16161a] flex items-center justify-between">
                  <h3 className="font-label text-outline-variant uppercase text-xs tracking-widest">Agent Activity</h3>
                  <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                </div>
                <div className="flex-1 p-3 overflow-y-auto space-y-3 font-mono text-[11px] custom-scrollbar">
                  {activityLog.map((log, idx) => (
                    <div key={idx} className="flex gap-2 border-b border-outline-variant/10 pb-2">
                      <span className="text-secondary/40">[{new Date().toLocaleTimeString()}]</span>
                      <span className="text-slate-500">{log}</span>
                    </div>
                  ))}
                  {activityLog.length === 0 && (
                    <div className="text-outline/30 italic">No activity recorded yet.</div>
                  )}
                </div>
              </section>

              {/* Final Intelligence Report */}
              <section className="col-span-12 lg:col-span-8 bg-[#16161a] border border-slate-800 flex flex-col">
                <div className="flex justify-between items-start p-6 border-b border-slate-800">
                  <div>
                    <h2 className="font-headline text-xl text-[#00f7ff] mb-2 uppercase">Final Intelligence Executive Summary</h2>
                    <p className="text-outline-variant text-xs italic">Case ID: {id} | Assigned: Multi-Agent Core</p>
                  </div>
                  <button onClick={() => setModalContent({ title: "Final Intelligence Executive Summary", content: job?.final_report })} className="text-slate-500 hover:text-[#00f7ff]">
                    <span className="material-symbols-outlined text-sm">fullscreen</span>
                  </button>
                </div>
                <div className="p-6 overflow-y-auto max-h-[300px] custom-scrollbar">
                  <h4 className="text-[#00f7ff] uppercase tracking-wider text-xs font-bold mb-4 font-headline">Findings</h4>
                  <div className="text-on-surface text-sm leading-relaxed">
                    <Typewriter text={job?.final_report || "Report generation in progress..."} speed={2} />
                  </div>
                </div>
              </section>

              {/* Investigation Timeline */}
              <section className="col-span-12 lg:col-span-4 bg-[#16161a] border border-slate-800 p-6">
                <h3 className="font-label text-outline-variant uppercase text-xs tracking-widest mb-6">Investigation Timeline</h3>
                <div className="relative space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-[1px] before:bg-slate-800 custom-scrollbar max-h-[300px] overflow-y-auto pl-2">
                  {job?.subtasks?.map((task: any, idx: number) => (
                    <div key={idx} className="relative pl-8">
                      <div className={`absolute left-0 top-1 w-4 h-4 bg-slate-800 border border-slate-600 rounded-full z-10 flex items-center justify-center`}>
                        <div className={`w-1.5 h-1.5 rounded-full ${task.status === 'completed' ? 'bg-secondary' : 'bg-outline'}`}></div>
                      </div>
                      <p className="text-xs font-mono text-[#00f7ff]">{task.timestamp || "T+0s"}</p>
                      <p className="text-sm font-semibold font-headline uppercase">{task.agent}</p>
                      <p className="text-xs text-slate-500">{task.task}</p>
                    </div>
                  ))}
                  {(!job?.subtasks || job.subtasks.length === 0) && (
                    <div className="text-outline/30 italic text-xs pl-6">No tasks recorded.</div>
                  )}
                </div>
              </section>
            </>
          )}
        </main>

        {/* Modal */}
        {modalContent && (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-md z-[100] flex items-center justify-center p-6">
            <div className="bg-[#16161a] border border-slate-800 w-full max-w-6xl max-h-[90vh] flex flex-col glass-panel">
              <div className="p-6 border-b border-slate-800 flex justify-between items-center">
                <h3 className="font-headline text-xl font-bold uppercase text-[#00f7ff]">{modalContent.title}</h3>
                <button onClick={() => setModalContent(null)} className="text-slate-500 hover:text-[#00f7ff]">
                  <span className="material-symbols-outlined">close</span>
                </button>
              </div>
              <div className="p-6 overflow-y-auto custom-scrollbar text-on-surface text-sm leading-relaxed flex-1">
                {modalContent.title === 'Link Analysis Graph' ? (
                  <div className="w-full h-[70vh]">
                    <ReactFlow
                      edges={edges}
                      fitView
                      nodes={nodes}
                      nodesConnectable={false}
                      nodeTypes={nodeTypes}
                      onEdgesChange={onEdgesChange}
                      onNodesChange={onNodesChange}
                    >
                      <Background color="var(--outline-variant)" gap={20} size={0.5} variant={BackgroundVariant.Lines} />
                      <Controls className="!bg-surface-container-highest !border-outline-variant !shadow-none !rounded-none" />
                      <MiniMap 
                        className="!bg-surface-container-lowest !border-outline-variant !rounded-none" 
                        maskColor="rgba(0,0,0,0.8)" 
                        nodeColor={(n: any) => n.data?.isMalicious ? "var(--primary)" : n.data?.isRoot ? "var(--secondary)" : "var(--outline)"} 
                      />
                    </ReactFlow>
                  </div>
                ) : (
                  <MarkdownRenderer content={modalContent.content} />
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer Meta */}
      <footer className="fixed bottom-0 left-64 right-0 h-8 border-t border-slate-800 bg-[#0e0e10] flex justify-between items-center px-4 font-mono text-[10px] tracking-tighter text-[#00f7ff] z-50">
        <div>v2.4.1-stable | <span className="text-slate-600 ml-2">System Status: Nominal</span></div>
        <div className="flex gap-4">
          <span className="hover:text-white cursor-default transition-colors">System Status</span>
          <span className="hover:text-white cursor-default transition-colors">Active Agents: 14</span>
        </div>
      </footer>
    </div>
  );
}
