"use client";

import Image from "next/image";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useRef, ChangeEvent } from "react";
import { Background, Controls, MiniMap, ReactFlow, useNodesState, useEdgesState } from "@xyflow/react";
import { forceSimulation, forceLink, forceManyBody, forceCollide, forceX, forceY } from "d3-force";
import "@xyflow/react/dist/style.css";

// Define TypeScript interfaces for the API response
interface BackendNode {
  id: string;
  label: string;
  color: string;
  size: number;
  title?: string;
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
  // SSE / polling state
  const [jobStatus, setJobStatus] = useState<string>("running");
  const [progress, setProgress] = useState<number>(0);
  const [statusMessage, setStatusMessage] = useState<string>("Connecting to investigation stream...");
  const [activityLog, setActivityLog] = useState<string[]>([]);
  // Jobs history dropdown
  const [recentJobs, setRecentJobs] = useState<any[]>([]);
  // Physics simulation ref — persists across renders, cleaned up on unmount
  const simulationRef = useRef<any>(null);

  useEffect(() => {
    if (!id) return;

    // Fetch past jobs for the history dropdown (independent of the main investigation useEffect)
    fetch("/api/investigations")
      .then((r) => r.json())
      .then((jobs) => setRecentJobs(Array.isArray(jobs) ? jobs : []))
      .catch(() => setRecentJobs([]));

    let pollInterval: ReturnType<typeof setInterval> | null = null;
    let eventSource: EventSource | null = null;

    // Shared function: fetch full job + graph data and update state.
    // Returns the job status string so the caller can decide whether to keep polling.
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

        // Only build graph if the response has nodes
        if (graphRes.ok) {
          const graphData: GraphData = await graphRes.json();
          if (graphData.nodes?.length > 0) {
            // Stop any previous simulation before starting a new one
            if (simulationRef.current) {
              simulationRef.current.stop();
              simulationRef.current = null;
            }

            setNodes((currentNodes) => {
              const existingPositions = new Map(currentNodes.map((n) => [n.id, n.position]));

              // Build d3 sim nodes — pin only the root node at center so the graph has a stable anchor
              const simNodes: any[] = graphData.nodes.map((n) => {
                const pos = existingPositions.get(n.id);
                const isRoot = n.id === "root";
                return {
                  id: n.id,
                  x: pos?.x ?? (Math.random() - 0.5) * 500,
                  y: pos?.y ?? (Math.random() - 0.5) * 500,
                  radius: n.size,
                  // Root is fixed at origin — mirrors old Streamlit behaviour
                  fx: isRoot ? 0 : undefined,
                  fy: isRoot ? 0 : undefined,
                };
              });

              const simEdges = graphData.edges.map((e) => ({ source: e.source, target: e.target }));
              // O(1) lookup per tick instead of O(n) find
              const simNodeMap = new Map<string, any>(simNodes.map((n) => [n.id, n]));

              const simulation = forceSimulation(simNodes)
                // Weak spring (0.08) matches old ForceAtlas2 springConstant — keeps edges loose and organic
                .force("link", forceLink(simEdges).id((d: any) => d.id).distance(200).strength(0.08))
                .force("charge", forceManyBody().strength(-600).distanceMax(500))
                .force("collide", forceCollide().radius((d: any) => d.radius + 15).strength(0.9))
                // Weak centering gravity — keeps non-root nodes from drifting too far
                .force("x", forceX(0).strength(0.04))
                .force("y", forceY(0).strength(0.04))
                .alphaDecay(0.015)
                .velocityDecay(0.4); // matches old damping: 0.4

              // Pre-stabilise 100 ticks silently so nodes don't appear in chaotic scatter
              simulation.stop();
              for (let i = 0; i < 100; i++) simulation.tick();

              // Resume live animation from the pre-stabilised positions
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

              // Return pre-stabilised initial positions
              return graphData.nodes.map((n) => {
                const sim = simNodeMap.get(n.id)!;
                const isRoot = n.id === "root";
                return {
                  id: n.id,
                  position: { x: sim.x, y: sim.y },
                  data: { label: n.label },
                  style: {
                    background: n.color,
                    color: "#fff",
                    border: isRoot ? "2px solid #fff" : "1px solid rgba(255,255,255,0.2)",
                    borderRadius: "50%",
                    width: n.size * 2,
                    height: n.size * 2,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: isRoot ? "12px" : "10px",
                    fontWeight: isRoot ? ("bold" as const) : ("normal" as const),
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
              style: { stroke: "#00fbfb", strokeWidth: 1 },
              labelStyle: { fill: "#adaaad", fontSize: "10px" },
              labelBgStyle: { fill: "#19191c", fillOpacity: 0.8 },
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

    // Fallback: poll every 10 seconds (mirrors Streamlit's 10s polling interval)
    const startPolling = () => {
      let pollCount = 0;
      const MAX_POLLS = 150; // 25 minutes max
      setStatusMessage("Real-time stream unavailable. Polling every 10 seconds...");
      pollInterval = setInterval(async () => {
        pollCount++;
        const elapsed = pollCount * 10;
        const estimatedDuration = 510; // ~8.5 min average
        const estimatedProgress = Math.min(Math.round((elapsed / estimatedDuration) * 100), 95);
        setProgress(estimatedProgress);
        setStatusMessage(`Polling... elapsed: ${elapsed}s`);

        const status = await refetch();
        if (status === "completed" || status === "failed" || pollCount >= MAX_POLLS) {
          if (pollInterval) clearInterval(pollInterval);
          setProgress(100);
          setStatusMessage(status === "completed" ? "Investigation complete!" : "Investigation failed.");
        }
      }, 10_000);
    };

    // 1. Initial fetch to pick up status (handles page refresh on a completed job)
    refetch().then((status) => {
      if (status === "completed" || status === "failed") {
        setProgress(100);
        setStatusMessage(status === "completed" ? "Investigation complete!" : "Investigation failed.");
        return; // Already done — no SSE needed
      }

      // 2. Open SSE stream (mirrors api_client.py stream_investigation_events)
      setStatusMessage("Connecting to real-time event stream...");
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
            setStatusMessage("Investigation complete!");
            await refetch();
            eventSource?.close();
          } else if (eventType === "investigation_failed") {
            setProgress(100);
            setStatusMessage(`Investigation failed: ${data.error ?? "Unknown error"}`);
            await refetch();
            eventSource?.close();
          } else if (eventType === "tool_invocation") {
            const tool: string = data.tool ?? "unknown";
            setActivityLog((prev) => [`🔧 ${agent}: calling ${tool}`, ...prev].slice(0, 20));
          } else if (eventType === "agent_reasoning") {
            setActivityLog((prev) => [`💭 ${agent}: reasoning (${(data.thought ?? "").length} chars)`, ...prev].slice(0, 20));
          } else if (eventType.includes("_started")) {
            setStatusMessage(`🤖 ${msg || agent}`);
          } else if (eventType.includes("_completed")) {
            setStatusMessage(`✅ ${msg || agent}`);
            if (agent) setActivityLog((prev) => [`✅ ${agent}: completed`, ...prev].slice(0, 20));
          } else {
            if (msg) setStatusMessage(msg);
          }
        } catch (parseErr) {
          console.warn("SSE parse error:", parseErr);
        }
      };

      // 3. If SSE errors, fall back to polling (same as Streamlit fallback)
      eventSource.onerror = () => {
        console.warn("SSE connection failed, falling back to polling");
        eventSource?.close();
        startPolling();
      };
    });

    // Cleanup on unmount
    return () => {
      eventSource?.close();
      if (pollInterval) clearInterval(pollInterval);
      simulationRef.current?.stop();
    };
  }, [id]);

  const tiles = [
    {
      id: 1,
      title: "Triage & Plan",
      icon: "radar",
      size: "col-span-12 lg:col-span-5",
      content: job
        ? `Status: ${job.status}\nVerdict: ${job.risk_level || "Unknown"}\nScore: ${job.gti_score || "N/A"}`
        : "Loading triage data...",
    },
    {
      id: 2,
      title: "Graph",
      icon: "hub",
      size: "col-span-12 lg:col-span-7 row-span-2",
      content: "Interactive visualization using React Flow.",
      isGraph: true,
    },
    {
      id: 3,
      title: "Specialist Reports",
      icon: "reorder",
      size: "col-span-12 lg:col-span-5",
      content:
        job && job.specialist_results
          ? `Reports found: ${Object.keys(job.specialist_results).length}`
          : "Loading specialist reports...",
    },
    {
      id: 4,
      title: "Final Report",
      icon: "description",
      size: "col-span-12 lg:col-span-6",
      content: job
        ? job.final_report?.substring(0, 100) + "..."
        : "Loading final report...",
    },
    {
      id: 5,
      title: "Timeline",
      icon: "history",
      size: "col-span-12 lg:col-span-3",
      content:
        job && job.subtasks
          ? `Tasks executed: ${job.subtasks.length}`
          : "Loading timeline...",
    },
    {
      id: 6,
      title: "Agent Transparency",
      icon: "terminal",
      size: "col-span-12 lg:col-span-3",
      content:
        job && job.transparency_log
          ? `Events logged: ${job.transparency_log.length}`
          : "Loading transparency log...",
    },
  ];

  return (
    <div className="font-body selection:bg-pink-500 selection:text-white min-h-screen bg-[#0e0e10] text-[#fffbfe] relative flex flex-col justify-between">
      {/* TopNavBar */}
      <header className="fixed top-0 left-0 w-full z-50 bg-[#0e0e10]/80 backdrop-blur-xl border-b-2 border-secondary/30 flex justify-between items-center px-6 py-4 shadow-[0_0_40px_rgba(255,124,245,0.15)]">
        <div className="flex items-center gap-8">
          <span className="text-3xl font-black italic text-pink-500 drop-shadow-[0_0_10px_rgba(255,0,255,0.8)] font-headline tracking-tighter uppercase">
            HARIMAU
          </span>
          <nav className="hidden md:flex space-x-8">
            <a
              className="text-cyan-400/60 hover:text-yellow-400 font-headline tracking-tighter uppercase"
              href="/"
            >
              HUNT
            </a>
            <a
              className="text-pink-500 border-b-4 border-pink-500 pb-2 font-headline tracking-tighter uppercase"
              href="#"
            >
              INVESTIGATE
            </a>
            <a
              className="text-cyan-400/60 hover:text-yellow-400 font-headline tracking-tighter uppercase"
              href="#"
            >
              INTEL
            </a>
          </nav>
        </div>
        <div className="flex items-center gap-6">
          <div className="relative group hidden lg:block">
            <select
              className="relative bg-[#19191c] border-b-2 border-pink-500 text-pink-500 text-xs px-4 py-2 focus:ring-0 w-48 font-label cursor-pointer appearance-none"
              value={id}
              onChange={(e: ChangeEvent<HTMLSelectElement>) => {
                if (e.target.value && e.target.value !== id)
                  router.push(`/investigate/${e.target.value}`);
              }}
            >
              <option value={id}>
                {recentJobs.length > 0 ? "Recent Jobs..." : "Loading jobs..."}
              </option>
              {recentJobs.map((j: any) => (
                <option key={j.job_id} value={j.job_id}>
                  {j.ioc} — {j.status}
                </option>
              ))}
            </select>
            <span className="absolute right-2 top-2.5 text-pink-500 material-symbols-outlined text-sm pointer-events-none">
              arrow_drop_down
            </span>
          </div>

          <div className="flex gap-4">
            <span className="material-symbols-outlined text-cyan-400 hover:text-pink-500 cursor-pointer">
              terminal
            </span>
            <span className="material-symbols-outlined text-cyan-400 hover:text-pink-500 cursor-pointer">
              settings
            </span>
            <div className="w-10 h-10 border-2 border-pink-500 grayscale hover:grayscale-0 relative">
              <Image
                alt="Hunter Avatar"
                className="object-cover"
                fill
                sizes="40px"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuDVO5RrZ_clVGo5R6WzaccYn2MJ3LQTRkkWvGK5vizCrU_thqz1SiFYLudUQ6sYCsqcDhTrkec5EvX-bRmtSGux9MaBkOB_gayBp2eKFQdfu6csogWVfUkNuHq86X7uCEC-tDEsxXPO5gZc_BVjrR9ZCp012Owd8NMOBtinGnJPRj-Ya94qHL1or_JA4BUqeP2lC4u9Oy5_WiiFhga8cPaCU9cqLykjM10gFgTDIFC2FV_rQ3HBhUagliiRW93-i_-bjoPw--xucsI-"
              />
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area (Scrollable grid) */}
      <main className="pt-24 px-6 pb-28 flex-grow overflow-y-auto">

        {/* Running State — shown while investigation is in progress */}
        {jobStatus === "running" && (
          <div className="flex flex-col items-center justify-center min-h-[70vh] gap-8">
            {/* IOC being investigated */}
            <div className="text-center">
              <p className="font-label text-xs text-cyan-400/60 uppercase mb-1">Investigating</p>
              <h2 className="font-headline text-2xl font-black text-pink-500 uppercase tracking-tighter">
                {job?.ioc ?? id}
              </h2>
            </div>

            {/* Progress bar */}
            <div className="w-full max-w-xl">
              <div className="flex justify-between items-center mb-2">
                <span className="font-label text-xs text-cyan-400/60 uppercase">Progress</span>
                <span className="font-label text-xs text-pink-500">{progress}%</span>
              </div>
              <div className="w-full h-1 bg-[#19191c] border border-cyan-400/20">
                <div
                  className="h-full bg-pink-500 transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {/* Status message */}
            <p className="font-label text-sm text-cyan-400 text-center max-w-xl">{statusMessage}</p>

            {/* Agent activity log (last 10 entries) */}
            {activityLog.length > 0 && (
              <div className="w-full max-w-xl bg-[#19191c] border border-cyan-400/20 p-4 space-y-1 max-h-48 overflow-y-auto">
                <p className="font-label text-[10px] text-cyan-400/40 uppercase mb-2">Agent Activity</p>
                {activityLog.map((entry, i) => (
                  <p key={i} className="font-mono text-[11px] text-[#adaaad]">{entry}</p>
                ))}
              </div>
            )}

            {/* Animated pulse indicator */}
            <div className="flex gap-2">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="w-2 h-2 bg-pink-500 rounded-full animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
          </div>
        )}

        {/* Results grid — shown once investigation is completed or failed */}
        {jobStatus !== "running" && (
          <div className="grid grid-cols-12 gap-6 auto-rows-[250px]">
            {tiles.map((tile) => (
              <div
                className={`${tile.size} bg-[#19191c] p-6 border-l-4 pulse-border cursor-pointer hover:bg-[#262529] transition-all flex flex-col justify-between h-full`}
                key={tile.id}
                onClick={() => setExpandedTile(tile.id)}
              >
                <div className="flex justify-between items-start">
                  <h3 className="font-headline text-xl font-black text-[#fffbfe] uppercase italic">
                    {tile.title}
                  </h3>
                  <span className="text-cyan-400 material-symbols-outlined text-2xl">
                    {tile.icon}
                  </span>
                </div>

                {/* Render Graph if it is the graph tile */}
                {tile.isGraph ? (
                  <div className="flex-grow w-full h-full min-h-[400px] mt-4 relative bg-[#0e0e10]/50 border border-cyan-400/20">
                    {/* Hide ReactFlow connection handles — we don't want visible anchor dots */}
                    <style>{`.react-flow__handle { opacity: 0 !important; pointer-events: none !important; }`}</style>
                    {loading ? (
                      <div className="absolute inset-0 flex items-center justify-center text-cyan-400 font-label text-xs">
                        LOADING_GRAPH_DATA...
                      </div>
                    ) : (
                      <ReactFlow
                        edges={edges}
                        fitView
                        nodes={nodes}
                        nodesConnectable={false}
                        onEdgesChange={onEdgesChange}
                        onNodesChange={onNodesChange}
                      >
                        <Background color="#00fbfb" gap={16} size={1} />
                        <Controls />
                        <MiniMap
                          nodeColor={(n: any) => n.style?.background || "#19191c"}
                        />
                      </ReactFlow>
                    )}
                  </div>
                ) : (
                  <p className="font-label text-xs text-cyan-400/60 mt-2">
                    {tile.content}
                  </p>
                )}

                <div className="mt-auto text-[10px] font-label text-pink-500 text-right uppercase">
                  Click to expand
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Overlay */}
      {expandedTile !== null && (
        <div
          className="fixed inset-0 bg-[#0e0e10]/95 backdrop-blur-xl z-[100] flex items-center justify-center p-6"
          onClick={() => setExpandedTile(null)}
        >
          <div
            className="bg-[#19191c] border-2 border-pink-500 p-8 w-11/12 h-[90vh] overflow-y-auto relative"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="absolute top-4 right-4 text-cyan-400 hover:text-pink-500 material-symbols-outlined text-3xl"
              onClick={() => setExpandedTile(null)}
            >
              close
            </button>
            <h2 className="font-headline text-4xl font-black text-pink-500 uppercase mb-6 italic">
              {tiles.find((t) => t.id === expandedTile)?.title}
            </h2>
            <div className="font-body text-[#adaaad] text-sm space-y-4 h-full">
              {/* If expanding graph, show it larger */}
              {tiles.find((t) => t.id === expandedTile)?.isGraph ? (
                <div className="w-full h-[70vh] bg-[#0e0e10]/50 border border-cyan-400/20">
                  <ReactFlow
                    edges={edges}
                    fitView
                    nodes={nodes}
                    nodesConnectable={false}
                    onEdgesChange={onEdgesChange}
                    onNodesChange={onNodesChange}
                  >
                    <Background color="#00fbfb" gap={16} size={1} />
                    <Controls />
                    <MiniMap
                      nodeColor={(n: any) => n.style?.background || "#19191c"}
                    />
                  </ReactFlow>
                </div>
              ) : (
                <>
                  {expandedTile === 1 && (
                    <div className="space-y-4">
                      <section>
                        <h3 className="text-xl font-headline font-black text-pink-500 uppercase mb-2">
                          Triage Summary
                        </h3>
                        <p className="text-sm text-[#adaaad] font-body whitespace-pre-wrap">
                          {job?.rich_intel?.triage_summary || "No summary available."}
                        </p>
                      </section>
                      <section>
                        <h3 className="text-xl font-headline font-black text-pink-500 uppercase mb-2">
                          Generated Tasks
                        </h3>
                        <ul className="space-y-2">
                          {job?.subtasks?.map((task: any, idx: number) => (
                            <li
                              className="bg-[#19191c] p-4 border-l-2 border-cyan-400"
                              key={idx}
                            >
                              <div className="flex justify-between items-center mb-1">
                                <strong className="font-headline text-[#fffbfe] uppercase tracking-tighter">
                                  {task.agent}
                                </strong>
                                <span
                                  className={`text-xs font-label uppercase ${task.status === "completed" ? "text-green-400" : "text-yellow-400"}`}
                                >
                                  {task.status}
                                </span>
                              </div>
                              <p className="text-xs text-[#adaaad]">
                                {task.task}
                              </p>
                            </li>
                          ))}
                        </ul>
                      </section>
                    </div>
                  )}
                  {expandedTile === 3 && (
                    <div className="space-y-6">
                      <h3 className="text-xl font-headline font-black text-pink-500 uppercase mb-4">
                        Specialist Reports
                      </h3>
                      {job?.specialist_results ? (
                        Object.entries(job.specialist_results).map(
                          ([agent, result]: [string, any]) => (
                            <div
                              key={agent}
                              className="bg-[#19191c] p-6 border-l-2 border-cyan-400"
                            >
                              <div className="flex justify-between items-center mb-4">
                                <h4 className="font-headline text-lg font-black text-[#fffbfe] uppercase tracking-tighter">
                                  {agent.replace("_", " ").toUpperCase()}
                                </h4>
                                <span
                                  className={`text-xs font-label uppercase ${result.verdict?.toUpperCase() === "MALICIOUS" ? "text-pink-500" : result.verdict?.toUpperCase() === "SUSPICIOUS" ? "text-yellow-400" : "text-green-400"}`}
                                >
                                  {result.verdict || "N/A"}
                                </span>
                              </div>
                              <pre className="whitespace-pre-wrap text-[11px] leading-relaxed text-[#adaaad] font-mono bg-[#0e0e10] p-4 border border-cyan-400/20">
                                {result.markdown_report || "No report content."}
                              </pre>
                            </div>
                          ),
                        )
                      ) : (
                        <p className="text-sm text-[#adaaad]">
                          No specialist reports available.
                        </p>
                      )}
                    </div>
                  )}
                  {expandedTile === 4 && (
                    <div className="space-y-4">
                      <h3 className="text-xl font-headline font-black text-pink-500 uppercase mb-4">
                        Final Intelligence Report
                      </h3>
                      <div className="bg-[#19191c] p-6 border-l-2 border-cyan-400">
                        <pre className="whitespace-pre-wrap text-xs leading-relaxed text-[#adaaad] font-mono bg-[#0e0e10] p-4 border border-cyan-400/20">
                          {job?.final_report || "No report available."}
                        </pre>
                      </div>
                    </div>
                  )}
                  {expandedTile === 5 && (
                    <div className="space-y-4">
                      <h3 className="text-xl font-headline font-black text-pink-500 uppercase mb-4">
                        Investigation Timeline
                      </h3>
                      <div className="space-y-4">
                        {job?.subtasks?.map((task: any, idx: number) => (
                          <div
                            className="flex gap-4 items-center bg-[#19191c] p-4 border-l-2 border-cyan-400"
                            key={idx}
                          >
                            <span className="text-pink-500 font-label text-xs">
                              {task.timestamp || "N/A"}
                            </span>
                            <span className="bg-[#0e0e10] px-2 py-1 text-xs font-label text-cyan-400 uppercase">
                              {task.agent}
                            </span>
                            <span className="text-xs text-[#fffbfe] flex-grow">
                              {task.task}
                            </span>
                            <span
                              className={`text-xs font-label uppercase ${task.status === "completed" ? "text-green-400" : "text-yellow-400"}`}
                            >
                              {task.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {expandedTile === 6 && (
                    <div className="space-y-4">
                      <h3 className="text-xl font-headline font-black text-pink-500 uppercase mb-4">
                        Agent Transparency Log
                      </h3>
                      <div className="space-y-2">
                        {job?.transparency_log?.map(
                          (event: any, idx: number) => (
                            <div
                              className="bg-[#19191c] p-4 border-l-2 border-pink-500 text-xs"
                              key={idx}
                            >
                              <div className="flex gap-2 items-center mb-1">
                                <span className="text-cyan-400 font-label text-[10px]">
                                  {event.timestamp}
                                </span>
                                <span className="bg-[#0e0e10] px-1.5 py-0.5 text-[10px] font-label text-pink-500 uppercase">
                                  {event.agent}
                                </span>
                              </div>
                              <p className="text-[#adaaad]">
                                {event.type === "tool"
                                  ? `Used tool: ${event.tool}`
                                  : `Thought: ${event.thought}`}
                              </p>
                            </div>
                          ),
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Background Grid Lines */}
      <div className="fixed inset-0 pointer-events-none z-[-1] opacity-[0.03]">
        <div
          className="h-full w-full"
          style={{
            backgroundImage:
              "linear-gradient(#00fbfb 1px, transparent 1px), linear-gradient(90deg, #00fbfb 1px, transparent 1px)",
            backgroundSize: "100px 100px",
          }}
        ></div>
      </div>
    </div>
  );
}
