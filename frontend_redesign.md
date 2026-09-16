# Harimau Frontend Redesign & Migration Prompt

> **Purpose**: Use the prompt below in a new chat session to migrate the validated Harimau Editorial Dossier and Attack Flow Workbench from the standalone prototype (`/prototype`) into the production Next.js frontend (`/app`).

---

## `/teamwork-preview` Agent Swarm Prompt (Copy & Paste)

```markdown
/teamwork-preview Migrate the validated Harimau Threat Intelligence Editorial Dossier workbench from `/prototype/index.html` into the production Next.js frontend in `/app`.

### CRITICAL: 3-Stage Contract-First Swarm Execution Plan
To prevent merge conflicts and TypeScript prop mismatches, execute this migration strictly in 3 sequential stages where Stage 2 runs as a 3-agent parallel swarm with strict file isolation:

---

### Stage 1: Shared TypeScript Contract & Pure Utilities (Sequential — Run First)
**Owner**: Architect / Lead Agent
**Files to Create**:
1. `app/src/lib/dossier-types.ts` — Define and freeze all shared TypeScript interfaces:
   - `DossierJob`, `SpecialistReportData`, `MalwareSpecialistReport`, `InfraSpecialistReport`
   - `ParsedDotNode`, `ParsedDotEdge`, `ParsedDotGraph`
   - `SwimLaneCategory` (`'ingress' | 'execution' | 'decoy' | 'dropped' | 'c2'`), `SwimLaneStage`
   - `IocEntry` (`type`, `value`, `notes`, `confidence`)
   - Component prop contracts including shared callbacks:
     `onJumpToNode: (nodeId: string) => void`
     `onCopyIoc: (value: string) => void`
2. `app/src/lib/dossier-utils.ts` — Port pure transformation functions from `prototype/index.html`:
   - `normalizeReportSections(markdown: string)`: Deterministically reorder and renumber incoming backend LLM markdown into the strict 1–7 Dossier sequence:
     `1. Executive Summary`, `2. Attack Narrative`, `3. Specialist Reports`, `4. Investigation Timeline`, `5. Technical Analysis`, `6. Attack Flow Diagram`, `7. Appendix`.
   - `parseDotToGraph(dotString: string): ParsedDotGraph`: Extract DOT nodes, attributes, threat scores, decoy flags, and edges.
   - `deriveSwimLanes(parsedGraph: ParsedDotGraph, rootIoc: string): SwimLaneStage[]`: Categorize nodes into active behavioral stages (`ingress`, `execution`, `decoy`, `dropped`, `c2`).
   - `extractFallbackIocs(parsedGraph: ParsedDotGraph, rawGraphData?: any): IocEntry[]`: Fallback IOC extractor when `appendixIocs` is empty.
3. `app/src/lib/dossier-utils.test.ts` — Unit tests verifying section normalization and stage counting against `prototype/data/clickfix_example.json` (5 active stages), `prototype/data/sample_minecraft_mod.json` (4 active stages), and `prototype/data/sample_investigation.json` (3 active stages).

*Gate*: Do NOT launch Stage 2 until `dossier-types.ts` and `dossier-utils.ts` compile cleanly.

---

### Stage 2: Parallel 3-Agent Component Swarm (100% File-Isolated)
Once Stage 1 completes, spawn 3 subagents concurrently. Every subagent MUST import types/helpers exclusively from `@/lib/dossier-types` and `@/lib/dossier-utils` and write ONLY to its assigned files:

#### Subagent A — Dossier Core, Specialist Grid & Companion Rail
**Assigned Files (Strict Isolation)**:
- `app/src/components/investigation/DossierMasthead.tsx`:
  - TLP classification amber pill, Job ID badge, title, synthesis metadata, timestamp.
  - 4-card Bento metrics grid: GTI Score `/100` with color badge, Execution Status, Primary IOC Type, Graph Entities / Pivots count.
- `app/src/components/investigation/SpecialistReportsGrid.tsx`:
  - Integrated dual-card autonomous specialist grid (`grid-cols-1 lg:grid-cols-2 gap-6`):
    - **Malware Analysis Specialist (`AGENT-01`)**: Verdict badge, analyst synthesis callout, MITRE ATT&CK tags, discovered findings, investigated targets with 1-click copy & Jump-to-Canvas (`onJumpToNode`), plus collapsible full technical reverse-engineering teardown (`ReactMarkdown` + `remark-gfm`).
    - **Infrastructure Specialist (`AGENT-02`)**: Verdict & confidence, passive DNS / registrar profiling, network MITRE badges, JARM / ASN / routing findings, investigated infrastructure nodes, and collapsible network teardown.
- `app/src/components/investigation/DossierCompanionRail.tsx`:
  - Right-hand sticky companion rail (`w-80 shrink-0 hidden lg:block`).
  - "Explore Topology in Canvas" quick-action card.
  - Quick-jump Table of Contents linking to `#section-1-...` through `#section-7-...` with `scroll-mt-20` offset compensation.
  - Target IOC summary card with 1-click copy.

#### Subagent B — Attack Flow Workbench & Dynamic Swim Lanes
**Assigned Files (Strict Isolation)**:
- `app/src/components/investigation/AttackFlowSection.tsx`:
  - Section 6 container with mode switcher (`Unified`, `Diagram Only`, `Swim Lanes Only`), layout orientation toggle (`LR` / `TB`), Zoom In, Zoom Out, Center on Root, Fit All, and View DOT Source modal.
  - Interactive Graphviz diagram rendered via `d3-graphviz`.
- `app/src/components/investigation/TacticalSwimLanes.tsx`:
  - Report-derived dynamic behavioral swim lanes (`ingress`, `execution`, `decoy`, `dropped`, `c2`).
  - **CRITICAL Tailwind CSS v4 Requirement**: Do NOT use dynamic string interpolation like `lg:grid-cols-${numStages}` (Tailwind's static AST scanner will purge it). Bind `--num-stages` via inline CSS custom property and use arbitrary value syntax:
    ```tsx
    <div
      style={{ "--num-stages": activeStages.length } as React.CSSProperties}
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[repeat(var(--num-stages),minmax(0,1fr))] gap-4 w-full items-stretch"
    >
    ```
  - Enforce `w-full items-stretch h-full` on swim lanes so cards stretch edge-to-edge across 100% of the container width without empty voids on wide monitors.
  - Sequential stage pill badges (`#1`..`#N`), category icons, node count pills, execution pipeline header (`Stage 1 ➔ Stage N`), and `min-w-0 w-full truncate` on item cards.
- `app/src/components/investigation/DecoyInsightBanner.tsx`:
  - MITRE T1036 Defense Evasion callout banner highlighting dual-use / legitimate decoy infrastructure (e.g., official `nodejs.org` runtime abuse).

#### Subagent C — Appendix Observables Table
**Assigned Files (Strict Isolation)**:
- `app/src/components/investigation/AppendixIocTable.tsx`:
  - Section 7 complete observables IOC table with color-coded type badges (`domain`, `ip`, `file`, `url`), confidence pills, context notes, 1-click clipboard copy, and Jump-to-Canvas action.

---

### Stage 3: Page Integration & Verification (Sequential — Run Last)
**Owner**: Lead / Integration Agent
**Target File**: `app/src/app/investigate/[id]/page.tsx`
1. **Fluid ~75% Viewport Layout**:
   - Update outer reading container to adapt across screens: `w-full sm:w-[92%] md:w-[88%] lg:w-[82%] xl:w-[75%] mx-auto`.
   - Remove arbitrary `max-w-[1020px]` constraints on the reading canvas (`flex-1 min-w-0`).
2. **Dossier & Canvas Dual-Mode Integration**:
   - Render the 7-section Editorial Dossier alongside `DossierCompanionRail` in Editorial Mode.
   - Preserve existing real-time SSE streaming (`app/src/lib/investigation-stream.ts`) and Spatial Topology Canvas (`@xyflow/react`).
   - Connect `onJumpToNode(nodeId)` from all Dossier components so clicking any indicator switches to Spatial Canvas mode and focuses/centers on that node.
3. **Security & Quality Rules**:
   - **NO `dangerouslySetInnerHTML`**: Rely strictly on React JSX auto-escaping and `ReactMarkdown` (`remark-gfm`) for untrusted strings.
   - Run `npm test` and `npm run build` inside `/app` and fix any TypeScript or ESLint errors before completing.
```

