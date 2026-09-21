"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { DossierJob } from "@/lib/dossier-types";

const DEPTH_LABELS: Record<number, { title: string; subtitle: string }> = {
  1: {
    title: "Surface Triage",
    subtitle: "Fast reputation lookup & initial GTI enrichment",
  },
  2: {
    title: "Standard Investigation",
    subtitle: "Multi-agent pivot across immediate infrastructure & relations",
  },
  3: {
    title: "Deep Static Analysis",
    subtitle: "Specialist Malware & Infrastructure sub-agent teardown",
  },
  4: {
    title: "Extended Campaign Hunt",
    subtitle: "Multi-hop graph expansion, decoy correlation & C2 clustering",
  },
  5: {
    title: "Full Exhaustive Forensics",
    subtitle: "Maximum recursion depth across all behavioral & network artifacts",
  },
};

export default function Home() {
  const router = useRouter();
  const [ioc, setIoc] = useState("");
  const [depth, setDepth] = useState(2);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [recentJobs, setRecentJobs] = useState<DossierJob[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);

  useEffect(() => {
    fetch("/api/investigations")
      .then((r) => r.json())
      .then((jobs) => setRecentJobs(Array.isArray(jobs) ? jobs : []))
      .catch(() => setRecentJobs([]))
      .finally(() => setIsLoadingHistory(false));
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = ioc.trim();
    if (!trimmed || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const response = await fetch("/api/investigate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ioc: trimmed, max_iterations: depth }),
      });

      if (!response.ok) {
        throw new Error("Failed to submit investigation");
      }

      const data = await response.json();
      const jobId = data.job_id;

      router.push(`/investigate/${jobId}`);
    } catch (error) {
      console.error("Error submitting investigation:", error);
      setErrorMessage("Failed to start investigation. Please verify backend connectivity and try again.");
      setIsSubmitting(false);
    }
  };

  const getRiskBadgeStyle = (risk?: string | null) => {
    const upper = (risk || "").toUpperCase();
    if (upper.includes("MALICIOUS") || upper.includes("CRITICAL") || upper.includes("HIGH")) {
      return "bg-rose-500/15 text-rose-300 border-rose-500/30";
    }
    if (upper.includes("SUSPICIOUS") || upper.includes("MEDIUM")) {
      return "bg-amber-500/15 text-amber-300 border-amber-500/30";
    }
    if (upper.includes("CLEAN") || upper.includes("BENIGN") || upper.includes("LOW")) {
      return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
    }
    return "bg-slate-800 text-slate-400 border-slate-700";
  };

  const getStatusBadgeStyle = (status?: string) => {
    const lower = (status || "").toLowerCase();
    if (lower === "completed") {
      return "bg-emerald-950/80 text-emerald-400 border-emerald-800/60";
    }
    if (lower === "running" || lower === "queued" || lower === "in_progress") {
      return "bg-teal-950/80 text-teal-300 border-teal-700/60";
    }
    if (lower === "failed" || lower === "error") {
      return "bg-rose-950/80 text-rose-400 border-rose-800/60";
    }
    return "bg-slate-900 text-slate-400 border-slate-800";
  };

  const currentDepthMeta = DEPTH_LABELS[depth] || DEPTH_LABELS[2];

  return (
    <div
      className="dossier-surface min-h-screen bg-[#080c14] text-slate-100 relative flex flex-col selection:bg-teal-500 selection:text-slate-950 overflow-x-hidden font-sans"
      style={{
        backgroundImage: "radial-gradient(rgba(255, 255, 255, 0.06) 1px, transparent 1px)",
        backgroundSize: "28px 28px",
      }}
    >
      {/* Subtle Ambient Radial Glows */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden z-0">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[760px] h-[380px] bg-teal-500/10 blur-[130px] rounded-full" />
        <div className="absolute bottom-0 right-1/4 w-[480px] h-[320px] bg-emerald-500/5 blur-[120px] rounded-full" />
      </div>

      {/* Backing Image (Harimau Tiger Logo) */}
      <div className="fixed inset-0 opacity-10 flex items-center justify-center pointer-events-none z-0">
        <Image
          src="/tiger_logo.png"
          alt="Harimau Tiger Logo"
          width={700}
          height={700}
          className="object-contain -translate-y-[12%] select-none drop-shadow-[0_0_45px_rgba(45,212,191,0.25)]"
          priority
        />
      </div>

      {/* Top Global App Header (Consistent with Threat Dossier Workbench) */}
      <header className="sticky top-0 z-40 h-14 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-slate-900 border border-teal-500/40 flex items-center justify-center overflow-hidden shadow-lg shadow-teal-500/15">
              <Image
                src="/tiger_logo.png"
                alt="Harimau Tiger"
                width={26}
                height={26}
                className="object-contain"
              />
            </div>
            <span className="font-bold text-sm tracking-wider text-white uppercase font-mono">
              HARIMAU
            </span>
          </Link>

          <div className="h-4 w-px bg-slate-800 hidden md:block" />

          <nav className="hidden md:flex items-center gap-5 text-xs font-mono uppercase tracking-wider">
            <Link
              href="/"
              className="text-teal-400 border-b-2 border-teal-400 pb-0.5 font-semibold transition-colors"
            >
              Hunt
            </Link>
            <Link
              href={recentJobs.length > 0 ? `/investigate/${recentJobs[0].job_id}` : "#"}
              className="text-slate-400 hover:text-teal-300 transition-colors"
            >
              Threat Dossier
            </Link>
          </nav>
        </div>

        <div className="flex items-center gap-3">
          {recentJobs.length > 0 && (
            <Link
              href={`/investigate/${recentJobs[0].job_id}`}
              className="px-3.5 py-1.5 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-teal-500/40 text-slate-300 hover:text-white flex items-center gap-2 transition-all"
            >
              <span>Latest Threat Dossier</span>
              <span className="text-teal-400">➔</span>
            </Link>
          )}
          <div className="w-8 h-8 rounded-full border border-slate-800 overflow-hidden bg-slate-900">
            <Image
              src="/avatar.jpeg"
              alt="Analyst Avatar"
              width={32}
              height={32}
              className="object-cover"
            />
          </div>
        </div>
      </header>

      {/* Main Content Container */}
      <main className="relative z-10 flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-12 sm:py-16 flex flex-col justify-between gap-12">
        {/* Hero & Search Section */}
        <div className="space-y-8 text-center">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-teal-950/70 border border-teal-800/60 text-teal-300 text-[11px] font-mono uppercase tracking-wider">
              <span className="w-1.5 h-1.5 rounded-full bg-teal-400" />
              <span>Autonomous Multi-Agent Threat Intelligence</span>
            </div>

            <h1 className="text-5xl sm:text-6xl md:text-7xl font-black tracking-tighter uppercase italic text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-100 to-teal-300">
              Harimau
            </h1>

            <p className="text-xs sm:text-sm text-slate-300 max-w-2xl mx-auto leading-relaxed font-mono">
              Inspired by the predatory tiger, Harimau is an automated threat intelligence system
              that utilizes a LangGraph-based multi-agent architecture to investigate IOCs.
              <br />
              <br />
              By mimicking human analyst workflows, it systematically analyzes malware and maps
              infrastructure to synthesize complex data into actionable Threat Dossiers.
            </p>
          </div>

          {/* Search Form */}
          <form onSubmit={handleSearch} className="space-y-5 text-left">
            <div className="p-2 rounded-2xl bg-slate-900/90 backdrop-blur-md border border-slate-800 focus-within:border-teal-500/60 focus-within:ring-4 focus-within:ring-teal-500/10 shadow-2xl transition-all flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <div className="flex items-center gap-3 flex-1 px-3 py-2">
                <svg
                  className="w-5 h-5 text-teal-400 shrink-0"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.3-4.3" />
                </svg>
                <input
                  type="text"
                  value={ioc}
                  onChange={(e) => setIoc(e.target.value)}
                  placeholder="Enter IOC (SHA-256, Domain, IPv4, or URL)..."
                  className="w-full bg-transparent text-slate-100 placeholder:text-slate-500 font-mono text-sm sm:text-base focus:outline-none"
                  disabled={isSubmitting}
                />
                {ioc && (
                  <button
                    type="button"
                    onClick={() => setIoc("")}
                    className="text-xs font-mono text-slate-500 hover:text-slate-300 px-1.5 py-0.5 rounded bg-slate-800/80"
                  >
                    ESC
                  </button>
                )}
              </div>

              <button
                type="submit"
                disabled={!ioc.trim() || isSubmitting}
                className="px-8 py-3.5 rounded-xl bg-gradient-to-r from-teal-500 to-emerald-600 hover:from-teal-400 hover:to-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-slate-950 font-black font-mono text-sm uppercase tracking-wider transition-all shadow-lg shadow-teal-500/20 flex items-center justify-center gap-2 shrink-0 cursor-pointer"
              >
                {isSubmitting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin" />
                    <span>HUNTING...</span>
                  </>
                ) : (
                  <>
                    <span>HUNT</span>
                    <span>➔</span>
                  </>
                )}
              </button>
            </div>

            {errorMessage && (
              <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs font-mono flex items-center justify-between">
                <span>{errorMessage}</span>
                <button
                  type="button"
                  onClick={() => setErrorMessage(null)}
                  className="text-rose-400 hover:text-white ml-4"
                >
                  ✕
                </button>
              </div>
            )}

            {/* Forensic Intensity / Recursion Depth Selector Card */}
            <div className="rounded-2xl bg-slate-900/60 backdrop-blur-sm border border-slate-800/80 p-4 sm:p-5 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold">
                    Forensic Intensity
                  </span>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-teal-950 text-teal-300 border border-teal-800/60 font-semibold">
                    Level {depth} / 5
                  </span>
                </div>
                <div className="text-xs text-slate-300 font-medium">
                  <span className="text-teal-400 font-semibold">{currentDepthMeta.title}:</span>{" "}
                  <span className="text-slate-400">{currentDepthMeta.subtitle}</span>
                </div>
              </div>

              <div className="grid grid-cols-5 gap-2 pt-1">
                {[1, 2, 3, 4, 5].map((lvl) => {
                  const isSelected = depth === lvl;
                  const isActive = lvl <= depth;
                  return (
                    <button
                      key={lvl}
                      type="button"
                      onClick={() => setDepth(lvl)}
                      className={`py-2 px-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                        isSelected
                          ? "bg-teal-500/15 border-teal-500/60 text-teal-200 shadow-sm shadow-teal-500/10"
                          : isActive
                            ? "bg-slate-900/90 border-teal-900/60 text-slate-300 hover:border-slate-700"
                            : "bg-slate-950/60 border-slate-800/70 text-slate-500 hover:border-slate-700 hover:text-slate-300"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[10px] font-mono font-bold uppercase">
                          Depth 0{lvl}
                        </span>
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            isActive ? "bg-teal-400" : "bg-slate-700"
                          }`}
                        />
                      </div>
                      <div className="text-[11px] font-medium truncate">
                        {DEPTH_LABELS[lvl].title}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </form>
        </div>

        {/* Recent Threat Dossiers Section */}
        <section className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2.5">
              <span className="w-2 h-2 rounded-full bg-teal-400" />
              <h2 className="text-xs font-mono uppercase tracking-wider font-bold text-slate-300">
                Recent Threat Dossiers
              </h2>
              {recentJobs.length > 0 && (
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-slate-400">
                  {recentJobs.length}
                </span>
              )}
            </div>
            <span className="text-[11px] font-mono text-slate-500">
              Select a case to open Threat Dossier &amp; Spatial Canvas
            </span>
          </div>

          <div className="rounded-2xl bg-slate-900/70 backdrop-blur-md border border-slate-800/90 divide-y divide-slate-800/70 overflow-hidden shadow-xl">
            {isLoadingHistory ? (
              <div className="p-8 text-center text-xs font-mono text-slate-500">
                Loading recent Threat Dossiers...
              </div>
            ) : recentJobs.length === 0 ? (
              <div className="p-8 text-center space-y-1">
                <p className="text-sm font-medium text-slate-300">
                  No Threat Dossiers recorded yet
                </p>
                <p className="text-xs text-slate-500">
                  Submit an indicator above to initiate your first autonomous investigation.
                </p>
              </div>
            ) : (
              recentJobs.slice(0, 6).map((job) => (
                <Link
                  key={job.job_id}
                  href={`/investigate/${job.job_id}`}
                  className="p-4 hover:bg-slate-800/50 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3 group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-xl bg-slate-950 border border-slate-800 group-hover:border-teal-500/40 flex items-center justify-center text-teal-400 shrink-0 transition-colors">
                      <svg
                        className="w-4 h-4"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold text-slate-100 group-hover:text-teal-300 truncate transition-colors">
                          {job.ioc}
                        </span>
                        {job.ioc_type && (
                          <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-800/90 text-slate-400 border border-slate-700/60 shrink-0">
                            {job.ioc_type}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[11px] font-mono text-slate-500 mt-0.5">
                        <span>CASE: {job.job_id.slice(0, 8)}</span>
                        {job.created_at && (
                          <>
                            <span>•</span>
                            <span>{new Date(job.created_at).toLocaleString()}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2.5 shrink-0 self-end sm:self-center">
                    {job.risk_level && (
                      <span
                        className={`text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full border uppercase ${getRiskBadgeStyle(
                          job.risk_level
                        )}`}
                      >
                        {job.risk_level}
                        {job.gti_score !== null && job.gti_score !== undefined
                          ? ` • ${job.gti_score}/100`
                          : ""}
                      </span>
                    )}

                    <span
                      className={`text-[10px] font-mono font-semibold px-2.5 py-0.5 rounded-lg border uppercase ${getStatusBadgeStyle(
                        job.status
                      )}`}
                    >
                      {job.status}
                    </span>

                    <span className="text-xs font-mono text-slate-500 group-hover:text-teal-400 group-hover:translate-x-0.5 transition-all pl-1">
                      ➔
                    </span>
                  </div>
                </Link>
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

