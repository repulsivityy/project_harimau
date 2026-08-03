# Roadmap & PRD: Rethinking Attack-Chain Relationship Modeling & Graph Scoring

> **Owner:** Project Harimau · **Status:** 🗺️ Planned / Roadmap · **Created:** 2026-08-03  
> **Document Type:** Consolidated Product Requirements Document (PRD) & Technical Implementation Plan

---

## 1. Executive Summary & Problem Statement

### 1.1 Current Architecture & Its Limitations
In Project Harimau, attack-flow diagramming and LLM synthesis rely on a hardcoded set of relationship strings (`IMPORTANT_RELATIONSHIPS` in `lead_hunter_synthesis.py` and `dot_builder.py`) and numeric GTI threat score thresholds (`score >= 80` or `score > 60` with multiple qualifiers) to select the top 40 edges (`DIAGRAM_EDGE_LIMIT = 40`) for report inclusion.

This design introduces three structural vulnerabilities:
1. **Context-Blind Relationship Strings:** A relationship string like `contacted_domains` is evaluated identically whether it represents a malware payload beaconing to an attacker C2 server or a benign operating system check to `time.windows.com` or `ajax.googleapis.com`.
2. **Missing Attack-Chain Progressions (`file -> file` & `infra -> infra`):** Current bridge qualifiers only reward cross-layer `file <-> infra` edges. Critical attack-chain progressions—such as a `.zip` file dropping an `.exe` payload (`file -> file`) or a phishing URL redirecting to a credential-harvesting domain (`infra -> infra`)—are treated as low-priority background noise unless they match hardcoded strings.
3. **Unknown Score Coercion & Edge Budget Eviction:** Descriptor-only IOCs discovered during pivot hunts (e.g., dropped files from sandbox execution) often lack a GTI assessment score (`score = 0`). Because `0 > 60` evaluates to `False`, these newly discovered IOCs are excluded from `high_signal_node_ids`, causing their edges to be outranked and evicted by benign CDN domains in the 40-edge diagram budget.

### 1.2 The Vision
We will transition from **static relationship string matching** to an **Open Agent Context & Synthetic Baseline Scoring Architecture**. Specialist agents and tools will explicitly tag entities and edges with open-field attack-chain context (`attack_chain: true`, `context: "..."`, `signal_reason: "..."`), enabling dynamic graph prioritization that reflects analyst reasoning rather than rigid nomenclature.

---

## 2. Product Requirements Document (PRD)

### 2.1 Objectives & Key Results (OKRs)
* **Objective 1: Eliminate False-Negative Edge Eviction in Multi-Pivot Hunts**
  * **KR 1.1:** 100% of specialist-discovered IOCs (`malware_context`, `infra_context`, or `attack_chain`) survive the 40-edge diagram budget when competing against benign background infrastructure.
  * **KR 1.2:** Zero dropped payload files (`file -> file`) or phishing redirection links (`infra -> infra`) are dropped from the final Graphviz DOT output.
* **Objective 2: Enable Autonomous Agent Context Attribution**
  * **KR 2.1:** Allow specialist agents to tag edges and nodes with open-form context without requiring core backend config changes.
* **Objective 3: Maintain Diagram Readability & Token Efficiency**
  * **KR 3.1:** Maintain the hard 40-edge cap (`DIAGRAM_EDGE_LIMIT = 40`) to prevent LLM prompt token bloat and frontend D3 Graphviz visual clutter.

### 2.2 Target Users & Personas
* **Lead Threat Hunter (Human Analyst):** Requires a concise, grounded attack-flow diagram that clearly shows step-by-step attack progression (initial access -> drop -> execution -> C2) without being cluttered by benign CDNs.
* **Specialist Subagents (`malware`, `infrastructure`, `triage`):** Need an expressive, non-deterministic way to communicate semantic findings (e.g., "this domain is a dead-drop resolver") back to the Lead Hunter synthesis engine.

### 2.3 Out of Scope / Non-Goals
* **Removing the 40-Edge Budget:** The diagram budget remains capped at 40 edges to guarantee prompt window stability and rendering performance.
* **Universal `file -> file` / `infra -> infra` Boosting:** We will *not* indiscriminately give `+1 qualifier` to all `file -> file` or `infra -> infra` edges, as this would elevate noise (e.g., standard DNS resolutions, CDN subdomains) to the same priority as actual attacks.

---

## 3. Technical Architecture & System Design

### 3.1 Open Agent Context Metadata Model
Instead of relying solely on `rel in IMPORTANT_RELATIONSHIPS`, nodes and edges in `InvestigationCache` (`NetworkX` MultiDiGraph) will support open context attributes:

```json
{
  "id": "44d88612fea8a8f36de82e1278abb02f",
  "type": "file",
  "raw_attributes": {
    "malware_context": "dropped_file",
    "attack_chain": true,
    "signal_reason": "dropped_by_stage1_loader",
    "specialist_source": "malware_analysis_tool"
  }
}
```

### 3.2 Updated Qualifier & Synthetic Baseline Scoring (`_compute_high_signal`)
When evaluating nodes in `backend/agents/lead_hunter_synthesis.py`, we introduce:
1. **Open Context Recognition:** A node receives `+1 qualifier` if it carries any agent-attributed context:
   ```python
   has_agent_context = any(
       k in node.get("raw_attributes", {})
       for k in ("malware_context", "infra_context", "signal_reason", "attack_chain", "pivot_reason", "context")
   )
   if has_agent_context:
       qualifiers += 1
   ```
2. **Unscored Node Qualification:** An unscored node (`not node["score_known"]`) qualifies as high-signal if it has at least 1 qualifier:
   ```python
   score_ok = node["score"] >= 80 or (node["score"] > HIGH_SIGNAL_THREAT_SCORE and qualifiers >= 2)
   unknown_but_qualified = (not node["score_known"]) and (qualifiers >= 1)
   qualifies = score_ok or unknown_but_qualified
   ```
3. **Synthetic Baseline Score (`70` Suspicious/Amber):** When an unscored node qualifies as high-signal, it is dynamically assigned a synthetic baseline score of `70` for sorting arithmetic so its connected edges inherit an Amber threat level rather than default `0` benign:
   ```python
   if qualifies and not node["score_known"]:
       node["score"] = 70
   ```

### 3.3 Dynamic Edge Relevance Scoring (`_score_edges`)
In `_score_edges()`, edge qualifiers are awarded when:
* The relationship string matches `IMPORTANT_RELATIONSHIPS` (backward compatibility).
* **OR** the edge data contains an explicit `attack_chain` or `context` tag set by a specialist tool.
* **OR** both endpoints are high-signal attack progression nodes (`file -> file` payload drops or `infra -> infra` phishing/C2 redirects with specialist context).

```python
is_attack_progression = bool(data.get("attack_chain") or data.get("context"))
if rel in IMPORTANT_RELATIONSHIPS or is_attack_progression:
    qualifiers += 1
```

---

## 4. Implementation Plan & Work Breakdown Structure (WBS)

### Phase 1 — Schema & Graph Cache Foundation
| Task ID | Component | Description |
| :--- | :--- | :--- |
| **RAC-P1-1** | `graph_cache.py` | Extend `add_relationship` and `add_entity` to normalize and accept open-field context keys (`attack_chain`, `context`, `signal_reason`). |
| **RAC-P1-2** | `state.py` | Ensure `merge_metadata` and `merge_graphs` preserve open metadata dictionaries during parallel LangGraph branch fan-in. |

### Phase 2 — Specialist Agent & Tool Instrumentation
| Task ID | Component | Description |
| :--- | :--- | :--- |
| **RAC-P2-1** | `malware.py` | Update `malware_analysis_tool` to tag dropped files and attack-chain edges with `{"attack_chain": True, "context": "dropped_payload"}`. |
| **RAC-P2-2** | `infrastructure.py` | Update infrastructure tools to tag redirect chains and C2 resolution edges with `{"attack_chain": True, "context": "c2_infrastructure"}`. |
| **RAC-P2-3** | `triage.py` | Ensure `signal_reason` generated by `signal_filter.py` is propagated into the node's `raw_attributes` in state. |

### Phase 3 — Synthesis Engine Refactor
| Task ID | Component | Description |
| :--- | :--- | :--- |
| **RAC-P3-1** | `lead_hunter_synthesis.py` | Implement open-field context check and synthetic `70` baseline score in `_compute_high_signal()`. |
| **RAC-P3-2** | `lead_hunter_synthesis.py` | Update `_score_edges()` to reward `attack_chain` and `context` edge tags so they rank above benign CDN edges. |
| **RAC-P3-3** | `dot_builder.py` | Ensure Graphviz DOT builder formats open `context` strings as edge tooltips or label annotations. |

### Phase 4 — Test Automation & Verification
| Task ID | Component | Description |
| :--- | :--- | :--- |
| **RAC-P4-1** | `backend/tests/` | Create `test_open_attack_chain_scoring.py` verifying that unscored specialist-tagged nodes achieve synthetic score `70` and outrank benign CDN edges. |
| **RAC-P4-2** | `sprint_baselines/` | Run multi-pivot benchmark against `44d88612fea8a8f36de82e1278abb02f` and confirm 0 dropped files are evicted from the 40-edge budget. |

---

## 5. Risk Assessment & Mitigation

| Risk | Impact | Likelihood | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **LLM Hallucinating `attack_chain: True` on Noisy Edges** | Medium | Low | Restrict open context tagging to structured `ToolNode` tool outputs rather than free-form LLM JSON parsing. |
| **Synthetic `70` Score Over-Highlighting Nodes in UI** | Low | Medium | Keep `score_known: False` in node details; frontend rendering uses `score_known` to display `"Unknown (Suspicious Context)"` rather than a misleading raw number. |
| **Backward Compatibility with Existing Graphs** | High | Low | Maintain `IMPORTANT_RELATIONSHIPS` check as a fallback so legacy/unmarked edges continue to score correctly. |

---

## 6. Current Workaround in Codebase & Where to Start Next

### 6.1 What Was Shipped as an Interim Workaround (Sprint 1 Hotfix)
While the full open-context architecture is scheduled for a future sprint, an **immediate interim workaround** has been applied to the live codebase:
1. **Relationship Nomenclature Alignment:**
   * Changed `"dropped"` to `"dropped_files"` across `backend/agents/malware.py`, `backend/graph/state.py`, and `backend/tests/test_state_merge.py`.
   * *Effect:* Dropped IOCs discovered by the malware specialist now match `IMPORTANT_RELATIONSHIPS` in `lead_hunter_synthesis.py` and `dot_builder.py`, giving them `+10` points in `_score_edges()`.
2. **High-Signal Gate Relaxation for Unscored Nodes:**
   * Updated `_compute_high_signal()` in `backend/agents/lead_hunter_synthesis.py`:
     ```python
     score_ok = node["score"] >= 80 or (node["score"] > HIGH_SIGNAL_THREAT_SCORE and qualifiers >= 2)
     unknown_but_specialist_discovered = (not node["score_known"]) and (qualifiers >= 1)
     qualifies = score_ok or unknown_but_specialist_discovered
     ```
   * *Effect:* Unscored pivot entities (`not node["score_known"]`) with at least 1 qualifier (such as specialist discovery `"malware_context"` / `"infra_context"`) are now admitted into `high_signal_node_ids`.

### 6.2 Limitations of the Current Workaround
* **Tied Edge Scores (`102` vs `102`):** Because dropped files now receive `+10` points from `IMPORTANT_RELATIONSHIPS`, they score `102` (`92` root score + `10` important rel). However, benign CDN domains (`contacted_domains`) also score `102`. If a hunt produces more than 40 tied edges, Python's sort order may still evict some dropped files.
* **No Synthetic Baseline Score:** Unscored nodes still have `node["score"] = 0` (coerced). They do not yet receive the synthetic `70` baseline score, preventing their connected edges from reaching the `112` score needed to cleanly outrank CDN noise.

### 6.3 Where to Start Next (Handoff Instructions for Next Sprint)
When resuming this roadmap, **start execution in this exact order:**
1. **Step 1 — Phase 1 (`RAC-P1-1`):** Open `backend/utils/graph_cache.py` and extend `add_relationship()` and `add_entity()` to accept and persist open metadata keys (`attack_chain`, `context`, `signal_reason`).
2. **Step 2 — Phase 2 (`RAC-P2-1` & `RAC-P2-2`):** Open `backend/agents/malware.py` (`malware_analysis_tool`) and `backend/agents/infrastructure.py` to attach `{"attack_chain": True, "context": "..."}` when adding entities and relationships to the graph cache.
3. **Step 3 — Phase 3 (`RAC-P3-1` & `RAC-P3-2`):** Open `backend/agents/lead_hunter_synthesis.py`:
   * In `_compute_high_signal()`, replace `unknown_but_specialist_discovered` with the open-field check `has_agent_context`, and assign `node["score"] = 70` when `not node["score_known"] and qualifies`.
   * In `_score_edges()`, reward edge qualifiers when `data.get("attack_chain")` or `data.get("context")` is present, boosting those edges to `110–120+` above benign background noise.
