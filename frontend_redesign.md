# Harimau Frontend Redesign & Migration Prompt

> **Purpose**: Use the prompt below in a new chat session to migrate the validated Harimau Editorial Dossier and Attack Flow Workbench from the standalone prototype (`/prototype`) into the production Next.js frontend (`/app`).

---

## Agent Prompt (Copy & Paste into New Chat)

```markdown
You are tasked with migrating the validated Harimau Threat Intelligence Editorial Dossier workbench from the prototype in `/prototype` into the production Next.js frontend in `/app`.

### Context & Source of Truth
- **Branch**: `feature/prototype-editorial-dossier`
- **Reference Prototype**: `prototype/index.html` (fully functional standalone implementation with Tailwind, D3, Lucide, Graphviz WASM, force simulation, and responsive layouts).
- **Test Fixtures**: `prototype/data/` (`clickfix_example.json`, `sample_minecraft_mod.json`, `sample_investigation.json`).
- **Target Production Codebase**: `/app` (Next.js 16 App Router, React 19, Tailwind CSS v4, `@xyflow/react`, `d3-graphviz`, `react-markdown`, `remark-gfm`).
  - Primary view: `app/src/app/investigate/[id]/page.tsx`
  - Stream handler: `app/src/lib/investigation-stream.ts`

---

### Core Architectural Requirements

#### 1. Fluid ~75% Viewport Spacing
- Update container layout to adapt dynamically across screen sizes:
  - Wide monitors (32", 34" ultrawides): `xl:w-[75%]`
  - Standard QHD (27"): `lg:w-[82%]`
  - Laptops / medium screens: `md:w-[88%]`
  - Small / mobile screens: `w-full sm:w-[92%]`
- Remove arbitrary `max-w-[1020px]` constraints on the reading canvas (`flex-1 min-w-0`), allowing the editorial prose, tables, and attack flow diagrams to stretch comfortably.

#### 2. Strict 7-Section Dossier Architecture
The investigation brief must strictly follow this exact 7-section sequence:
1. **Section 1. Executive Summary**:
   - Classification masthead (TLP amber pill, Job ID badge, title, synthesis metadata, timestamp).
   - At-A-Glance Bento metric cards (GTI Score /100 with color badge, Execution Status, Primary IOC Type, Graph Entities / Pivots count).
   - Core executive summary prose.
2. **Section 2. Attack Narrative**:
   - End-to-end campaign story synthesized from intelligence telemetry.
3. **Section 3. Specialist Reports**:
   - Integrated dual-card autonomous specialist intelligence grid:
     - **Malware Analysis Specialist (`AGENT-01`)**: Verdict badge, analyst synthesis callout, MITRE ATT&CK technique tags, discovered findings, investigated targets with 1-click clipboard copy and Jump-to-Canvas actions, plus collapsible full technical reverse-engineering teardowns.
     - **Infrastructure Specialist (`AGENT-02`)**: Verdict & confidence, passive DNS / registrar profiling, network MITRE badges, JARM / ASN / routing findings, investigated infrastructure nodes, and collapsible network teardowns.
4. **Section 4. Investigation Timeline**:
   - Chronological event sequence with formatted timestamps, sources, and event descriptions.
5. **Section 5. Technical Analysis**:
   - In-depth forensic deep dive and execution mechanics.
6. **Section 6. Attack Flow Diagram**:
   - Interactive Graphviz/DOT & Cytoscape diagram views with controls: Zoom In, Zoom Out, Center on Root, Fit All, Layout switcher (LR / TB), View Mode switcher (Unified / Diagram / Telemetry), and View DOT source modal.
   - **Report-Derived Dynamic Swim Lanes**:
     - Dynamic behavioral grouping: `ingress`, `execution`, `decoy`, `dropped`, `c2`.
     - Count active stages (`numStages`) and assign dynamic full-width grid columns: `lg:grid-cols-${numStages}` (`lg:grid-cols-4`, `lg:grid-cols-5`, `lg:grid-cols-3`).
     - Enforce `w-full items-stretch h-full` on all swim lanes so cards stretch edge-to-edge across 100% of the container width without empty voids on wide screens.
     - Add sequential stage pill badges (`#1`, `#2`, `#3`, `#4`), category icons, node count pills, and an execution pipeline header (`Stage 1 ➔ Stage N`).
     - Preserve authentic decoy/dual-use insights callouts (e.g., legitimate Node.js runtime downloads or authentic login redirects) to prevent losing threat evasion context.
     - Use `min-w-0 w-full truncate` on item cards to prevent long paths or commands from distorting columns.
7. **Section 7. Appendix**:
   - Complete observables IOC table with color-coded type badges (domain, ip, file, url), context notes, and 1-click clipboard copy.

#### 3. Sticky Reading Companion Rail
- Right-hand sticky rail (`w-80 shrink-0 hidden lg:block`):
  - **Explore Topology in Canvas** quick-action card.
  - **Dossier Contents Quick-Jump Table of Contents** linking directly to `#section-1-...` through `#section-7-...` with `scroll-mt-20` offset compensation.
  - **Target IOC Card** with 1-click clipboard copy and timestamps.

#### 4. Dynamic Report Normalizer (`normalizeReportSections`)
- Automatically renumber and re-order incoming backend markdown sections so that live backend jobs or historical runs adhere to the 1–7 numbering regardless of raw LLM formatting.

---

### Component Decomposition Strategy for Next.js

Organize the implementation into modular React components under `app/src/components/investigation/`:
1. `DossierMasthead.tsx` — TLP badge, case ID, title, and Bento metrics grid.
2. `SpecialistReportsGrid.tsx` — Agent-01 Malware & Agent-02 Infrastructure cards with collapsible teardowns.
3. `AttackFlowSection.tsx` — Graphviz / ReactFlow viewport, mode switcher, and zoom controls.
4. `TacticalSwimLanes.tsx` — Dynamic width-aligned behavioral stage columns (`lg:grid-cols-${numStages}`).
5. `DecoyInsightBanner.tsx` — T1036 Evasion callout for dual-use & legitimate decoy services.
6. `AppendixIocTable.tsx` — IOC table with badges, fallback extraction, and copy actions.
7. `DossierCompanionRail.tsx` — Sticky quick-jump TOC and target IOC summary.

---

### Verification Checklist
- [ ] Next.js app builds cleanly with zero TypeScript or lint errors (`npm run build`).
- [ ] Tested against `prototype/data/clickfix_example.json` (5 stages active, 100% width).
- [ ] Tested against `prototype/data/sample_minecraft_mod.json` (4 stages active, 100% width).
- [ ] Tested against `prototype/data/sample_investigation.json` (3 stages active, 100% width).
- [ ] SSE real-time investigation streaming in `app/src/lib/investigation-stream.ts` functions seamlessly without regressions.
- [ ] Anchor navigation in the companion rail smoothly scrolls to each section without header occlusion.
```
