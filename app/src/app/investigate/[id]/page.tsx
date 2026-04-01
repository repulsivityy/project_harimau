"use client";

import Image from "next/image";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow } from "@xyflow/react";
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

  const [expandedTile, setExpandedTile] = useState<number | null>(null);
  const [nodes, setNodes] = useState<any[]>([]);
  const [edges, setEdges] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [job, setJob] = useState<any>(null);

  useEffect(() => {
    if (!id) return;

    const fetchData = async () => {
      setLoading(true);
      try {
        const [graphRes, jobRes] = await Promise.all([
          fetch(`/api/investigations/${id}/graph`),
          fetch(`/api/investigations/${id}`),
        ]);

        if (!graphRes.ok) {
          throw new Error("Failed to fetch graph data");
        }
        if (!jobRes.ok) {
          throw new Error("Failed to fetch job details");
        }

        const graphData: GraphData = await graphRes.json();
        const jobData = await jobRes.json();

        setJob(jobData);

        // Apply Circular Layout
        const calculatedNodes = graphData.nodes.map((node, index) => {
          // Central node 'root' or first node at (0,0)
          if (node.id === "root" || index === 0) {
            return {
              id: node.id,
              position: { x: 0, y: 0 },
              data: { label: node.label },
              style: {
                background: node.color,
                color: "#fff",
                border: "2px solid #fff",
                borderRadius: "50%",
                width: node.size * 2,
                height: node.size * 2,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "12px",
                fontWeight: "bold",
              },
            };
          }

          // Other nodes in a circle
          const radius = 250;
          const angle = (index / (graphData.nodes.length - 1)) * 2 * Math.PI;
          const x = radius * Math.cos(angle);
          const y = radius * Math.sin(angle);

          return {
            id: node.id,
            position: { x, y },
            data: { label: node.label },
            style: {
              background: node.color,
              color: "#fff",
              border: "1px solid rgba(255,255,255,0.2)",
              borderRadius: "50%",
              width: node.size * 2,
              height: node.size * 2,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "10px",
            },
          };
        });

        const calculatedEdges = graphData.edges.map((edge, index) => ({
          id: `e-${index}`,
          source: edge.source,
          target: edge.target,
          label: edge.label,
          style: { stroke: "#00fbfb", strokeWidth: 1 },
          labelStyle: { fill: "#adaaad", fontSize: "10px" },
          labelBgStyle: { fill: "#19191c", fillOpacity: 0.8 },
        }));

        setNodes(calculatedNodes);
        setEdges(calculatedEdges);
      } catch (error) {
        console.error("Error fetching data:", error);
        // Fallback mock data if API fails
        setNodes([
          {
            id: "root",
            position: { x: 0, y: 0 },
            data: { label: "Target IOC" },
            style: { border: "2px solid #FF4B4B", background: "#19191c" },
          },
          {
            id: "n1",
            position: { x: 150, y: 150 },
            data: { label: "Rel 1" },
            style: { border: "1px solid #00fbfb", background: "#19191c" },
          },
          {
            id: "n2",
            position: { x: -150, y: -150 },
            data: { label: "Rel 2" },
            style: { border: "1px solid #00fbfb", background: "#19191c" },
          },
        ]);
        setEdges([
          { id: "e1", source: "root", target: "n1", label: "communicates_with" },
          { id: "e2", source: "root", target: "n2", label: "resolved_to" },
        ]);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
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
      title: "Network Graph",
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
            <select className="relative bg-[#19191c] border-b-2 border-pink-500 text-pink-500 text-xs px-4 py-2 focus:ring-0 w-48 font-label cursor-pointer appearance-none">
              <option>JOBS_HISTORY...</option>
              <option>Job #1234 - Malicious</option>
              <option>Job #1233 - Suspicious</option>
              <option>Job #1232 - Benign</option>
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
                  {loading ? (
                    <div className="absolute inset-0 flex items-center justify-center text-cyan-400 font-label text-xs">
                      LOADING_GRAPH_DATA...
                    </div>
                  ) : (
                    <ReactFlow edges={edges} nodes={nodes}>
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
                  <ReactFlow edges={edges} nodes={nodes}>
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
                          <p className="text-sm text-[#adaaad] font-body">
                            {job?.rich_intel?.triage_summary ||
                              "No summary available."}
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
                                <pre className="whitespace-pre-wrap text-xs text-[#adaaad] font-mono bg-[#0e0e10] p-4 border border-cyan-400/20">
                                  {result.markdown_report ||
                                    "No report content."}
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
                          <pre className="whitespace-pre-wrap text-xs text-[#adaaad] font-mono bg-[#0e0e10] p-4 border border-cyan-400/20">
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
