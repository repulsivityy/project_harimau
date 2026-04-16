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
    <div className="min-h-screen bg-surface text-foreground relative flex flex-col selection:bg-primary selection:text-on-primary overflow-hidden">
      {/* Background HUD elements */}
      <div className="fixed inset-0 pointer-events-none opacity-20">
        <div className="absolute top-0 left-0 w-full h-full radar-sweep"></div>
        <div className="absolute top-0 left-0 w-full h-full opacity-10" style={{ backgroundImage: "linear-gradient(var(--secondary) 1px, transparent 1px), linear-gradient(90deg, var(--secondary) 1px, transparent 1px)", backgroundSize: "64px 64px" }}></div>
      </div>

      {/* Asymmetric Tactical Header */}
      <header className="relative z-50 flex items-stretch h-20 border-b border-outline-variant/30 bg-surface/80 backdrop-blur-xl">
        <div className="flex items-center px-8 bg-primary/10 border-r border-primary/30 skew-x-[-12deg] -ml-4 pr-12">
          <Link href="/" className="flex items-center gap-4 skew-x-[12deg]">
            <div className="w-10 h-10 border-2 border-primary relative overflow-hidden">
              <Image src="/avatar.jpeg" alt="Logo" fill className="object-cover" />
            </div>
            <span className="text-4xl font-black italic tracking-tighter uppercase font-headline text-primary glow-text-primary">
              HARIMAU
            </span>
          </Link>
        </div>
        
        <nav className="flex-grow flex items-center px-12 gap-8">
          <Link href="/" className="font-headline text-primary border-b-2 border-primary pb-1 uppercase tracking-widest text-sm">Hunt</Link>
          <Link href="#" className="font-headline text-secondary/60 hover:text-primary transition-colors uppercase tracking-widest text-sm">Investigate</Link>
          <Link href="#" className="font-headline text-secondary/60 hover:text-primary transition-colors uppercase tracking-widest text-sm">Intel</Link>
        </nav>

        <div className="flex items-center px-8 gap-6 border-l border-outline-variant/30">
          <div className="hidden lg:block">
            <select
              className="bg-surface-container border-b-2 border-secondary text-secondary text-[10px] px-3 py-1 font-label uppercase outline-none cursor-pointer"
              value=""
              onChange={(e) => {
                if (e.target.value) router.push(`/investigate/${e.target.value}`);
              }}
            >
              <option value="">RECORDS_HISTORY</option>
              {recentJobs.map((job: any) => (
                <option key={job.job_id} value={job.job_id}>
                  {job.ioc} // {job.status}
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-4 text-secondary">
            <span className="material-symbols-outlined cursor-pointer hover:text-primary transition-colors">terminal</span>
            <span className="material-symbols-outlined cursor-pointer hover:text-primary transition-colors">settings</span>
          </div>
        </div>
      </header>

      <main className="flex-grow flex relative z-10">
        {/* Left Side: Asymmetric Info Panels */}
        <div className="hidden xl:flex flex-col w-1/3 pt-32 pl-12 gap-6">
          <div className="bg-surface-container-low border-l-4 border-primary p-6 relative overflow-hidden scanline">
            <h3 className="font-headline text-primary text-xs font-black uppercase mb-4 tracking-widest">System_Briefing</h3>
            <p className="font-body text-xs text-outline leading-relaxed">
              AI-POWERED THREAT HUNTING CORE V2.5. UTILIZING MULTI-AGENT LANGGRAPH ORCHESTRATION FOR AUTONOMOUS FORENSICS.
            </p>
          </div>
          
          <div className="bg-surface-container-highest/30 border-l-2 border-secondary/50 p-6 backdrop-blur-md -ml-8">
            <h3 className="font-headline text-secondary text-[10px] font-black uppercase mb-3 tracking-widest">Specialist_Nodes</h3>
            <div className="space-y-2">
              <div className="flex justify-between items-center text-[10px] font-label">
                <span className="text-outline">TRIAGE_AGENT</span>
                <span className="text-secondary">ACTIVE</span>
              </div>
              <div className="flex justify-between items-center text-[10px] font-label">
                <span className="text-outline">INFRA_AGENT</span>
                <span className="text-secondary">ACTIVE</span>
              </div>
              <div className="flex justify-between items-center text-[10px] font-label">
                <span className="text-outline">MALWARE_AGENT</span>
                <span className="text-secondary">ACTIVE</span>
              </div>
            </div>
          </div>
        </div>

        {/* Center: Main Hunting HUD */}
        <div className="flex-grow flex flex-col items-center justify-center px-12">
          <div className="w-full max-w-2xl flex flex-col items-center text-center gap-12">
            <div className="relative">
              <h1 className="text-6xl font-black italic font-headline tracking-tighter uppercase text-primary drop-shadow-[0_0_20px_rgba(255,124,245,0.3)]">
                Digital Predator
              </h1>
              <div className="absolute -top-6 -right-12 px-2 py-1 bg-secondary text-surface text-[10px] font-black uppercase tracking-widest">
                Protocol_H
              </div>
            </div>

            <form className="w-full flex flex-col items-center gap-12" onSubmit={handleSearch}>
              {/* Predator Input Field */}
              <div className="w-full relative group">
                <input
                  className="w-full bg-surface-container-high/50 border-b-2 border-secondary/30 text-secondary px-8 py-6 font-headline text-2xl tracking-tighter focus:outline-none focus:border-primary transition-all placeholder:text-outline/30 uppercase"
                  onChange={(e) => setIoc(e.target.value)}
                  placeholder="INJECT_IOC_IDENTIFIER_..."
                  type="text"
                  value={ioc}
                />
                <div className="absolute bottom-0 left-0 h-[2px] bg-primary w-0 group-focus-within:w-full transition-all duration-500 shadow-[0_0_10px_var(--primary)]"></div>
                
                <button
                  className="absolute right-0 bottom-full mb-4 bg-primary text-on-primary font-headline font-black px-6 py-2 uppercase italic tracking-tighter hover:bg-secondary transition-colors"
                  type="submit"
                >
                  Initiate_Hunt
                </button>
              </div>

              {/* Tactical Depth Dial */}
              <div className="flex flex-col items-center gap-4">
                <span className="font-label text-[10px] text-outline uppercase tracking-widest">Investigation_Depth_Control</span>
                <div className="relative w-32 h-32 flex items-center justify-center">
                  {/* Outer Ring */}
                  <div className="absolute inset-0 border border-outline-variant/30 rounded-full"></div>
                  
                  {/* Moving Dial */}
                  <div 
                    className="w-24 h-24 bg-surface-container-highest border-2 border-secondary rounded-full flex items-center justify-center transition-transform duration-500 ease-out shadow-[0_0_30px_rgba(0,251,251,0.2)]"
                    style={{ transform: `rotate(${rotationDegrees}deg)` }}
                  >
                    <div className="absolute top-1 left-1/2 -translate-x-1/2 w-1 h-6 bg-primary"></div>
                    <div className="w-4 h-4 bg-primary glow-primary rounded-full"></div>
                  </div>

                  <input
                    className="absolute inset-0 opacity-0 cursor-pointer z-20"
                    max="5"
                    min="1"
                    onChange={(e) => setDepth(parseInt(e.target.value))}
                    type="range"
                    value={depth}
                  />

                  {/* Tick Marks */}
                  <div className="absolute inset-[-20px] pointer-events-none">
                    {[1, 2, 3, 4, 5].map(d => (
                      <div 
                        key={d} 
                        className={`absolute w-1 h-3 transition-colors duration-300 ${depth === d ? 'bg-primary' : 'bg-outline-variant/50'}`}
                        style={{ 
                          left: '50%', 
                          top: '50%', 
                          transformOrigin: '0 52px',
                          transform: `translateX(-50%) rotate(${(d - 3) * 30}deg) translateY(-52px)`
                        }}
                      />
                    ))}
                  </div>
                </div>
                <div className="font-headline text-primary font-black uppercase tracking-widest text-lg">
                  Lvl_{depth}
                </div>
              </div>
            </form>
          </div>
        </div>

        {/* Right Side: Floating Status Panel */}
        <div className="hidden xl:flex flex-col w-1/4 pt-32 pr-12 gap-6 items-end">
          <div className="bg-surface-container border-r-4 border-secondary p-4 w-full glass-panel">
            <h3 className="font-headline text-secondary text-[10px] font-black uppercase mb-2">Node_Status</h3>
            <div className="font-label text-[10px] text-outline space-y-1">
              <div className="flex justify-between"><span>CPU_LOAD</span><span className="text-secondary">12.4%</span></div>
              <div className="flex justify-between"><span>MEM_USE</span><span className="text-secondary">4.2GB</span></div>
              <div className="flex justify-between"><span>API_LATENCY</span><span className="text-primary">42ms</span></div>
            </div>
          </div>
          
          <div className="relative w-48 h-48 border border-outline-variant/30 flex items-center justify-center overflow-hidden">
             <Image src={imageSrc} alt="Tiger" fill className="object-contain opacity-10 p-4" />
             <div className="absolute inset-0 radar-sweep opacity-50"></div>
          </div>
        </div>
      </main>

      {/* Footer Branding */}
      <footer className="relative z-50 h-12 border-t border-outline-variant/30 bg-surface flex items-center justify-between px-8">
        <div className="text-[10px] font-label text-outline uppercase tracking-widest">
          &copy; 2026 PROJECT_HARIMAU // DIGITAL_PREDATOR_CORE
        </div>
        <div className="flex items-center gap-4 text-[10px] font-label text-secondary uppercase">
          <span className="flex items-center gap-1"><div className="w-1.5 h-1.5 bg-secondary glow-secondary"></div> GRID_STABLE</span>
          <span>EST_COMPLETION: 480S</span>
        </div>
      </footer>
    </div>
  );
}
