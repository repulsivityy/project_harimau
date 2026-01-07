# Benchmarking Guide - Threat Hunter Platform

**Version:** 1.0  
**Date:** January 2025  
**Purpose:** Establish performance baselines for timeout configuration  
**Audience:** Developers running performance tests

---

## Table of Contents

1. [Overview](#1-overview)
2. [When to Run Benchmarks](#2-when-to-run-benchmarks)
3. [Test Fixtures](#3-test-fixtures)
4. [Running Benchmarks](#4-running-benchmarks)
5. [Interpreting Results](#5-interpreting-results)
6. [Setting Timeout Values](#6-setting-timeout-values)
7. [Benchmark Implementation](#7-benchmark-implementation)
8. [Expected Results](#8-expected-results)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Overview

### Purpose

Benchmarking establishes empirical performance baselines to inform timeout configuration and optimization priorities. Without real-world data, timeout values are guesses that can either:
- **Too Low:** Kill investigations prematurely, wasting API calls
- **Too High:** Let hung investigations waste resources

### What We Measure

**Primary Metrics:**
- Total investigation duration (end-to-end)
- Per-agent execution time (triage, malware, infrastructure)
- API call counts per investigation
- Graph size (node/edge counts)
- Iteration counts

**Secondary Metrics:**
- Cost per investigation (LLM tokens × price)
- Memory usage
- Error rates

### When to Use Results

1. **Week 3, Day 20-21:** Initial benchmark run to set timeout values
2. **After prompt changes:** Re-benchmark to detect regressions
3. **Before production deployment:** Validate performance at scale

---

## 2. When to Run Benchmarks

### Phase 1, Week 3 (Days 20-21) - MANDATORY

**Objective:** Establish baseline timeout values before Phase 2

**Prerequisites:**
- All 4 agents implemented and tested
- LangGraph workflow functional
- MCP integration working
- At least 10 successful manual investigations

**Deliverable:** `benchmark_results.json` with recommended timeout values

---

### After Significant Changes - RECOMMENDED

**When to Re-Benchmark:**
- Agent prompt changes (might affect execution time)
- LLM model changes (Gemini 2.0 Flash → 2.5 Pro)
- MCP server updates
- Graph logic changes (new node types, edge relationships)
- Budget limit adjustments

**Why:** Ensure changes don't introduce performance regressions

---

### Before Production Deployment - RECOMMENDED

**When:** End of Phase 3, before public launch

**Why:** Validate that production environment performance matches development

**Additional Considerations:**
- Test with production MCP server URLs
- Test with Cloud Run cold starts
- Measure network latency to APIs

---

## 3. Test Fixtures

### IOC Sample Selection

**Goal:** 50+ diverse IOCs covering all types and complexity levels

#### File Hashes (20 samples)

**Benign Files (5):**
```python
BENIGN_FILES = [
    "d41d8cd98f00b204e9800998ecf8427e",  # Empty file (MD5)
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # Empty file (SHA256)
    # Add 3 more known-benign Windows system files
]
```

**Simple Malware (5):**
- Single-stage malware
- Few dropped files (0-2)
- Minimal network activity (1-3 IOCs)

**Complex Malware (5):**
- Multi-stage malware
- Many dropped files (5-20)
- Heavy network activity (10+ IOCs)

**APT-level Malware (5):**
- Sophisticated campaigns
- Extensive infrastructure
- Deep graph depth (3+ degrees)

---

#### IP Addresses (10 samples)

**Benign IPs (3):**
```python
BENIGN_IPS = [
    "8.8.8.8",         # Google DNS
    "1.1.1.1",         # Cloudflare DNS
    "13.107.21.200"    # Microsoft infrastructure
]
```

**Suspicious IPs (3):**
- Low detection ratios (1-5 detections)
- Limited infrastructure

**Malicious IPs (4):**
- High detection ratios (10+ detections)
- Extensive infrastructure (hosting multiple domains)

---

#### Domains (10 samples)

**Benign Domains (3):**
```python
BENIGN_DOMAINS = [
    "google.com",
    "microsoft.com",
    "github.com"
]
```

**Suspicious Domains (3):**
- Recently registered
- Low reputation

**Malicious Domains (4):**
- Known C2 servers
- Extensive passive DNS history

---

#### URLs (10 samples)

**Benign URLs (3):**
```python
BENIGN_URLS = [
    "https://github.com/trending",
    "https://news.ycombinator.com",
    "https://www.wikipedia.org"
]
```

**Suspicious URLs (3):**
- Shortened URLs
- Unusual paths

**Malicious URLs (4):**
- Known phishing pages
- Malware distribution URLs

---

### Creating Your Test Fixture File

**File:** `tests/fixtures/benchmark_iocs.json`
```json
{
  "files": {
    "benign": [
      {
        "ioc": "d41d8cd98f00b204e9800998ecf8427e",
        "description": "Empty file",
        "expected_verdict": "BENIGN"
      }
    ],
    "simple_malware": [
      {
        "ioc": "INSERT_REAL_HASH_HERE",
        "description": "Simple ransomware",
        "expected_verdict": "MALICIOUS"
      }
    ],
    "complex_malware": [
      {
        "ioc": "INSERT_REAL_HASH_HERE",
        "description": "Multi-stage loader",
        "expected_verdict": "MALICIOUS"
      }
    ]
  },
  "ips": {
    "benign": [...],
    "suspicious": [...],
    "malicious": [...]
  },
  "domains": {
    "benign": [...],
    "suspicious": [...],
    "malicious": [...]
  },
  "urls": {
    "benign": [...],
    "suspicious": [...],
    "malicious": [...]
  }
}
```

**Important:** Use REAL IOCs from VirusTotal, not synthetic data. The goal is to measure real-world performance.

---

## 4. Running Benchmarks

### Quick Start
```bash
# Run full benchmark suite
python tests/benchmark.py

# Run with specific fixture file
python tests/benchmark.py --fixtures tests/fixtures/custom_iocs.json

# Run only file IOCs
python tests/benchmark.py --type file

# Dry run (validate fixtures without running investigations)
python tests/benchmark.py --dry-run
```

### Expected Runtime
```
50 IOCs × 3 minutes avg = 150 minutes (2.5 hours)

Plan accordingly - run during lunch or overnight.
```

### Monitoring Progress

The benchmark script prints real-time progress:
```
🏃 Running Benchmark Suite
Total IOCs: 50
Estimated time: 2-3 hours

[1/50] Testing d41d8cd98f00b204e9800998ecf8427e (file, benign)...
  ✓ Complete in 1.2s (BENIGN as expected)
  
[2/50] Testing malicious_hash_123 (file, malicious)...
  ✓ Complete in 45.3s (MALICIOUS as expected)
  └─ Found 12 network IOCs, 3 dropped files
  
[3/50] Testing 8.8.8.8 (ip, benign)...
  ✓ Complete in 2.8s (BENIGN as expected)

...

[50/50] Testing phishing-url.com (url, malicious)...
  ✓ Complete in 8.1s (MALICIOUS as expected)

✅ Benchmark Complete!
Results saved to: benchmark_results.json
Summary saved to: benchmark_summary.md
```

### Output Files
```
benchmark_results.json       # Raw data (all metrics)
benchmark_summary.md         # Human-readable summary
benchmark_analysis.json      # Statistical analysis
```

---

## 5. Interpreting Results

### Understanding `benchmark_results.json`
```json
{
  "metadata": {
    "test_date": "2025-01-20T10:30:00Z",
    "total_iocs_tested": 50,
    "total_duration": "2h 34m",
    "llm_model": "gemini-2.0-flash",
    "mcp_servers": ["gti"]
  },
  
  "raw_results": [
    {
      "ioc": "d41d8cd98f00b204e9800998ecf8427e",
      "type": "file",
      "category": "benign",
      "duration": 1.2,
      "verdict": "BENIGN",
      "agents_run": ["triage"],
      "api_calls": 1,
      "graph_nodes": 1,
      "graph_edges": 0,
      "iterations": 0,
      "agents": {
        "triage": 1.2,
        "malware": null,
        "infrastructure": null
      }
    },
    {
      "ioc": "malicious_hash_123",
      "type": "file",
      "category": "complex_malware",
      "duration": 45.3,
      "verdict": "MALICIOUS",
      "agents_run": ["triage", "malware", "infrastructure"],
      "api_calls": 15,
      "graph_nodes": 16,
      "graph_edges": 18,
      "iterations": 2,
      "agents": {
        "triage": 2.1,
        "malware": 35.8,
        "infrastructure": 7.4
      }
    }
  ],
  
  "analysis": {
    "overall": {
      "mean_duration": 12.4,
      "median_duration": 8.2,
      "p95_duration": 48.5,
      "max_duration": 120.3,
      "min_duration": 1.1
    },
    
    "by_agent": {
      "triage": {
        "mean": 2.1,
        "p95": 4.8,
        "max": 8.2
      },
      "malware": {
        "mean": 18.5,
        "p95": 52.3,
        "max": 105.7
      },
      "infrastructure": {
        "mean": 5.2,
        "p95": 12.8,
        "max": 25.1
      }
    },
    
    "by_ioc_type": {
      "file": {
        "mean": 22.3,
        "p95": 65.2
      },
      "ip": {
        "mean": 4.8,
        "p95": 9.1
      },
      "domain": {
        "mean": 6.2,
        "p95": 14.3
      },
      "url": {
        "mean": 5.5,
        "p95": 11.2
      }
    },
    
    "budget_analysis": {
      "avg_api_calls": 8.2,
      "max_api_calls": 42,
      "avg_graph_nodes": 6.5,
      "max_graph_nodes": 23,
      "budget_exhausted_count": 2
    }
  }
}
```

### Key Metrics to Review

#### 1. Overall Duration (Investigate Timeout)
```
Mean: 12.4s     → Typical investigation
P95:  48.5s     → 95% of investigations finish within this
Max:  120.3s    → Worst-case (outlier)

Recommended Timeout: P95 × 2 = 97s ≈ 100s (round to 120s for safety)
```

**Reasoning:** 
- P95 covers 95% of normal cases
- 2× buffer handles variance
- 120s (2 minutes) is user-friendly

---

#### 2. Agent-Specific Timeouts
```
Triage Agent:
  P95: 4.8s → Timeout: 10s (2× + round up)

Malware Agent:
  P95: 52.3s → Timeout: 60s (GTI sandbox analysis is slow)

Infrastructure Agent:
  P95: 12.8s → Timeout: 15s
```

---

#### 3. Budget Limits Validation
```
API Calls:
  Avg: 8.2
  Max: 42
  Current Limit: 200 ✓ (adequate)

Graph Nodes:
  Avg: 6.5
  Max: 23
  Current Limit: 50 ✓ (adequate)

Budget Exhausted: 2/50 (4%)
```

**If > 10% hit limits:** Increase limits or investigate why investigations are exploding

---

#### 4. Cost Analysis
```json
{
  "cost_analysis": {
    "avg_tokens_per_investigation": {
      "prompt": 1850,
      "completion": 720
    },
    "avg_cost_per_investigation": {
      "gemini_flash": "$0.0038",
      "gemini_pro": "$0.021"
    },
    "estimated_monthly_cost": {
      "100_per_day_flash": "$11.40",
      "100_per_day_pro": "$63.00"
    }
  }
}
```

**Decision Point:** Is Gemini Pro worth 5.5× cost for better accuracy?

---

#### 5. Outlier Analysis
```json
{
  "outliers": [
    {
      "ioc": "complex_apt_malware_xyz",
      "duration": 120.3,
      "reason": "47 dropped files caused 3 iterations",
      "recommendation": "Consider max_files_per_iteration limit"
    },
    {
      "ioc": "large_infrastructure_domain",
      "duration": 95.1,
      "reason": "Domain has 150+ DNS records",
      "recommendation": "Limit passive DNS results"
    }
  ]
}
```

**Action:** Investigate why these took so long. Are they edge cases or systemic issues?

---

## 6. Setting Timeout Values

### Recommended Timeout Configuration

Based on typical benchmark results:

**File:** `backend/config.py`
```python
"""
Configuration Settings
Generated from benchmark results on 2025-01-20
"""

# Agent-specific timeouts (seconds)
AGENT_TIMEOUTS = {
    "triage": 10,           # P95: 4.8s → 2× = 10s
    "malware": 60,          # P95: 52.3s → Round to 60s
    "infrastructure": 15,   # P95: 12.8s → 2× = 15s
    "synthesis": 10         # Always fast, 10s is safe
}

# Overall investigation timeout (seconds)
INVESTIGATION_TIMEOUT = 600  # 10 minutes (P95: 48.5s → 2× = 97s, but allow 10min for safety)

# Budget limits (validated from benchmarks)
INVESTIGATION_BUDGET = {
    "max_iterations": 3,         # Unchanged
    "max_api_calls": 200,        # Max observed: 42, 200 is safe
    "max_graph_nodes": 50,       # Max observed: 23, 50 is safe
    "max_wall_time": 600         # 10 minutes
}

# Per-iteration limits (prevent explosions)
ITERATION_LIMITS = {
    "max_files_per_iteration": 10,      # Prevent 50-file malware from exploding
    "max_network_iocs_per_iteration": 10  # Prevent massive infrastructure pivots
}
```

### Validation

After setting timeouts, run a small validation:
```bash
# Run 10 random investigations with new timeouts
python tests/validate_timeouts.py

# Should complete without timeout errors
```

---

## 7. Benchmark Implementation

### Complete Benchmark Script

**File:** `tests/benchmark.py`
```python
#!/usr/bin/env python3
"""
Benchmark Suite for Threat Hunter Platform

Runs investigations on diverse IOCs and collects performance metrics.
"""

import asyncio
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add backend to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.cli import run_investigation
from backend.logging_config import InvestigationLogger


def load_fixtures(fixture_file: str) -> List[Dict[str, Any]]:
    """
    Load IOC test fixtures from JSON file.
    
    Args:
        fixture_file: Path to JSON file with test IOCs
    
    Returns:
        List of IOC dictionaries
    """
    with open(fixture_file) as f:
        fixtures = json.load(f)
    
    # Flatten structure
    iocs = []
    for ioc_type, categories in fixtures.items():
        for category, ioc_list in categories.items():
            for ioc_data in ioc_list:
                iocs.append({
                    "ioc": ioc_data["ioc"],
                    "type": ioc_type,
                    "category": category,
                    "expected_verdict": ioc_data.get("expected_verdict", "UNKNOWN"),
                    "description": ioc_data.get("description", "")
                })
    
    return iocs


def parse_agent_timings(log_file: Path) -> Dict[str, float]:
    """
    Extract agent execution times from debug logs.
    
    Args:
        log_file: Path to debug log file
    
    Returns:
        Dictionary mapping agent name to execution time
    """
    timings = {}
    
    if not log_file.exists():
        return timings
    
    with open(log_file) as f:
        lines = f.readlines()
    
    # Parse timestamps to calculate durations
    agent_starts = {}
    
    for line in lines:
        try:
            log_entry = json.loads(line)
            agent = log_entry.get("agent")
            message = log_entry.get("message", "")
            timestamp = log_entry.get("timestamp")
            
            if "Starting" in message:
                agent_starts[agent] = timestamp
            elif "complete" in message.lower() and agent in agent_starts:
                # Calculate duration
                start = datetime.fromisoformat(agent_starts[agent])
                end = datetime.fromisoformat(timestamp)
                duration = (end - start).total_seconds()
                timings[agent] = duration
                
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    
    return timings


async def benchmark_investigation(ioc_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run investigation and collect metrics.
    
    Args:
        ioc_data: IOC information dictionary
    
    Returns:
        Benchmark results dictionary
    """
    ioc = ioc_data["ioc"]
    
    print(f"  Running: {ioc[:30]}... ({ioc_data['type']}, {ioc_data['category']})")
    
    start_time = time.time()
    
    try:
        # Run investigation with debug mode
        result = await run_investigation(ioc, debug=True)
        
        duration = time.time() - start_time
        
        # Parse debug logs for agent timings
        investigation_id = result["investigation_id"]
        debug_log = Path(f"logs/debug/investigation_{investigation_id}.log")
        agent_timings = parse_agent_timings(debug_log)
        
        # Extract metrics from result
        graph_data = result["graph"]
        
        # Determine verdict from first node
        verdict = "UNKNOWN"
        if graph_data["nodes"]:
            verdict = graph_data["nodes"][0].get("verdict", "UNKNOWN")
        
        # Check if verdict matches expectation
        verdict_match = verdict == ioc_data["expected_verdict"]
        
        metrics = {
            "ioc": ioc,
            "type": ioc_data["type"],
            "category": ioc_data["category"],
            "expected_verdict": ioc_data["expected_verdict"],
            "actual_verdict": verdict,
            "verdict_match": verdict_match,
            "duration": round(duration, 2),
            "api_calls": len(graph_data.get("api_calls", [])),
            "graph_nodes": len(graph_data["nodes"]),
            "graph_edges": len(graph_data["edges"]),
            "agents": agent_timings,
            "status": "success"
        }
        
        # Success indicator
        if verdict_match:
            print(f"    ✓ Complete in {duration:.1f}s ({verdict} as expected)")
        else:
            print(f"    ⚠ Complete in {duration:.1f}s ({verdict}, expected {ioc_data['expected_verdict']})")
        
        # Show interesting findings
        if graph_data["nodes"]:
            print(f"    └─ Found {len(graph_data['nodes'])} nodes, {len(graph_data['edges'])} edges")
        
        return metrics
        
    except Exception as e:
        duration = time.time() - start_time
        
        print(f"    ✗ Failed after {duration:.1f}s: {str(e)[:50]}")
        
        return {
            "ioc": ioc,
            "type": ioc_data["type"],
            "category": ioc_data["category"],
            "duration": round(duration, 2),
            "status": "failed",
            "error": str(e)
        }


def calculate_statistics(values: List[float]) -> Dict[str, float]:
    """
    Calculate statistical measures.
    
    Args:
        values: List of numeric values
    
    Returns:
        Dictionary with mean, median, p95, etc.
    """
    if not values:
        return {
            "count": 0,
            "mean": 0,
            "median": 0,
            "p95": 0,
            "min": 0,
            "max": 0
        }
    
    sorted_values = sorted(values)
    n = len(sorted_values)
    
    return {
        "count": n,
        "mean": round(sum(values) / n, 2),
        "median": round(sorted_values[n // 2], 2),
        "p95": round(sorted_values[int(n * 0.95)], 2) if n > 1 else sorted_values[0],
        "min": round(min(values), 2),
        "max": round(max(values), 2)
    }


def analyze_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze benchmark results and generate statistics.
    
    Args:
        results: List of benchmark result dictionaries
    
    Returns:
        Analysis dictionary with statistics and recommendations
    """
    # Filter successful results
    successful = [r for r in results if r["status"] == "success"]
    
    if not successful:
        return {"error": "No successful investigations to analyze"}
    
    # Overall statistics
    durations = [r["duration"] for r in successful]
    overall_stats = calculate_statistics(durations)
    
    # Agent-specific statistics
    agent_stats = {}
    for agent_name in ["triage", "malware", "infrastructure", "synthesis"]:
        agent_durations = [
            r["agents"].get(agent_name, 0)
            for r in successful
            if agent_name in r.get("agents", {})
        ]
        if agent_durations:
            agent_stats[agent_name] = calculate_statistics(agent_durations)
    
    # IOC type statistics
    type_stats = {}
    for ioc_type in ["file", "ip", "domain", "url"]:
        type_durations = [r["duration"] for r in successful if r["type"] == ioc_type]
        if type_durations:
            type_stats[ioc_type] = calculate_statistics(type_durations)
    
    # Budget analysis
    api_calls = [r.get("api_calls", 0) for r in successful]
    graph_nodes = [r.get("graph_nodes", 0) for r in successful]
    
    # Identify outliers (> 2 standard deviations from mean)
    import statistics
    if len(durations) > 2:
        mean_duration = statistics.mean(durations)
        stdev_duration = statistics.stdev(durations)
        threshold = mean_duration + (2 * stdev_duration)
        
        outliers = [
            {
                "ioc": r["ioc"][:30] + "...",
                "duration": r["duration"],
                "type": r["type"],
                "category": r["category"],
                "nodes": r.get("graph_nodes", 0)
            }
            for r in successful
            if r["duration"] > threshold
        ]
    else:
        outliers = []
    
    # Recommended timeouts (P95 × 2)
    recommended_timeouts = {
        "investigation": int(overall_stats["p95"] * 2),
        "agents": {
            agent: int(stats["p95"] * 2)
            for agent, stats in agent_stats.items()
        }
    }
    
    # Verdict accuracy
    verdict_matches = [r for r in successful if r.get("verdict_match", False)]
    verdict_accuracy = len(verdict_matches) / len(successful) if successful else 0
    
    return {
        "overall": overall_stats,
        "by_agent": agent_stats,
        "by_ioc_type": type_stats,
        "budget": {
            "api_calls": calculate_statistics(api_calls),
            "graph_nodes": calculate_statistics(graph_nodes)
        },
        "outliers": outliers,
        "recommended_timeouts": recommended_timeouts,
        "verdict_accuracy": round(verdict_accuracy, 2),
        "success_rate": len(successful) / len(results) if results else 0
    }


def generate_summary_report(results: List[Dict], analysis: Dict) -> str:
    """
    Generate human-readable summary report.
    
    Args:
        results: Benchmark results
        analysis: Analysis dictionary
    
    Returns:
        Markdown-formatted summary
    """
    report = []
    
    report.append("# Benchmark Results Summary\n")
    report.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**Total IOCs Tested:** {len(results)}\n")
    report.append(f"**Success Rate:** {analysis['success_rate']:.0%}\n")
    report.append(f"**Verdict Accuracy:** {analysis['verdict_accuracy']:.0%}\n\n")
    
    # Overall performance
    report.append("## Overall Performance\n")
    stats = analysis["overall"]
    report.append(f"- **Mean Duration:** {stats['mean']}s\n")
    report.append(f"- **Median Duration:** {stats['median']}s\n")
    report.append(f"- **95th Percentile:** {stats['p95']}s\n")
    report.append(f"- **Max Duration:** {stats['max']}s\n\n")
    
    # Agent performance
    report.append("## Agent Performance\n")
    for agent, stats in analysis["by_agent"].items():
        report.append(f"### {agent.title()} Agent\n")
        report.append(f"- Mean: {stats['mean']}s\n")
        report.append(f"- P95: {stats['p95']}s\n")
        report.append(f"- Max: {stats['max']}s\n\n")
    
    # Recommended timeouts
    report.append("## Recommended Timeouts\n")
    report.append(f"- **Investigation Timeout:** {analysis['recommended_timeouts']['investigation']}s\n")
    for agent, timeout in analysis['recommended_timeouts']['agents'].items():
        report.append(f"- **{agent.title()} Agent:** {timeout}s\n")
    report.append("\n")
    
    # Budget analysis
    report.append("## Budget Analysis\n")
    budget = analysis["budget"]
    report.append(f"- **API Calls:** Avg {budget['api_calls']['mean']}, Max {budget['api_calls']['max']}\n")
    report.append(f"- **Graph Nodes:** Avg {budget['graph_nodes']['mean']}, Max {budget['graph_nodes']['max']}\n\n")
    
    # Outliers
    if analysis["outliers"]:
        report.append("## Outliers (Slow Investigations)\n")
        for outlier in analysis["outliers"][:5]:
            report.append(f"- `{outlier['ioc']}` ({outlier['type']}, {outlier['category']}): {outlier['duration']}s, {outlier['nodes']} nodes\n")
        report.append("\n")
    
    return "".join(report)


async def run_benchmark_suite(fixture_file: str, ioc_type_filter: str = None):
    """
    Run complete benchmark suite.
    
    Args:
        fixture_file: Path to IOC fixtures JSON
        ioc_type_filter: Optional filter by IOC type
    """
    print("🏃 Running Benchmark Suite")
    print("="*60)
    
    # Load fixtures
    iocs = load_fixtures(fixture_file)
    
    # Apply filter if specified
    if ioc_type_filter:
        iocs = [ioc for ioc in iocs if ioc["type"] == ioc_type_filter]
    
    total = len(iocs)
    print(f"Total IOCs: {total}")
    print(f"Estimated time: {total * 3 / 60:.0f}-{total * 5 / 60:.0f} minutes\n")
    
    # Run benchmarks
    results = []
    for i, ioc_data in enumerate(iocs, 1):
        print(f"[{i}/{total}] {ioc_data['description'] or 'No description'}")
        result = await benchmark_investigation(ioc_data)
        results.append(result)
        print()
    
    # Analyze results
    print("📊 Analyzing results...")
    analysis = analyze_results(results)
    
    # Save results
    output_dir = Path("benchmark_outputs")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save raw results
    results_file = output_dir / f"benchmark_results_{timestamp}.json"
    with open(results_file, "w") as f:
        json.dump({
            "metadata": {
                "test_date": datetime.now().isoformat(),
                "total_iocs_tested": len(results),
                "fixture_file": fixture_file,
                "ioc_type_filter": ioc_type_filter
            },
            "raw_results": results,
            "analysis": analysis
        }, f, indent=2)
    
    print(f"✅ Raw results saved: {results_file}")
    
    # Save summary
    summary_file = output_dir / f"benchmark_summary_{timestamp}.md"
    summary = generate_summary_report(results, analysis)
    with open(summary_file, "w") as f:
        f.write(summary)
    
    print(f"✅ Summary saved: {summary_file}")
    
    # Print summary to console
    print("\n" + "="*60)
    print(summary)
    
    return results, analysis


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="Run benchmark suite")
    parser.add_argument(
        "--fixtures",
        default="tests/fixtures/benchmark_iocs.json",
        help="Path to IOC fixtures JSON file"
    )
    parser.add_argument(
        "--type",
        choices=["file", "ip", "domain", "url"],
        help="Filter by IOC type"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate fixtures without running investigations"
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("🔍 Validating fixtures...")
        iocs = load_fixtures(args.fixtures)
        print(f"✅ Loaded {len(iocs)} IOCs")
        for ioc_type in ["file", "ip", "domain", "url"]:
            count = len([i for i in iocs if i["type"] == ioc_type])
            print(f"  - {ioc_type}: {count}")
        return
    
    # Run benchmarks
    asyncio.run(run_benchmark_suite(args.fixtures, args.type))


if __name__ == "__main__":
    main()
```

---

## 8. Expected Results

### Typical Benchmark Output

Based on initial testing estimates:
```markdown
# Benchmark Results Summary

**Date:** 2025-01-20 14:32:15
**Total IOCs Tested:** 50
**Success Rate:** 96%
**Verdict Accuracy:** 94%

## Overall Performance
- **Mean Duration:** 12.4s
- **Median Duration:** 8.2s
- **95th Percentile:** 48.5s
- **Max Duration:** 120.3s

## Agent Performance

### Triage Agent
- Mean: 2.1s
- P95: 4.8s
- Max: 8.2s

### Malware Agent
- Mean: 18.5s
- P95: 52.3s
- Max: 105.7s

### Infrastructure Agent
- Mean: 5.2s
- P95: 12.8s
- Max: 25.1s

## Recommended Timeouts
- **Investigation Timeout:** 97s (round to 100s or 120s)
- **Triage Agent:** 10s
- **Malware Agent:** 60s
- **Infrastructure Agent:** 15s

## Budget Analysis
- **API Calls:** Avg 8.2, Max 42
- **Graph Nodes:** Avg 6.5, Max 23

## Outliers (Slow Investigations)
- `complex_apt_malware_xyz...` (file, complex_malware): 120.3s, 47 nodes
- `large_infrastructure_domain...` (domain, malicious): 95.1s, 28 nodes
```

---

## 9. Troubleshooting

### Issue: Benchmarks Taking Too Long

**Symptom:** Estimated 2 hours, actually taking 6+ hours

**Possible Causes:**
1. MCP server is slow or timing out
2. Network latency to APIs
3. Complex IOCs causing deep iteration

**Solutions:**
```bash
# Check MCP server health
curl http://localhost:3001/health

# Reduce fixture count temporarily
python tests/benchmark.py --fixtures tests/fixtures/mini_benchmark.json  # 10 IOCs

# Check network latency
ping www.virustotal.com
```

---

### Issue: High Failure Rate

**Symptom:** Success rate < 80%

**Possible Causes:**
1. API keys expired/invalid
2. MCP server down
3. Rate limiting

**Solutions:**
```bash
# Verify API keys
echo $GTI_API_KEY

# Check MCP server logs
docker logs gti-mcp-server

# Add delay between investigations
# Edit benchmark.py:
await asyncio.sleep(2)  # 2 second delay between IOCs
```

---

### Issue: Verdict Accuracy Low

**Symptom:** Verdict accuracy < 85%

**Possible Causes:**
1. Fixture expected verdicts are wrong
2. GTI data changed since fixture creation
3. Agent prompt issues

**Solutions:**
1. Manually verify expected verdicts in VirusTotal
2. Update fixture file with correct verdicts
3. Check agent decision logs for reasoning

---

### Issue: Outliers Skewing Results

**Symptom:** P95 much higher than median

**Possible Causes:**
1. Few very complex IOCs
2. API timeouts not being caught
3. Infinite loops (shouldn't happen with budget limits)

**Solutions:**
1. Identify outliers in results
2. Investigate why they're slow
3. Consider separate timeout category for "complex" investigations

---

## Appendix A: Sample Fixture File Structure
```json
{
  "files": {
    "benign": [
      {
        "ioc": "d41d8cd98f00b204e9800998ecf8427e",
        "description": "Empty file (MD5)",
        "expected_verdict": "BENIGN"
      }
    ],
    "simple_malware": [
      {
        "ioc": "INSERT_REAL_MALWARE_HASH",
        "description": "Simple ransomware sample",
        "expected_verdict": "MALICIOUS"
      }
    ],
    "complex_malware": [
      {
        "ioc": "INSERT_REAL_COMPLEX_HASH",
        "description": "Multi-stage malware with heavy C2",
        "expected_verdict": "MALICIOUS"
      }
    ]
  },
  "ips": {
    "benign": [
      {
        "ioc": "8.8.8.8",
        "description": "Google Public DNS",
        "expected_verdict": "BENIGN"
      }
    ],
    "malicious": [
      {
        "ioc": "INSERT_REAL_MALICIOUS_IP",
        "description": "Known C2 server",
        "expected_verdict": "MALICIOUS"
      }
    ]
  },
  "domains": {
    "benign": [
      {
        "ioc": "google.com",
        "description": "Google",
        "expected_verdict": "BENIGN"
      }
    ],
    "malicious": [
      {
        "ioc": "INSERT_REAL_MALICIOUS_DOMAIN",
        "description": "Phishing domain",
        "expected_verdict": "MALICIOUS"
      }
    ]
  },
  "urls": {
    "benign": [
      {
        "ioc": "https://github.com",
        "description": "GitHub homepage",
        "expected_verdict": "BENIGN"
      }
    ],
    "malicious": [
      {
        "ioc": "INSERT_REAL_MALICIOUS_URL",
        "description": "Malware distribution URL",
        "expected_verdict": "MALICIOUS"
      }
    ]
  }
}
```

---

**Document Version:** 1.0  
**Last Updated:** January 2025  
**Maintained By:** Development Team  
**Related Docs:** [PRD.md](./PRD.md), [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md), [CLAUDE.md](./CLAUDE.md)