import type {
  DossierJob,
  DossierSection,
  IocEntry,
  ParsedDossierReport,
  ParsedDotEdge,
  ParsedDotGraph,
  ParsedDotNode,
  SwimLaneStage,
} from "./dossier-types";

export const CANONICAL_SECTIONS: Array<{
  number: number;
  id: string;
  defaultTitle: string;
  numberedMatcher: RegExp;
  unnumberedMatcher: RegExp;
}> = [
  {
    number: 1,
    id: "section-1-executive-summary",
    defaultTitle: "1. Executive Summary",
    numberedMatcher: /^#{1,4}\s*\d+\.\s*Executive\s*Summary([^\n]*)/i,
    unnumberedMatcher: /^#{1,4}\s*Executive\s*Summary(\s*:[^\n]*)?$/i,
  },
  {
    number: 2,
    id: "section-2-attack-narrative",
    defaultTitle: "2. Attack Narrative",
    numberedMatcher: /^#{1,4}\s*\d+\.\s*Attack\s*Narrative([^\n]*)/i,
    unnumberedMatcher: /^#{1,4}\s*Attack\s*Narrative(\s*:[^\n]*)?$/i,
  },
  {
    number: 3,
    id: "section-3-specialist-reports",
    defaultTitle: "3. Specialist Reports",
    numberedMatcher: /^#{1,4}\s*\d+\.\s*Specialist\s*Reports([^\n]*)/i,
    unnumberedMatcher: /^#{1,4}\s*Specialist\s*Reports(\s*:[^\n]*)?$/i,
  },
  {
    number: 4,
    id: "section-4-investigation-timeline",
    defaultTitle: "4. Investigation Timeline",
    numberedMatcher: /^#{1,4}\s*\d+\.\s*(?:Investigation\s*)?Timeline([^\n]*)/i,
    unnumberedMatcher: /^#{1,4}\s*(?:Investigation\s*)?Timeline(\s*:[^\n]*)?$/i,
  },
  {
    number: 5,
    id: "section-5-technical-analysis",
    defaultTitle: "5. Technical Analysis",
    numberedMatcher: /^#{1,4}\s*\d+\.\s*Technical\s*Analysis([^\n]*)/i,
    unnumberedMatcher: /^#{1,4}\s*Technical\s*Analysis(\s*:[^\n]*)?$/i,
  },
  {
    number: 6,
    id: "section-6-attack-flow-diagram",
    defaultTitle: "6. Attack Flow Diagram",
    numberedMatcher: /^#{1,4}\s*\d+\.\s*Attack\s*Flow([^\n]*)/i,
    unnumberedMatcher: /^#{1,4}\s*Attack\s*Flow(?:\s*Diagram)?(\s*:[^\n]*)?$/i,
  },
  {
    number: 7,
    id: "section-7-appendix",
    defaultTitle: "7. Appendix",
    numberedMatcher: /^#{1,4}\s*\d+\.\s*Appendix([^\n]*)/i,
    unnumberedMatcher: /^#{1,4}\s*Appendix(\s*:[^\n]*)?$/i,
  },
];

/**
 * Deterministically reorders and renumbers incoming backend LLM markdown into
 * the strict 1-7 Dossier sequence:
 * 1. Executive Summary
 * 2. Attack Narrative
 * 3. Specialist Reports
 * 4. Investigation Timeline
 * 5. Technical Analysis
 * 6. Attack Flow Diagram
 * 7. Appendix
 */
// A fenced code block (```...``` or ~~~...~~~) can legitimately contain a line
// like "# Timeline" or "# Appendix" (e.g. a Python/Bash/PowerShell comment)
// that would otherwise be misread as a section heading, splitting the snippet
// across two canonical sections. Track the active opening fence marker and
// ignore single-line inline triple-backtick spans (e.g. ```cmd /c ...```)
// so a same-line closing span never leaves the parser stuck in `inFence` mode.
function updateFenceState(
  trimmedLine: string,
  currentFence: string | null
): string | null {
  if (currentFence === null) {
    const openMatch = /^(`{3,}|~{3,})([^`~]*)$/.exec(trimmedLine);
    return openMatch ? openMatch[1] : null;
  }
  const fenceChar = currentFence[0];
  const minLen = currentFence.length;
  const closeRegex = new RegExp(`^\\${fenceChar}{${minLen},}\\s*$`);
  return closeRegex.test(trimmedLine) ? null : currentFence;
}

export function normalizeReportSections(markdown: string): string {
  if (!markdown || !markdown.trim()) return "";

  const lines = markdown.split(/\r?\n/);
  const preambleLines: string[] = [];
  const bucketMap = new Map<number, { headerSuffix: string; bodyLines: string[] }>();

  // Check which canonical sections already have explicit numbered headings
  const numberedPresent = new Set<number>();
  let prescanFence: string | null = null;
  for (const line of lines) {
    const trimmed = line.trim();
    if (prescanFence === null) {
      for (const sec of CANONICAL_SECTIONS) {
        if (sec.numberedMatcher.test(trimmed)) {
          numberedPresent.add(sec.number);
        }
      }
    }
    prescanFence = updateFenceState(trimmed, prescanFence);
  }

  let currentBucket: number | null = null;
  let activeFence: string | null = null;

  for (const line of lines) {
    const trimmed = line.trim();
    let matchedSection: (typeof CANONICAL_SECTIONS)[number] | null = null;
    let suffix = "";

    if (activeFence === null) {
      for (const sec of CANONICAL_SECTIONS) {
        const numMatch = sec.numberedMatcher.exec(trimmed);
        if (numMatch) {
          matchedSection = sec;
          suffix = numMatch[1] || "";
          break;
        }
        // Only allow unnumbered header if this section does not have a numbered header anywhere
        // AND it hasn't been bucketed yet
        if (!numberedPresent.has(sec.number) && !bucketMap.has(sec.number)) {
          const unnumMatch = sec.unnumberedMatcher.exec(trimmed);
          if (unnumMatch) {
            matchedSection = sec;
            suffix = unnumMatch[1] || "";
            break;
          }
        }
      }
    }

    activeFence = updateFenceState(trimmed, activeFence);

    if (matchedSection) {
      const isRepeat = bucketMap.has(matchedSection.number);
      currentBucket = matchedSection.number;
      if (!isRepeat) {
        bucketMap.set(currentBucket, { headerSuffix: suffix, bodyLines: [] });
      } else {
        // A repeated/variant heading for an already-bucketed section (e.g. a
        // second "### 2. Attack Narrative" further down the report). Keep
        // its text as a sub-heading in the body instead of silently
        // dropping it while still merging the content into the same
        // canonical section. Strip the leading section number too (not just
        // the "#" markers) so the synthesized "####" line can't itself be
        // re-matched as a numbered heading by parseDossierReport's second
        // pass over this function's output.
        const headingText = trimmed
          .replace(/^#{1,4}\s*/, "")
          .replace(/^\d+\.\s*/, "")
          .trim();
        if (headingText) {
          bucketMap.get(currentBucket)!.bodyLines.push(`#### ${headingText}`);
        }
      }
    } else {
      if (currentBucket === null) {
        preambleLines.push(line);
      } else {
        bucketMap.get(currentBucket)!.bodyLines.push(line);
      }
    }
  }

  const outputParts: string[] = [];
  const preamble = preambleLines.join("\n").trim();
  if (preamble) {
    outputParts.push(preamble);
  }

  for (const sec of CANONICAL_SECTIONS) {
    const existing = bucketMap.get(sec.number);
    let headerLine = `### ${sec.defaultTitle}`;
    if (existing && existing.headerSuffix) {
      const cleanSuffix = existing.headerSuffix.trim();
      if (cleanSuffix.startsWith(":")) {
        headerLine = `### ${sec.defaultTitle}${existing.headerSuffix}`;
      } else if (
        sec.number === 6 &&
        cleanSuffix.toLowerCase().startsWith("diagram")
      ) {
        headerLine = `### 6. Attack Flow ${cleanSuffix}`;
      } else if (cleanSuffix.length > 0) {
        headerLine = `### ${sec.defaultTitle} ${cleanSuffix}`;
      }
    }

    const body = existing ? existing.bodyLines.join("\n").trim() : "";
    if (body) {
      outputParts.push(`${headerLine}\n\n${body}`);
    } else {
      outputParts.push(headerLine);
    }
  }

  return outputParts.join("\n\n");
}

/**
 * Extract DOT nodes, attributes, threat scores, decoy flags, and edges from a Graphviz DOT string.
 */
export function parseDotToGraph(
  dotString: string,
  rootIoc: string = "",
  rootGtiScore: number | undefined = undefined,
  rootRiskLevel: string | undefined = undefined
): ParsedDotGraph {
  const nodesMap = new Map<string, ParsedDotNode>();
  const edges: ParsedDotEdge[] = [];
  if (!dotString) return { nodes: [], edges: [] };

  const rootIocLower = (rootIoc || "").toLowerCase();

  // 1. Parse node declarations anchored to line start so edge targets are never misparsed
  const nodeRegex = /^\s*"([^"]+)"\s*\[([\s\S]*?)\]\s*;\s*$/gm;
  let match: RegExpExecArray | null;

  while ((match = nodeRegex.exec(dotString)) !== null) {
    const id = match[1];
    const attrs = match[2];
    const labelMatch = /label="([^"]+)"/.exec(attrs);
    const rawLabel = labelMatch ? labelMatch[1].replace(/\\n/g, "\n") : id;
    const rawLabelLower = rawLabel.toLowerCase();
    const idLower = id.toLowerCase();
    const isRoot =
      Boolean(rootIoc) && (id === rootIoc || idLower === rootIocLower);

    const isDecoy =
      attrs.includes("dashed") ||
      attrs.toLowerCase().includes("legitimate") ||
      attrs.toLowerCase().includes("decoy") ||
      rawLabelLower.includes("legitimate") ||
      rawLabelLower.includes("decoy");

    // The root's own DOT color/label is an LLM heuristic like any other
    // node's, so it should not be overridden by "isRoot" alone — a benign
    // investigation's root must not always render as MALICIOUS. Where the
    // DOT doesn't clearly color the root, fall back to the job's actual
    // assessed risk level rather than assuming malice.
    const rootRiskLevelUpper = (rootRiskLevel || "").toUpperCase();
    const rootLooksMalicious = isRoot && rootRiskLevelUpper.includes("MALICIOUS");
    const rootLooksSuspicious = isRoot && rootRiskLevelUpper.includes("SUSPICIOUS");

    const isMalicious =
      attrs.includes("#ef4444") ||
      attrs.includes("#7f1d1d") ||
      attrs.includes("#581c87") ||
      attrs.includes("#a855f7") ||
      rawLabelLower.includes("malicious") ||
      rawLabelLower.includes("lure") ||
      rawLabelLower.includes("c2") ||
      rootLooksMalicious;

    const isSuspicious =
      !isMalicious &&
      (attrs.includes("#f59e0b") ||
        attrs.includes("#451a03") ||
        rawLabelLower.includes("lolbin") ||
        rootLooksSuspicious);

    let entityType = "entity";
    if (
      idLower.endsWith(".zip") ||
      idLower.endsWith(".dll") ||
      idLower.endsWith(".js") ||
      idLower.endsWith(".vbs") ||
      rawLabelLower.includes(".zip") ||
      rawLabelLower.includes(".js") ||
      id.length === 64
    ) {
      entityType = "file";
    } else if (
      idLower.endsWith(".exe") ||
      rawLabelLower.includes("browser") ||
      rawLabelLower.includes("process") ||
      rawLabelLower.includes("lolbin") ||
      rawLabelLower.includes("runtime")
    ) {
      entityType = "process";
    } else if (idLower.startsWith("http") || rawLabelLower.includes("http")) {
      entityType = "url";
    } else if (
      /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/.test(id) ||
      /\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/.test(rawLabel)
    ) {
      entityType = "ip_address";
    } else if (
      id.includes(".") ||
      rawLabelLower.includes(".com") ||
      rawLabelLower.includes(".org")
    ) {
      entityType = "domain";
    }

    let friendlyName = "";
    const lines = rawLabel.split("\n");
    if (lines.length > 1) {
      friendlyName = lines[1].replace(/^[([<{]+|[)\]>}]+$/g, "").trim();
    }

    nodesMap.set(id, {
      id,
      label: friendlyName || id,
      friendlyName,
      rawLabel,
      isRoot,
      entityType,
      isDecoy,
      threatScore: isRoot ? rootGtiScore : undefined,
      verdict: isMalicious
        ? "MALICIOUS"
        : isSuspicious
          ? "SUSPICIOUS"
          : isDecoy
            ? "BENIGN"
            : isRoot
              ? rootRiskLevel || "TARGET"
              : "UNKNOWN",
      isMalicious: isMalicious && !isDecoy,
    });
  }

  // 2. Parse edge declarations: "source" -> "target" [label="..."];
  const edgeRegex = /"([^"]+)"\s*->\s*"([^"]+)"(?:\s*\[([\s\S]*?)\])?\s*;/g;
  while ((match = edgeRegex.exec(dotString)) !== null) {
    const source = match[1];
    const target = match[2];
    const attrs = match[3] || "";
    const lm = /label="([^"]*)"/.exec(attrs);
    const label = lm ? lm[1] : "related_to";

    if (!nodesMap.has(source)) {
      nodesMap.set(source, {
        id: source,
        label: source,
        entityType: "entity",
        threatScore: undefined,
        verdict: "UNKNOWN",
      });
    }
    if (!nodesMap.has(target)) {
      nodesMap.set(target, {
        id: target,
        label: target,
        entityType: "entity",
        threatScore: undefined,
        verdict: "UNKNOWN",
      });
    }
    edges.push({ source, target, label });
  }

  return { nodes: Array.from(nodesMap.values()), edges };
}

/**
 * Categorize nodes into active behavioral stages (ingress, execution, decoy, dropped, c2).
 */
export function deriveSwimLanes(
  parsedGraph: ParsedDotGraph,
  rootIoc: string,
  rootJob?: Partial<DossierJob>
): SwimLaneStage[] {
  const allNodes = parsedGraph?.nodes || [];
  const ingressList: ParsedDotNode[] = [];
  const execList: ParsedDotNode[] = [];
  const decoyList: ParsedDotNode[] = [];
  const droppedList: ParsedDotNode[] = [];
  const c2List: ParsedDotNode[] = [];

  allNodes.forEach((n) => {
    const idL = n.id.toLowerCase();
    const lblL = (n.rawLabel || n.label || "").toLowerCase();

    // Decoy / Dual-use
    if (
      n.isDecoy ||
      idL.includes("nodejs.org") ||
      idL.includes("microsoftonline") ||
      lblL.includes("legitimate") ||
      lblL.includes("decoy")
    ) {
      decoyList.push(n);
    }
    // Ingress / Lure
    else if (
      idL.includes("firefox") ||
      idL.includes("autoupdatet") ||
      idL.includes("lure") ||
      idL.includes("discordapp") ||
      idL.includes("jenny.zip") ||
      lblL.includes("lure") ||
      lblL.includes("browser") ||
      (n.isRoot && (n.entityType === "domain" || n.entityType === "url"))
    ) {
      ingressList.push(n);
    }
    // Execution / LOLBin
    else if (
      idL.includes("powershell") ||
      idL.includes("javaw") ||
      idL.includes("msedge") ||
      idL.includes("cmd.exe") ||
      lblL.includes("lolbin") ||
      lblL.includes("execution") ||
      (n.isRoot && n.entityType === "file")
    ) {
      execList.push(n);
    }
    // Dropped / Secondary File
    else if (
      idL.endsWith(".js") ||
      idL.endsWith(".vbs") ||
      idL.endsWith(".dll") ||
      idL.endsWith(".zip") ||
      idL.includes("_js") ||
      idL.includes("_vbs") ||
      idL.includes("_dll") ||
      idL.includes("_zip") ||
      lblL.includes(".js") ||
      lblL.includes(".vbs") ||
      lblL.includes(".dll") ||
      lblL.includes(".zip") ||
      lblL.includes("dropped") ||
      lblL.includes("stager") ||
      lblL.includes("archive") ||
      (idL.endsWith(".exe") &&
        !idL.includes("firefox") &&
        !idL.includes("node") &&
        !idL.includes("powershell"))
    ) {
      droppedList.push(n);
    }
    // C2 & Network Callbacks
    else {
      c2List.push(n);
    }
  });

  // Ensure root IOC is represented if both ingress and execution lists are empty
  if (ingressList.length === 0 && execList.length === 0 && rootIoc) {
    execList.push({
      id: rootIoc,
      label: rootIoc,
      entityType: rootJob?.ioc_type || "target",
      verdict: rootJob?.risk_level || "TARGET",
      threatScore:
        typeof rootJob?.gti_score === "number" ? rootJob.gti_score : undefined,
      // Derived from the job's actual assessed risk level, not assumed —
      // a benign root must not be flagged malicious just for being the root.
      isMalicious: Boolean(rootJob?.risk_level?.toUpperCase().includes("MALICIOUS")),
    });
  }

  const activeStages: SwimLaneStage[] = [];

  if (ingressList.length > 0) {
    activeStages.push({
      id: "ingress",
      category: "ingress",
      title: "Ingress & Delivery Vector",
      badgeText: `${ingressList.length} Nodes`,
      icon: "download-cloud",
      cardBorder: "border-sky-500/30",
      headerColor: "text-sky-400",
      numBg: "bg-sky-950 text-sky-400 border border-sky-800/50",
      badgeBg: "bg-sky-950 text-sky-300 border border-sky-800/50",
      itemBadgeStyle: "bg-sky-950/80 text-sky-300 border border-sky-800/50",
      itemRoleLabel: "Lure / Ingress",
      nodes: ingressList,
    });
  }

  if (execList.length > 0) {
    activeStages.push({
      id: "execution",
      category: "execution",
      title: "Execution & Tool Transfer",
      badgeText: `${execList.length} Tools`,
      icon: "terminal",
      cardBorder: "border-amber-500/30",
      headerColor: "text-amber-400",
      numBg: "bg-amber-950 text-amber-400 border border-amber-800/50",
      badgeBg: "bg-amber-950 text-amber-300 border border-amber-800/50",
      itemBadgeStyle: "bg-amber-950 text-amber-300 border border-amber-800/60",
      itemRoleLabel: "Process / Stager",
      nodes: execList,
    });
  }

  if (decoyList.length > 0) {
    activeStages.push({
      id: "decoy",
      category: "decoy",
      title: "Decoy & Dual-Use Infra",
      badgeText: `${decoyList.length} Legitimate`,
      icon: "shield",
      cardBorder: "border-teal-500/40",
      headerColor: "text-teal-400",
      numBg: "bg-teal-950 text-teal-400 border border-teal-800/50",
      badgeBg: "bg-teal-950 text-teal-300 border border-teal-800/50",
      itemBadgeStyle: "bg-teal-950 text-teal-300 border border-teal-800/50",
      itemRoleLabel: "Legitimate Decoy",
      nodes: decoyList,
    });
  }

  if (droppedList.length > 0) {
    activeStages.push({
      id: "dropped",
      category: "dropped",
      title: "Unpacked / Dropped Files",
      badgeText: `${droppedList.length} Artifacts`,
      icon: "file-output",
      cardBorder: "border-rose-500/30",
      headerColor: "text-rose-400",
      numBg: "bg-rose-950 text-rose-400 border border-rose-800/50",
      badgeBg: "bg-rose-950 text-rose-300 border border-rose-800/50",
      itemBadgeStyle: "bg-rose-950/80 text-rose-300 border border-rose-800/50",
      itemRoleLabel: "Dropped Payload",
      nodes: droppedList,
    });
  }

  if (c2List.length > 0) {
    activeStages.push({
      id: "c2",
      category: "c2",
      title: "C2 Callbacks & Staging",
      badgeText: `${c2List.length} Endpoints`,
      icon: "radio",
      cardBorder: "border-purple-500/30",
      headerColor: "text-purple-400",
      numBg: "bg-purple-950 text-purple-400 border border-purple-800/50",
      badgeBg: "bg-purple-950 text-purple-300 border border-purple-800/50",
      itemBadgeStyle: "bg-purple-950/80 text-purple-300 border border-purple-800/50",
      itemRoleLabel: "C2 / Pivot",
      nodes: c2List,
    });
  }

  return activeStages;
}

/**
 * Fallback IOC extractor when appendixIocs JSON block is empty or absent.
 */
export function extractFallbackIocs(
  parsedGraph: ParsedDotGraph,
  rawGraphData?: { nodes?: unknown[] } | null
): IocEntry[] {
  const nodes: Array<Record<string, unknown>> =
    parsedGraph?.nodes && parsedGraph.nodes.length > 0
      ? (parsedGraph.nodes as unknown as Array<Record<string, unknown>>)
      : rawGraphData?.nodes && Array.isArray(rawGraphData.nodes)
        ? (rawGraphData.nodes as Array<Record<string, unknown>>)
        : [];

  return nodes.map((n) => ({
    type: String(n.entityType || n.entity_type || "Indicator").replace(/_/g, " "),
    value: String(n.id || ""),
    notes: String(
      n.friendlyName ||
        (n.isRoot
          ? "Target Investigation Root"
          : n.isMalicious
            ? "Correlated Threat Artifact"
            : "Discovered Infrastructure")
    ),
    confidence: n.isRoot || n.isMalicious ? "High" : "Medium",
  }));
}

/**
 * Parse a complete raw report markdown string into structured Dossier sections,
 * extracting any embedded Graphviz DOT block and Appendix IOC JSON array.
 */
export function parseDossierReport(
  rawReport: string,
  job?: DossierJob,
  rawGraphData?: { nodes?: unknown[] } | null
): ParsedDossierReport {
  let cleanMarkdown = rawReport || "";

  // 1. Extract DOT code block
  const dotRegex = /```(?:dot|graphviz)?\s*(digraph[\s\S]*?)```/i;
  const dotMatch = dotRegex.exec(cleanMarkdown);
  let rawDotCode: string | null = null;
  if (dotMatch) {
    rawDotCode = dotMatch[1].trim();
    cleanMarkdown = cleanMarkdown.replace(dotMatch[0], "");
  }

  // 2. Extract Appendix IOCs JSON block
  let extractedIocs: IocEntry[] = [];
  let chosenMatch: { full: string; json: string } | null = null;

  // 2a. Look specifically for an explicit ```iocs block anywhere
  // The JSON body is matched with a "not a fence" guard ((?!```)) on every
  // character, not just a non-greedy [\s\S]*? — otherwise an earlier,
  // unrelated fenced block whose content never closes with `}]` lets the
  // match bridge across that fence's closing ``` and swallow (or corrupt)
  // a later, valid JSON block, advancing lastIndex past it in the process.
  const explicitIocsRegex = /```iocs\s*(\[\s*\{(?:(?!```)[\s\S])*?\}\s*\])\s*```/i;
  const explicitMatch = explicitIocsRegex.exec(cleanMarkdown);
  if (explicitMatch) {
    try {
      const parsed = JSON.parse(explicitMatch[1]);
      if (Array.isArray(parsed)) {
        const candidate: IocEntry[] = parsed
          .map((item: Record<string, unknown>) => ({
            type: String(item.type || "IOC"),
            value: String(item.value || "").trim(),
            notes: String(item.notes || "--"),
            confidence: String(item.confidence || "MEDIUM"),
          }))
          .filter((item) => Boolean(item.value));
        // Only claim this block (and skip 2b/2c) if it actually yielded
        // usable IOCs — an empty/valueless match must fall through instead
        // of silently discarding a real IOC block found later.
        if (candidate.length > 0) {
          extractedIocs = candidate;
          chosenMatch = { full: explicitMatch[0], json: explicitMatch[1] };
        }
      }
    } catch {
      // Ignore malformed JSON block
    }
  }

  // 2b. OR look for a ```json array block that appears within or after the Appendix section heading
  if (!chosenMatch) {
    const appendixHeadingRegex =
      /(?:^|\n)\s*#{1,4}\s*(?:\d+\.\s*)?Appendix[^\n]*/i;
    const appMatch = appendixHeadingRegex.exec(cleanMarkdown);
    if (appMatch && appMatch.index !== undefined) {
      const textAfterAppendix = cleanMarkdown.slice(appMatch.index);
      const jsonRegex = /```(?:json)?\s*(\[\s*\{(?:(?!```)[\s\S])*?\}\s*\])\s*```/gi;
      let jsonMatch: RegExpExecArray | null;
      while ((jsonMatch = jsonRegex.exec(textAfterAppendix)) !== null) {
        try {
          const parsed = JSON.parse(jsonMatch[1]);
          if (Array.isArray(parsed)) {
            const candidate: IocEntry[] = parsed
              .filter(
                (item: Record<string, unknown>) =>
                  item &&
                  typeof item === "object" &&
                  item.value !== undefined &&
                  item.value !== null &&
                  String(item.value).trim().length > 0 &&
                  (item.type !== undefined ||
                    item.confidence !== undefined ||
                    item.notes !== undefined)
              )
              .map((item: Record<string, unknown>) => ({
                type: String(item.type || "IOC"),
                value: String(item.value || "").trim(),
                notes: String(item.notes || "--"),
                confidence: String(item.confidence || "MEDIUM"),
              }));
            if (candidate.length > 0) {
              extractedIocs = candidate;
              chosenMatch = { full: jsonMatch[0], json: jsonMatch[1] };
              break;
            }
          }
        } catch {
          // Ignore malformed JSON block and continue scanning subsequent Appendix JSON blocks
        }
      }
    }
  }

  // 2c. If no Appendix heading is found yet, scan all JSON array blocks
  // and only accept one whose items have a valid non-empty value property (and type or confidence or notes).
  if (!chosenMatch) {
    const allJsonRegex = /```(?:json)?\s*(\[\s*\{(?:(?!```)[\s\S])*?\}\s*\])\s*```/gi;
    let match: RegExpExecArray | null;
    while ((match = allJsonRegex.exec(cleanMarkdown)) !== null) {
      try {
        const parsed = JSON.parse(match[1]);
        if (Array.isArray(parsed)) {
          const validItems = parsed.filter(
            (item: Record<string, unknown>) =>
              item &&
              typeof item === "object" &&
              item.value !== undefined &&
              item.value !== null &&
              String(item.value).trim().length > 0 &&
              (item.type !== undefined ||
                item.confidence !== undefined ||
                item.notes !== undefined)
          );
          if (validItems.length > 0) {
            extractedIocs = validItems.map((item: Record<string, unknown>) => ({
              type: String(item.type || "IOC"),
              value: String(item.value).trim(),
              notes: String(item.notes || "--"),
              confidence: String(item.confidence || "MEDIUM"),
            }));
            chosenMatch = { full: match[0], json: match[1] };
            break;
          }
        }
      } catch {
        // Ignore malformed JSON block
      }
    }
  }

  // Filter extractedIocs so that any item with an empty or whitespace-only value is discarded
  extractedIocs = extractedIocs.filter(
    (item) => item.value && String(item.value).trim().length > 0
  );

  if (chosenMatch) {
    cleanMarkdown = cleanMarkdown.replace(chosenMatch.full, "");
  }

  const parsedDotGraph = rawDotCode
    ? parseDotToGraph(rawDotCode, job?.ioc || "", job?.gti_score ?? undefined, job?.risk_level)
    : { nodes: [], edges: [] };

  const appendixIocs =
    extractedIocs.length > 0
      ? extractedIocs
      : extractFallbackIocs(
          parsedDotGraph,
          rawGraphData || job?.graph || job?.investigation_graph
        );

  const normalizedMarkdown = normalizeReportSections(cleanMarkdown);

  // Split normalizedMarkdown into preamble and 7 sections
  const lines = normalizedMarkdown.split(/\r?\n/);
  const preambleLines: string[] = [];
  const sectionMap = new Map<number, { title: string; lines: string[] }>();

  let activeSecNum: number | null = null;
  let sectionSplitFence: string | null = null;

  for (const line of lines) {
    const trimmedLine = line.trim();
    let matched: (typeof CANONICAL_SECTIONS)[number] | null = null;
    if (sectionSplitFence === null) {
      for (const sec of CANONICAL_SECTIONS) {
        if (sec.numberedMatcher.test(trimmedLine)) {
          matched = sec;
          break;
        }
      }
    }
    sectionSplitFence = updateFenceState(trimmedLine, sectionSplitFence);

    if (matched) {
      activeSecNum = matched.number;
      if (!sectionMap.has(activeSecNum)) {
        const titleText = line.replace(/^#{1,4}\s*/, "").trim();
        sectionMap.set(activeSecNum, { title: titleText, lines: [] });
      }
    } else {
      if (activeSecNum === null) {
        preambleLines.push(line);
      } else {
        sectionMap.get(activeSecNum)!.lines.push(line);
      }
    }
  }

  const sections: DossierSection[] = CANONICAL_SECTIONS.map((sec) => {
    const found = sectionMap.get(sec.number);
    return {
      number: sec.number,
      id: sec.id,
      title: found?.title || sec.defaultTitle,
      markdownBody: found ? found.lines.join("\n").trim() : "",
    };
  });

  return {
    preamble: preambleLines.join("\n").trim(),
    sections,
    rawDotCode,
    parsedDotGraph,
    appendixIocs,
    normalizedMarkdown,
  };
}

export interface NormalizedFallbackNode {
  id: string;
  label: string;
  color?: string;
  entityType: string;
  size: number;
  title?: string;
  isRoot?: boolean;
  isMalicious?: boolean;
  inReport?: boolean;
  threatScore?: number | null;
  verdict?: string | null;
  vendorDetections?: string | null;
}

export interface NormalizedFallbackEdge {
  source: string;
  target: string;
  label: string;
}

export interface NormalizedFallbackGraph {
  nodes: NormalizedFallbackNode[];
  edges: NormalizedFallbackEdge[];
}

/**
 * Normalize a fallback graph object (`job.graph` or raw NetworkX `job.investigation_graph`
 * serialized via `nx.node_link_data`) into the formatted `GraphData` shape expected by
 * the Spatial Canvas (`rebuildSpatialGraph`, `getSmartLabel`, and node inspector).
 *
 * Raw `job.investigation_graph` records store snake_case `entity_type`, nested
 * `gti_assessment`, `links` instead of `edges`, `relationship` instead of `label`,
 * and omit `label`, `isRoot`, `isMalicious`, and `inReport`.
 */
export function normalizeFallbackGraphData(
  rawGraph:
    | {
        nodes?: unknown[];
        edges?: unknown[];
        links?: unknown[];
      }
    | null
    | undefined,
  rootIoc: string = "",
  rootGtiScore?: number | null,
  rootRiskLevel?: string | null
): NormalizedFallbackGraph | null {
  if (!rawGraph || !Array.isArray(rawGraph.nodes)) return null;

  const rootLower = (rootIoc || "").trim().toLowerCase();
  const rootRiskUpper = (rootRiskLevel || "").toUpperCase();
  const rootIsMalicious = rootRiskUpper.includes("MALICIOUS");

  const nodes: NormalizedFallbackNode[] = [];

  for (const rawItem of rawGraph.nodes) {
    if (!rawItem || typeof rawItem !== "object") continue;
    const n = rawItem as Record<string, unknown>;
    const id = String(n.id ?? "").trim();
    if (!id) continue;

    const idLower = id.toLowerCase();
    const isRoot =
      typeof n.isRoot === "boolean"
        ? n.isRoot
        : Boolean(rootLower && idLower === rootLower);

    const entityType = String(
      n.entityType || n.entity_type || n.type || "entity"
    );

    // Extract nested GTI fields when present on raw NetworkX nodes
    const gti =
      n.gti_assessment && typeof n.gti_assessment === "object"
        ? (n.gti_assessment as Record<string, unknown>)
        : null;
    const gtiVerdictObj =
      gti?.verdict && typeof gti.verdict === "object"
        ? (gti.verdict as Record<string, unknown>)
        : null;
    const gtiScoreObj =
      gti?.threat_score && typeof gti.threat_score === "object"
        ? (gti.threat_score as Record<string, unknown>)
        : null;
    const statsObj =
      n.last_analysis_stats && typeof n.last_analysis_stats === "object"
        ? (n.last_analysis_stats as Record<string, unknown>)
        : null;

    const rawVerdictValue =
      typeof n.verdict === "string"
        ? n.verdict
        : typeof gtiVerdictObj?.value === "string"
          ? gtiVerdictObj.value
          : isRoot && rootRiskLevel
            ? rootRiskLevel
            : null;
    const rawVerdict = rawVerdictValue
      ? rawVerdictValue.replace(/^VERDICT_/i, "").toUpperCase()
      : null;

    const rawThreatScore =
      typeof n.threatScore === "number"
        ? n.threatScore
        : typeof gtiScoreObj?.value === "number"
          ? gtiScoreObj.value
          : isRoot && typeof rootGtiScore === "number"
            ? rootGtiScore
            : undefined;

    const maliciousVendors =
      typeof statsObj?.malicious === "number" ? statsObj.malicious : 0;

    const isMalicious =
      typeof n.isMalicious === "boolean"
        ? n.isMalicious
        : Boolean(
            (rawVerdict && rawVerdict.toUpperCase().includes("MALICIOUS")) ||
              maliciousVendors > 3 ||
              (isRoot && rootIsMalicious)
          );

    // Derive a guaranteed non-empty string label so getSmartLabel never crashes
    let derivedLabel = "";
    if (typeof n.label === "string" && n.label.trim()) {
      derivedLabel = n.label.trim();
    } else if (typeof n.host_name === "string" && n.host_name.trim()) {
      derivedLabel = n.host_name.trim();
    } else if (
      typeof n.meaningful_name === "string" &&
      n.meaningful_name.trim()
    ) {
      derivedLabel =
        entityType === "file"
          ? `${id}\n(${n.meaningful_name.trim()})`
          : n.meaningful_name.trim();
    } else if (typeof n.url === "string" && n.url.trim()) {
      derivedLabel = n.url.trim();
    } else if (typeof n.name === "string" && n.name.trim()) {
      derivedLabel = n.name.trim();
    } else {
      derivedLabel = id;
    }

    // Raw NetworkX nodes omit `inReport`; default to true when absent so
    // the default `reportOnly: true` filter does not hide the entire fallback graph.
    const inReport = typeof n.inReport === "boolean" ? n.inReport : true;

    nodes.push({
      id,
      label: derivedLabel,
      color: typeof n.color === "string" ? n.color : undefined,
      entityType,
      size: typeof n.size === "number" ? n.size : isRoot ? 30 : 22,
      title: typeof n.title === "string" ? n.title : undefined,
      isRoot,
      isMalicious,
      inReport,
      threatScore: rawThreatScore,
      verdict: rawVerdict,
      vendorDetections:
        typeof n.vendorDetections === "string"
          ? n.vendorDetections
          : maliciousVendors > 0
            ? `${maliciousVendors} malicious`
            : null,
    });
  }

  const rawEdgeList = Array.isArray(rawGraph.edges)
    ? rawGraph.edges
    : Array.isArray(rawGraph.links)
      ? rawGraph.links
      : [];

  const edges: NormalizedFallbackEdge[] = [];
  for (const rawEdge of rawEdgeList) {
    if (!rawEdge || typeof rawEdge !== "object") continue;
    const e = rawEdge as Record<string, unknown>;
    const source =
      typeof e.source === "object" && e.source !== null
        ? String((e.source as Record<string, unknown>).id ?? "")
        : String(e.source ?? "");
    const target =
      typeof e.target === "object" && e.target !== null
        ? String((e.target as Record<string, unknown>).id ?? "")
        : String(e.target ?? "");
    if (!source || !target) continue;

    const label = String(e.label || e.relationship || "related_to");
    edges.push({ source, target, label });
  }

  return { nodes, edges };
}

/**
 * Adapt a Graphviz DOT string for dark theme display, enforcing transparent background,
 * specified rankdir orientation, and stripping potentially malicious URL/href attributes.
 */
// Applies attribute-separator cleanup regexes only to the portions of a DOT
// string that fall outside quoted string literals, so a label like
// `label="a, b"` or `label="x]y"` is never corrupted by the cleanup.
function collapseAttributeSeparatorsOutsideQuotes(dot: string): string {
  const segments = dot.split(/("(?:[^"\\]|\\.)*")/g);
  return segments
    .map((segment, index) => {
      if (index % 2 === 1) return segment; // quoted literal, leave untouched
      return segment
        .replace(/,(?:\s*,)+/g, ",")
        .replace(/,\s*\]/g, "]")
        .replace(/\[\s*,/g, "[");
    })
    .join("");
}

export function adaptDotForDarkTheme(
  rawDot: string | null | undefined,
  ori: "LR" | "TB" | string = "LR"
): string {
  const baseDot =
    rawDot && rawDot.trim().length > 0
      ? rawDot
      : `digraph AttackFlow {\n  rankdir=${ori};\n  bgcolor="transparent";\n  node [shape=box, style="rounded,filled", fillcolor="#0f172a", color="#334155", fontcolor="#e2e8f0", fontname="monospace"];\n  "Target" [label="No DOT Graph Available"];\n}`;

  let adapted = baseDot;

  // 1. Strip any Graphviz link/target attributes (URL, href, edgeURL, headURL, tailURL,
  // labelURL, edgehref, headhref, tailhref, labelhref, target, edgetarget, headtarget,
  // tailtarget, labeltarget) with double-quoted, single-quoted, HTML-like <...>, or unquoted
  // values, while preserving double-quoted string literals (e.g., label="...") verbatim.
  adapted = adapted.replace(
    /("(?:[^"\\]|\\.)*")|\b(?:[A-Za-z]*(?:URL|href|target))\s*=\s*(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|<(?:[^<>]|<[^<>]*>)*>|[^\s,\];]+)/gi,
    (_match, quotedLiteral?: string) => (quotedLiteral ? quotedLiteral : "")
  );

  // 2. Also strip any href / xlink:href / on* attributes inside HTML-like label tags (<TABLE HREF=...>)
  adapted = adapted.replace(
    /("(?:[^"\\]|\\.)*")|(<(?:[^<>]|<[^<>]*>)*>)/g,
    (_match, quotedLiteral?: string, htmlLabel?: string) => {
      if (quotedLiteral) return quotedLiteral;
      if (!htmlLabel) return _match;
      return htmlLabel.replace(
        /\s*\b(?:href|xlink:href|url|on[a-z]+)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi,
        ""
      );
    }
  );

  adapted = collapseAttributeSeparatorsOutsideQuotes(adapted);

  // 3. Update or inject rankdir outside quoted strings
  let hasRankdirOutsideQuotes = false;
  adapted = adapted.replace(
    /("(?:[^"\\]|\\.)*")|\brankdir\s*=\s*(?:"[^"]*"|'[^']*'|[A-Za-z]+)/gi,
    (_match, quotedLiteral?: string) => {
      if (quotedLiteral) return quotedLiteral;
      hasRankdirOutsideQuotes = true;
      return `rankdir=${ori}`;
    }
  );
  if (!hasRankdirOutsideQuotes) {
    if (/digraph\s+[^{]*\{/i.test(adapted)) {
      adapted = adapted.replace(/(digraph\s+[^{]*\{)/i, `$1\n  rankdir=${ori};`);
    } else {
      adapted = `digraph G {\n  rankdir=${ori};\n${adapted}\n}`;
    }
  }

  // 4. Update or inject bgcolor="transparent" outside quoted strings
  let hasBgcolorOutsideQuotes = false;
  adapted = adapted.replace(
    /("(?:[^"\\]|\\.)*")|\bbgcolor\s*=\s*(?:"[^"]*"|'[^']*'|[^\s,\];]+)/gi,
    (_match, quotedLiteral?: string) => {
      if (quotedLiteral) return quotedLiteral;
      hasBgcolorOutsideQuotes = true;
      return 'bgcolor="transparent"';
    }
  );
  if (!hasBgcolorOutsideQuotes && /digraph\s+[^{]*\{/i.test(adapted)) {
    adapted = adapted.replace(
      /(digraph\s+[^{]*\{)/i,
      `$1\n  bgcolor="transparent";`
    );
  }

  return adapted;
}
