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

// Custom Node Component - Fractured Design (Sharp Edges)
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
  const bgColor = isRoot ? "rgba(0, 251, 251, 0.1)" : isMalicious ? "rgba(255, 124, 245, 0.1)" : "rgba(72, 71, 74, 0.1)";

  return (
    <div className="relative group flex flex-col items-center">
      <Handle type="target" position={Position.Top} className="!opacity-0" style={{ left: "50%", top: "50%" }} />
      <Handle type="source" position={Position.Bottom} className="!opacity-0" style={{ left: "50%", top: "50%" }} />

      <div
        className={`transition-all duration-300 ${isMalicious ? 'animate-pulse' : ''}`}
        style={{
          width: nodeSize,
          height: nodeSize,
          background: bgColor,
          border: `2px solid ${color}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: `0 0 15px ${color}33`,
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: iconSize, color: color }}>
          {icon}
        </span>
      </div>

      <div className="mt-2 text-[9px] font-label uppercase tracking-widest text-outline whitespace-nowrap overflow-hidden text-ellipsis max-w-[100px]">
        {label}
      </div>

      {/* Simplified Tooltip */}
      <div className="absolute bottom-full mb-2 hidden group-hover:block z-50 bg-surface-container-highest border border-outline-variant p-2 text-[8px] font-mono text-foreground min-w-[150px] shadow-2xl">
        <div className="text-secondary mb-1 border-b border-outline-variant/30 pb-1">{label}</div>
        <div className="text-outline/80 leading-tight">{title || "NO_METADATA"}</div>
      </div>
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
    <div className="min-h-screen bg-surface text-foreground relative flex flex-col selection:bg-primary selection:text-on-primary font-body">
      {/* HUD Header */}
      <header className="fixed top-0 left-0 w-full z-50 flex items-stretch h-16 border-b border-outline-variant/30 bg-surface/90 backdrop-blur-xl">
        <div className="flex items-center px-6 bg-primary/10 border-r border-primary/30">
          <Link href="/" className="flex items-center gap-3">
             <span className="text-2xl font-black italic font-headline text-primary glow-text-primary tracking-tighter uppercase">HARIMAU</span>
          </Link>
        </div>
        
        <div className="flex-grow flex items-center px-8 gap-4 overflow-hidden">
          <div className="text-[10px] font-label text-outline uppercase tracking-widest whitespace-nowrap">MISSION_ID:</div>
          <div className="text-[10px] font-mono text-secondary truncate max-w-[200px]">{id}</div>
          <div className="hidden md:block text-[10px] font-label text-outline uppercase tracking-widest ml-4">IOC:</div>
          <div className="hidden md:block text-[10px] font-mono text-primary font-black">{job?.ioc}</div>
        </div>

        <div className="flex items-center px-6 gap-6 border-l border-outline-variant/30">
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
          <Link href="/" className="font-headline text-secondary/60 hover:text-primary transition-colors uppercase tracking-widest text-[10px]">Close_Mission</Link>
          <div className="w-8 h-8 border border-primary grayscale relative overflow-hidden">
            <Image src="/avatar.jpeg" alt="Hunter" fill className="object-cover" />
          </div>
        </div>
      </header>

      <main className="pt-24 px-8 pb-12 flex-grow overflow-y-auto">
        {jobStatus === "running" ? (
          /* Tactical Loading State */
          <div className="flex flex-col items-center justify-center h-[70vh] gap-12 max-w-2xl mx-auto">
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

            <div className="flex gap-4">
               {[1,2,3].map(i => (
                 <div key={i} className="w-12 h-1 bg-outline-variant/30 relative overflow-hidden">
                    <div className="absolute inset-0 bg-secondary transition-all duration-1000 ease-in-out animate-shimmer" style={{ animationDelay: `${i * 0.3}s` }}></div>
                 </div>
               ))}
            </div>
          </div>
        ) : (
          /* Tectonic Plates Layout */
          <div className="grid grid-cols-12 gap-8 auto-rows-auto">
            {tiles.map((tile) => (
              <div
                key={tile.id}
                className={`${tile.size} bg-surface-container-low border-t-2 border-outline-variant/30 p-6 relative group hover:border-primary/50 transition-colors flex flex-col`}
                style={{ height: tile.isGraph ? '600px' : 'auto', minHeight: '250px' }}
              >
                <div className="flex justify-between items-start mb-6">
                  <div className="flex flex-col">
                    <span className="text-[8px] font-label text-outline uppercase tracking-[0.3em] mb-1">Sector_0{tile.id}</span>
                    <h3 className="font-headline text-xl font-black text-foreground uppercase tracking-tighter italic group-hover:text-primary transition-colors">{tile.title}</h3>
                  </div>
                  <span className="material-symbols-outlined text-secondary text-xl opacity-30 group-hover:opacity-100 transition-opacity">{tile.icon}</span>
                </div>

                {tile.isGraph ? (
                  <div className="flex-grow relative bg-surface-container-lowest/50 border border-outline-variant/20">
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
                ) : tile.isTriage && tile.content ? (
                   <div className="flex flex-col gap-6">
                      <div className="grid grid-cols-2 gap-4">
                        <div className="bg-surface-container-lowest p-4 border-l-2 border-primary">
                           <div className="text-[9px] font-label text-outline uppercase mb-1">Risk_Level</div>
                           <div className={`text-2xl font-headline font-black italic ${(tile.content as any).verdict === 'MALICIOUS' ? 'text-primary' : 'text-secondary'}`}>{(tile.content as any).verdict}</div>
                        </div>
                        <div className="bg-surface-container-lowest p-4 border-l-2 border-secondary">
                           <div className="text-[9px] font-label text-outline uppercase mb-1">GTI_Score</div>
                           <div className="text-2xl font-headline font-black text-foreground">{(tile.content as any).score}<span className="text-xs text-outline ml-1">/100</span></div>
                        </div>
                      </div>
                      <p className="text-xs text-outline/80 font-body leading-relaxed italic">"{(tile.content as any).summary}"</p>
                      
                      <div className="mt-4 flex flex-col gap-2">
                        <div className="flex justify-between text-[8px] font-label uppercase">
                           <span className="text-outline">Detections_Ratio</span>
                           <span className="text-secondary">{(tile.content as any).malicious}/{(tile.content as any).total}</span>
                        </div>
                        <div className="w-full h-1 bg-surface-container-highest">
                           <div className="h-full bg-primary" style={{ width: `${Math.min(((tile.content as any).malicious / ((tile.content as any).total || 1)) * 100, 100)}%` }}></div>
                        </div>
                      </div>
                   </div>
                ) : tile.isReports ? (
                   <div className="flex flex-col gap-4 max-h-[400px] overflow-y-auto pr-2 scrollbar-hide">
                      {job?.specialist_results ? Object.entries(job.specialist_results).map(([agent, result]: [string, any]) => (
                        <button 
                          key={agent}
                          onClick={() => setExpandedTile(3)}
                          className="w-full text-left bg-surface-container-lowest p-4 border-l-2 border-outline-variant hover:border-secondary transition-colors"
                        >
                           <div className="flex justify-between items-center mb-1">
                             <span className="text-[10px] font-headline font-black text-foreground uppercase">{agent.replace('_', ' ')}</span>
                             <span className={`text-[8px] font-label uppercase ${result.verdict === 'MALICIOUS' ? 'text-primary' : 'text-secondary'}`}>{result.verdict}</span>
                           </div>
                           <div className="text-[9px] text-outline truncate">{result.summary || "View detailed briefing..."}</div>
                        </button>
                      )) : <div className="text-[10px] text-outline/40 italic uppercase tracking-widest">Awaiting_Specialist_Inputs...</div>}
                   </div>
                ) : tile.isFinalReport ? (
                   <div className="bg-surface-container-lowest p-8 border border-outline-variant/20 relative">
                      <div className="absolute top-0 left-0 px-2 py-1 bg-primary text-on-primary text-[8px] font-black uppercase tracking-widest">Consolidated_Intel</div>
                      <div className="max-h-[500px] overflow-y-auto pr-4 custom-scrollbar">
                        <Typewriter text={job?.final_report || "Report generation in progress..."} speed={2} />
                      </div>
                   </div>
                ) : tile.isTimeline ? (
                   <div className="space-y-4 max-h-[350px] overflow-y-auto pr-2 scrollbar-hide">
                      {job?.subtasks?.map((task: any, idx: number) => (
                        <div key={idx} className="flex gap-4 items-start bg-surface-container-lowest p-3 border-l border-outline-variant">
                           <div className="text-[8px] font-mono text-primary mt-1">{task.timestamp || "T+0s"}</div>
                           <div className="flex flex-col gap-1">
                             <div className="text-[9px] font-headline font-black text-foreground uppercase tracking-widest">{task.agent}</div>
                             <div className="text-[10px] text-outline leading-tight">{task.task}</div>
                           </div>
                        </div>
                      ))}
                   </div>
                ) : tile.isTransparency ? (
                   <div className="bg-surface-container-lowest p-4 font-mono text-[9px] text-outline/60 space-y-2 max-h-[350px] overflow-y-auto custom-scrollbar">
                      {job?.transparency_log?.map((event: any, idx: number) => (
                        <div key={idx} className="border-b border-outline-variant/10 pb-2">
                           <span className="text-secondary/40">[{event.timestamp}]</span> <span className="text-primary/60">{event.agent}</span>: {event.type === 'tool' ? `INVOKE_${event.tool}` : `THINK_${(event.thought || "").substring(0, 50)}...`}
                        </div>
                      ))}
                   </div>
                ) : null}

                <div className="mt-6 flex items-center justify-between">
                   <div className="flex gap-1">
                      <div className="w-1 h-1 bg-secondary/30"></div>
                      <div className="w-1 h-1 bg-secondary/30"></div>
                      <div className="w-4 h-1 bg-primary/30"></div>
                   </div>
                   <button onClick={() => setExpandedTile(tile.id)} className="text-[8px] font-label text-primary uppercase tracking-[0.2em] hover:text-secondary transition-colors">Expand_Sector</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Fullscreen Modal Overlays */}
      {expandedTile !== null && (
        <div className="fixed inset-0 z-[100] bg-surface/95 backdrop-blur-3xl flex items-center justify-center p-12" onClick={() => setExpandedTile(null)}>
          <div className="bg-surface-container-low border-2 border-primary w-full max-w-6xl h-full relative overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="p-8 border-b border-outline-variant/30 flex justify-between items-center bg-surface-container">
               <div className="flex flex-col">
                 <span className="text-[10px] font-label text-outline uppercase tracking-[0.4em] mb-1">Detail_Inspection_Mode</span>
                 <h2 className="font-headline text-3xl font-black text-primary uppercase tracking-tighter italic glow-text-primary">
                    {tiles.find(t => t.id === expandedTile)?.title}
                 </h2>
               </div>
               <button onClick={() => setExpandedTile(null)} className="material-symbols-outlined text-4xl text-secondary hover:text-primary transition-colors">close</button>
            </div>
            
            <div className="flex-grow overflow-y-auto p-12 custom-scrollbar">
               {expandedTile === 3 && (
                 <div className="space-y-12">
                   {job?.specialist_results ? Object.entries(job.specialist_results).map(([agent, result]: [string, any]) => (
                     <div key={agent} className="bg-surface-container-lowest border border-outline-variant/20 p-8 relative">
                        <div className="absolute top-0 right-0 px-3 py-1 bg-secondary text-surface text-[10px] font-black uppercase tracking-widest">{agent}</div>
                        <div className="mb-6 flex items-center gap-4">
                           <div className={`px-3 py-1 text-[10px] font-black uppercase ${result.verdict === 'MALICIOUS' ? 'bg-primary text-on-primary' : 'bg-secondary text-on-secondary'}`}>{result.verdict}</div>
                        </div>
                        <MarkdownRenderer content={result.markdown_report || "MISSING_DATA"} />
                     </div>
                   )) : <div className="text-outline italic uppercase tracking-widest">Awaiting_Briefings...</div>}
                 </div>
               )}
               
               {expandedTile === 1 && (
                  <div className="space-y-12">
                     <div className="bg-surface-container-lowest border border-outline-variant/20 p-8">
                        <h3 className="text-xl font-headline font-black text-secondary uppercase mb-6 tracking-tighter italic">Analytical_Triage_Summary</h3>
                        <MarkdownRenderer content={job?.rich_intel?.triage_analysis?.markdown_report || "NO_SUMMARY"} />
                     </div>
                     <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {job?.subtasks?.map((task: any, idx: number) => (
                           <div key={idx} className="bg-surface-container p-6 border-l-4 border-primary shadow-xl">
                              <div className="flex justify-between items-center mb-3">
                                 <span className="text-xs font-headline font-black text-foreground uppercase">{task.agent}</span>
                                 <span className="text-[10px] font-label text-secondary uppercase">{task.status}</span>
                              </div>
                              <p className="text-xs text-outline leading-relaxed">{task.task}</p>
                           </div>
                        ))}
                     </div>
                  </div>
               )}

               {expandedTile === 4 && (
                  <div className="max-w-4xl mx-auto bg-surface-container-lowest p-12 border border-outline-variant/30 shadow-[0_0_100px_rgba(255,124,245,0.1)]">
                     <MarkdownRenderer content={job?.final_report || "GENERATING_REPORT..."} />
                  </div>
               )}
               
               {/* Default fallback for other tiles */}
               {[2, 5, 6].includes(expandedTile) && (
                  <div className="text-outline uppercase tracking-widest text-center mt-20 italic">Section_Display_Locked_To_Main_HUD</div>
               )}
            </div>
          </div>
        </div>
      )}

      {/* Footer Meta */}
      <footer className="fixed bottom-0 left-0 w-full h-8 border-t border-outline-variant/30 bg-surface/90 backdrop-blur-md z-40 flex items-center justify-between px-6 text-[8px] font-label text-outline uppercase tracking-[0.2em]">
        <div>Harimau_System_Link: <span className="text-secondary">Connected</span></div>
        <div className="flex gap-4">
           <span>Lat: {progress}%_Sync</span>
           <span className="text-primary font-black animate-pulse">Live_Feed</span>
        </div>
      </footer>
    </div>
  );
}
