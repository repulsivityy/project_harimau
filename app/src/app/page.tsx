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

  // Map depth (1-5) to rotation degrees (e.g., -60 to 60)
  const rotationDegrees = (depth - 3) * 30;

  // Only use cache-buster in development
  const imageSrc =
    process.env.NODE_ENV === "development"
      ? "/tiger_logo.png?v=2"
      : "/tiger_logo.png";

  return (
    <div className="font-body selection:bg-pink-500 selection:text-white min-h-screen bg-[#0e0e10] text-[#fffbfe] relative flex flex-col justify-between">
      {/* TopNavBar */}
      <header className="fixed top-0 left-0 w-full z-50 bg-[#0e0e10]/80 backdrop-blur-xl border-b-2 border-secondary/30 flex justify-between items-center px-6 py-4 shadow-[0_0_40px_rgba(255,124,245,0.15)]">
        <div className="flex items-center gap-8">
          <Link
            href="/"
            className="flex items-center gap-3 hover:opacity-80 transition-opacity"
          >
            <div className="w-10 h-10 border-2 border-pink-500 rounded-sm overflow-hidden relative">
              <Image
                src="/avatar.jpeg"
                alt="Harimau Logo"
                fill
                className="object-cover"
              />
            </div>
            <span className="text-3xl font-black italic text-pink-500 drop-shadow-[0_0_10px_rgba(255,0,255,0.8)] font-headline tracking-tighter uppercase">
              HARIMAU
            </span>
          </Link>
          <nav className="hidden md:flex space-x-8">
            <Link
              className="text-pink-500 border-b-4 border-pink-500 pb-2 font-headline tracking-tighter uppercase"
              href="/"
            >
              HUNT
            </Link>
            <a
              className="text-cyan-400/60 hover:text-yellow-400 font-headline tracking-tighter uppercase"
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
          {/* Jobs History Dropdown */}
          <div className="relative group hidden lg:block">
            <select
              className="relative bg-[#19191c] border-b-2 border-pink-500 text-pink-500 text-xs px-4 py-2 focus:ring-0 w-48 font-label cursor-pointer appearance-none"
              value=""
              onChange={(e) => {
                if (e.target.value) router.push(`/investigate/${e.target.value}`);
              }}
            >
              <option value="">
                {recentJobs.length > 0 ? "Recent Jobs..." : "No Recent Jobs"}
              </option>
              {recentJobs.map((job: any) => (
                <option key={job.job_id} value={job.job_id}>
                  {job.ioc} — {job.status}
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
                src="/avatar.jpeg"
              />
            </div>
          </div>
        </div>
      </header>

      {/* Floating Info Card (Top Right) */}
      <div className="fixed top-24 right-6 w-80 bg-[#19191c]/80 backdrop-blur-xl p-4 border-l-2 border-pink-500 z-40">
        <h3 className="font-headline text-xs font-black text-pink-500 uppercase mb-2">
          Platform Info
        </h3>
        <p className="font-label text-[10px] text-[#adaaad] leading-tight space-y-2">
          <span>
            Harimau (Tiger in Malay) is an AI-powered threat hunting platform
            that uses multiple specialized threat hunt agents to analyze and
            investigate IOCs (IPs, Domains, Hashes, URLs).
          </span>
          <br />
          <br />
          <span>
            Harimau leverages LangGraph with multiple specialized threat hunt
            agents to mimic the flow of a threat hunting program.
          </span>
          <br />
          <br />
          <span>
            Harimau is currently in Beta Phase. Expect some bugs and unexpected
            behavior. Current investigation takes ~7-8 minutes to complete.
          </span>
        </p>
      </div>

      {/* Tiger Watermark (Centered Background) */}
      <div className="fixed inset-0 flex items-center justify-center pointer-events-none opacity-[0.05] z-0">
        <div className="relative w-[600px] h-[600px]">
          <img
            alt="Tiger Watermark"
            className="w-full h-full object-contain"
            src={imageSrc}
          />
        </div>
      </div>

      {/* Main Content Area (Centered Search) */}
      <main className="flex-grow flex flex-col items-center justify-center px-6 z-10">
        <div className="w-full max-w-4xl text-center space-y-8 flex flex-col items-center">
          <h1 className="text-5xl font-black italic font-headline tracking-tighter uppercase text-pink-500 drop-shadow-[0_0_20px_rgba(255,0,255,0.5)]">
            Harimau - AI Threat Hunter
          </h1>
          <p className="font-label text-sm text-cyan-400/60 uppercase">
            Enter IP, Domain, Hash, or URL to begin investigation
          </p>

          <form
            className="relative flex flex-col items-center gap-6 w-full"
            onSubmit={handleSearch}
          >
            <div className="flex gap-4 w-full">
              <input
                className="flex-grow bg-[#19191c] border-2 pulse-border text-cyan-400 px-6 py-4 placeholder-cyan-400/40 font-headline tracking-tighter text-xl focus:ring-0 focus:border-pink-500 outline-none uppercase"
                onChange={(e) => setIoc(e.target.value)}
                placeholder="ENTER_IOC_HERE_..."
                type="text"
                value={ioc}
              />
              <button
                className="bg-pink-500 text-[#0e0e10] font-headline font-black px-8 py-4 uppercase tracking-tighter hover:bg-cyan-400 transition-colors flex items-center gap-2 text-xl"
                type="submit"
              >
                HUNT
                <span className="material-symbols-outlined text-base font-bold">
                  arrow_forward
                </span>
              </button>
            </div>

            {/* Rotary Dial for Depth */}
            <div className="flex flex-col items-center gap-2 mt-4">
              <label className="font-label text-xs text-cyan-400/60 uppercase">
                Investigation Depth Control
              </label>
              <div className="relative w-24 h-24 flex items-center justify-center">
                {/* Visual Dial */}
                <div
                  className="w-20 h-20 bg-[#19191c] border-4 border-cyan-400 rounded-full flex items-center justify-center relative transition-transform duration-300"
                  style={{ transform: `rotate(${rotationDegrees}deg)` }}
                >
                  {/* Pointer line */}
                  <div className="absolute top-0 left-1/2 w-1 h-10 bg-pink-500 -translate-x-1/Origin-bottom"></div>
                  {/* Center dot */}
                  <div className="w-4 h-4 bg-[#0e0e10] border-2 border-pink-500 rounded-full z-10"></div>
                </div>

                {/* Hidden Native Slider to control rotation */}
                <input
                  className="absolute inset-0 opacity-0 cursor-pointer w-full h-full z-20"
                  max="5"
                  min="1"
                  onChange={(e) => setDepth(parseInt(e.target.value))}
                  type="range"
                  value={depth}
                />

                {/* Depth Labels surrounding the dial */}
                <div className="absolute inset-0 flex justify-between items-center px-2 pointer-events-none text-xs font-label text-cyan-400/40">
                  <span>1</span>
                  <span>5</span>
                </div>
              </div>
              <div className="font-label text-xs text-pink-500 uppercase mt-2">
                Depth Level: {depth}
              </div>
              <p className="text-[10px] text-cyan-400/40">
                Turn the dial to set investigation rounds
              </p>
            </div>
          </form>

          <div className="flex gap-4 justify-center text-xs font-label text-cyan-400/40 mt-12">
            <span>TIP: Press Enter to fast-track investigation</span>
            <span>|</span>
            <span>API_STATUS: READY</span>
          </div>
        </div>
      </main>

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
