"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function Home() {
  const router = useRouter();
  const [ioc, setIoc] = useState("");
  const [depth, setDepth] = useState(2);
  const [recentJobs, setRecentJobs] = useState<any[]>([]);

  // Fetch past jobs from Cloud SQL for the history dropdown
  useEffect(() => {
    fetch("/api/investigations")
      .then((r) => r.json())
      .then((jobs) => setRecentJobs(Array.isArray(jobs) ? jobs : []))
      .catch(() => setRecentJobs([]));
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (ioc.trim()) {
      try {
        const response = await fetch("/api/investigate", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ ioc: ioc.trim(), max_iterations: depth }),
        });

        if (!response.ok) {
          throw new Error("Failed to submit investigation");
        }

        const data = await response.json();
        const jobId = data.job_id;

        router.push(`/investigate/${jobId}`);
      } catch (error) {
        console.error("Error submitting investigation:", error);
        alert("Failed to start investigation. Please try again.");
      }
    }
  };

  const rotationDegrees = (depth - 3) * 30;

  const imageSrc =
    process.env.NODE_ENV === "development"
      ? "/tiger_logo.png?v=2"
      : "/tiger_logo.png";

  return (
    <div className="min-h-screen bg-surface text-foreground relative flex flex-col selection:bg-primary selection:text-on-primary overflow-hidden font-body">
      {/* Background HUD elements */}
      <div className="fixed inset-0 pointer-events-none opacity-20">
        <div className="absolute top-0 left-0 w-full h-full radar-sweep"></div>
        <div className="absolute top-0 left-0 w-full h-full opacity-5" style={{ backgroundImage: "linear-gradient(var(--secondary) 1px, transparent 1px), linear-gradient(90deg, var(--secondary) 1px, transparent 1px)", backgroundSize: "32px 32px" }}></div>
      </div>

      {/* Top Navigation - Asymmetric & Minimal */}
      <nav className="relative z-50 flex justify-between items-center p-6 bg-[#0e0e10]">
        <div className="flex items-center gap-8">
          <Link href="/" className="text-2xl font-black italic text-[#FF00FF] font-headline tracking-tighter uppercase">
            HARIMAU
          </Link>
          <div className="hidden md:flex gap-6 font-headline text-sm uppercase tracking-widest">
            <Link href="/" className="text-[#00FFFF] border-b-2 border-[#00FFFF] pb-1 hover:text-[#FFFF00] transition-colors">Hunt</Link>
            <Link href={recentJobs.length > 0 ? `/investigate/${recentJobs[0].job_id}` : '#'} className="text-slate-400 hover:text-[#FFFF00] transition-colors">Investigation</Link>
            <Link href="#" className="text-slate-400 hover:text-[#FFFF00] transition-colors">Intel</Link>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <button className="bg-[#1a1a1c] px-4 py-1 text-xs font-bold text-[#ff7cf5] hover:text-[#FFFF00] transition-colors font-headline uppercase tracking-widest">EXECUTE</button>
          <div className="w-8 h-8 bg-surface-container-high overflow-hidden">
            <Image src="/avatar.jpeg" alt="Avatar" width={32} height={32} className="object-cover" />
          </div>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="flex-grow flex flex-col justify-between p-8 relative z-10">
        <div className="absolute inset-0 opacity-5 scanline pointer-events-none"></div>

        {/* Backing Image (Tiger Logo) */}
        <div className="absolute inset-0 opacity-5 flex items-center justify-center pointer-events-none z-0">
          <Image src="/tiger_logo.png" alt="Tiger Logo" width={700} height={700} className="object-contain -translate-y-[20%]" />
        </div>

        {/* Center - Main Search Area */}
        <div className="flex-grow flex flex-col justify-center items-center max-w-5xl w-full mx-auto gap-6 pt-32 pb-10">

          <div className="text-center">
            <h1 className="font-headline text-7xl md:text-7xl font-black tracking-tighter uppercase mb-4 leading-none italic text-foreground glow-text-primary">
              Harimau
            </h1>
            <p className="font-headline text-secondary max-w-4xl text-[13px] mb-6 tracking-wide uppercase mx-auto">
              Inspired by the predatory tiger, Harimau is an automated threat intelligence system that utilizes a LangGraph-based multi-agent architecture to investigate IOCs.
              <br />
              <br />
              By mimicking human analyst workflows, it systematically analyzes malware and maps infrastructure to synthesize complex data into actionable intelligence reports.
            </p>
          </div>

          <form className="w-full flex flex-col gap-8 items-center" onSubmit={handleSearch}>
            {/* Predator Input Field */}
            <div className="w-full max-w-4xl bg-surface-container-high/5 backdrop-blur-none glow-secondary p-1 flex flex-col md:flex-row gap-0 group">
              <div className="flex-grow relative">
                <input
                  className="w-full bg-transparent border-none text-secondary placeholder:text-outline-variant font-headline tracking-widest py-3 px-6 focus:ring-0 focus:outline-none uppercase text-xl"
                  onChange={(e) => setIoc(e.target.value)}
                  placeholder="Enter IOCs..."
                  type="text"
                  value={ioc}
                />
                <div className="absolute bottom-0 left-0 w-full h-[2px] bg-secondary opacity-50 group-focus-within:opacity-100 transition-opacity"></div>
              </div>
              <button
                className="bg-gradient-to-r from-primary to-primary-container text-on-primary font-headline font-black px-10 py-3 text-xl tracking-tighter active:scale-95 transition-transform"
                type="submit"
              >
                HUNT
              </button>
            </div>

            {/* Investigation Depth Control */}
            <div className="mt-4 w-full max-w-xl">
              <div className="flex justify-between items-end mb-4 font-headline text-[10px] tracking-widest uppercase">
                <span className="text-outline">Forensic Intensity</span>
                <span className="text-tertiary">Level {depth}: {depth === 5 ? 'Deep Memory Forensics' : depth >= 3 ? 'Deep Static Analysis' : 'Surface Scan'}</span>
              </div>
              <div className="relative h-2 bg-surface-container-highest">
                <div
                  className="absolute top-0 left-0 h-full bg-tertiary transition-all duration-300"
                  style={{ width: `${((depth - 1) / 4) * 100}%` }}
                ></div>
                <div
                  className="absolute top-[-4px] w-4 h-4 bg-tertiary border-2 border-background cursor-pointer z-10 force-rounded"
                  style={{
                    left: `${((depth - 1) / 4) * 100}%`,
                    transform: `translateX(-50%)`
                  }}
                ></div>
                {/* Hidden Range Input for interaction */}
                <input
                  className="absolute inset-0 opacity-0 cursor-pointer z-20"
                  max="5"
                  min="1"
                  onChange={(e) => setDepth(parseInt(e.target.value))}
                  type="range"
                  value={depth}
                />
              </div>
              <div className="flex justify-between mt-4">
                <span className="text-[9px] text-outline-variant font-headline uppercase">Surface Scan</span>
                <span className="text-[9px] text-outline-variant font-headline uppercase">Deep Memory Forensics</span>
              </div>
            </div>
          </form>
        </div>

        {/* Content Area - Aligned with Input Field */}
        <section className="w-full max-w-4xl mx-auto pb-10">
          {/* Recent Investigations (Full Width) */}
          <div className="bg-surface-container-low p-4 border-l-4 border-primary">
            <h2 className="font-headline text-xl font-bold uppercase mb-4 flex items-center gap-3 text-foreground">
              <span className="material-symbols-outlined text-primary">radar</span>
              Recent Investigations
            </h2>
            <div className="space-y-3">
              {recentJobs.slice(0, 3).map((job: any) => (
                <Link key={job.job_id} href={`/investigate/${job.job_id}`} className="flex items-center justify-between group cursor-pointer">
                  <div className="flex flex-col">
                    <span className="font-headline text-base tracking-tighter text-on-surface group-hover:text-primary transition-colors">{job.ioc}</span>
                    <span className="font-body text-[9px] text-outline uppercase">Status: {job.status}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="hidden md:block h-[1px] w-24 bg-outline-variant opacity-30"></div>
                    <span className={`px-2 py-0.5 text-[9px] font-headline uppercase ${job.status === 'completed' ? 'bg-secondary/10 text-secondary border border-secondary' : 'bg-tertiary/10 text-tertiary border border-tertiary'}`}>
                      {job.status}
                    </span>
                  </div>
                </Link>
              ))}
              {recentJobs.length === 0 && (
                <div className="text-outline-variant italic font-label text-sm">No history found</div>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
