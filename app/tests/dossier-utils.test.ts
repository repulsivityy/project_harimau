import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  adaptDotForDarkTheme,
  deriveSwimLanes,
  extractFallbackIocs,
  normalizeReportSections,
  parseDossierReport,
  parseDotToGraph,
} from "../src/lib/dossier-utils";

import type { DossierJob } from "../src/lib/dossier-types";

function loadSampleJson(filename: string): DossierJob {
  const filePath = path.resolve(process.cwd(), "tests", "fixtures", filename);
  return JSON.parse(fs.readFileSync(filePath, "utf8")) as DossierJob;
}

test("normalizeReportSections deterministically reorders and renumbers legacy or out-of-order markdown into strict 1-7 Dossier sequence", () => {
  const messyMarkdown = `## Threat Assessment Preamble

### 4. Technical Analysis
Details about binary execution.

### 1. Executive Summary
High level executive overview.

### 3. Investigation Timeline
Chronological events observed.

### 10. Appendix
Observables list.

### 2. Attack Narrative
Step by step kill chain.

### 5. Attack Flow
Diagram notes.`;

  const normalized = normalizeReportSections(messyMarkdown);
  const headings = (normalized.match(/^###\s+\d+\..*$/gm) || []).map((h) => h.trim());

  assert.equal(headings.length, 7);
  assert.match(headings[0], /^### 1\. Executive Summary/);
  assert.match(headings[1], /^### 2\. Attack Narrative/);
  assert.match(headings[2], /^### 3\. Specialist Reports/);
  assert.match(headings[3], /^### 4\. Investigation Timeline/);
  assert.match(headings[4], /^### 5\. Technical Analysis/);
  assert.match(headings[5], /^### 6\. Attack Flow/);
  assert.match(headings[6], /^### 7\. Appendix/);
});

test("clickfix_example.json produces exactly 5 active swim lane stages (ingress, execution, decoy, dropped, c2)", () => {
  const data = loadSampleJson("clickfix_example.json");
  const parsedReport = parseDossierReport(data.final_report || "", data);
  const stages = deriveSwimLanes(parsedReport.parsedDotGraph, data.ioc, data);

  assert.equal(stages.length, 5);
  assert.deepEqual(
    stages.map((s) => s.category),
    ["ingress", "execution", "decoy", "dropped", "c2"]
  );
});

test("sample_minecraft_mod.json produces exactly 4 active swim lane stages (ingress, execution, dropped, c2)", () => {
  const data = loadSampleJson("sample_minecraft_mod.json");
  const parsedReport = parseDossierReport(data.final_report || "", data);
  const stages = deriveSwimLanes(parsedReport.parsedDotGraph, data.ioc, data);

  assert.equal(stages.length, 4);
  assert.deepEqual(
    stages.map((s) => s.category),
    ["ingress", "execution", "dropped", "c2"]
  );
});

test("sample_investigation.json produces exactly 3 active swim lane stages (execution, dropped, c2)", () => {
  const data = loadSampleJson("sample_investigation.json");
  const parsedReport = parseDossierReport(data.final_report || "", data);
  const stages = deriveSwimLanes(parsedReport.parsedDotGraph, data.ioc, data);

  assert.equal(stages.length, 3);
  assert.deepEqual(
    stages.map((s) => s.category),
    ["execution", "dropped", "c2"]
  );
});

test("extractFallbackIocs extracts IOC entries when appendixIocs is empty", () => {
  const graph = parseDotToGraph(
    `digraph G {
      "evil.example.com" [label="evil.example.com\\n(C2 Domain)", color="#ef4444"];
      "198.51.100.42" [label="198.51.100.42", color="#f59e0b"];
      "evil.example.com" -> "198.51.100.42" [label="resolves_to"];
    }`,
    "evil.example.com",
    95
  );

  const iocs = extractFallbackIocs(graph);
  assert.equal(iocs.length, 2);
  assert.equal(iocs[0].value, "evil.example.com");
  assert.equal(iocs[0].confidence, "High");
});

test("normalizeReportSections and parseDossierReport never hoist unnumbered sub-headings out of their parent section", () => {
  const markdownWithSubsections = `### 1. Executive Summary
Summary text.

### 2. Attack Narrative
Narrative intro.

### Attack Flow Overview
This subsection belongs under section 2 but mentions Attack Flow.

### Initial Timeline Notes
This subsection also belongs under section 2.

### 5. Technical Analysis
Tech text.`;

  const parsed = parseDossierReport(markdownWithSubsections);
  const sec2 = parsed.sections.find((s) => s.number === 2)!;
  const sec4 = parsed.sections.find((s) => s.number === 4)!;
  const sec6 = parsed.sections.find((s) => s.number === 6)!;

  assert.match(sec2.markdownBody, /### Attack Flow Overview/);
  assert.match(sec2.markdownBody, /### Initial Timeline Notes/);
  assert.equal(sec4.markdownBody, "");
  assert.equal(sec6.markdownBody, "");
});

test("normalizeReportSections handles heading-level drift (#, ##, ####) and merges repeated canonical headings", () => {
  const markdownWithDriftAndRepeats = `# 1. Executive Summary
Overview part 1.

## 2. Attack Narrative
Initial infection vectors.

#### Mutex Creation
Mutex details under section 2.

### 2. Attack Narrative: Secondary Phase
Secondary lateral movement notes.

#### 5. Technical Analysis
Reverse engineering deep dive.

### 5. Technical Analysis
Further binary disassembly.`;

  const normalized = normalizeReportSections(markdownWithDriftAndRepeats);
  const headings = (normalized.match(/^###\s+\d+\..*$/gm) || []).map((h) => h.trim());

  assert.equal(headings.length, 7);
  assert.match(headings[0], /^### 1\. Executive Summary/);
  assert.match(headings[1], /^### 2\. Attack Narrative/);
  assert.match(headings[4], /^### 5\. Technical Analysis/);

  assert.match(normalized, /Overview part 1\./);
  assert.match(normalized, /Initial infection vectors\./);
  assert.match(normalized, /#### Mutex Creation/);
  assert.match(normalized, /Secondary lateral movement notes\./);
  assert.match(normalized, /Reverse engineering deep dive\./);
  assert.match(normalized, /Further binary disassembly\./);

  // Repeated/variant canonical headings must not be silently dropped: their
  // text survives as a "####" sub-heading ahead of their body content, and
  // (critically) without a leading section number so it can't be re-matched
  // as its own numbered heading downstream.
  assert.match(normalized, /#### Attack Narrative: Secondary Phase\nSecondary lateral movement notes\./);
  assert.match(normalized, /#### Technical Analysis\nFurther binary disassembly\./);
  assert.doesNotMatch(normalized, /#### \d+\./);

  // End-to-end through parseDossierReport's own section split: the
  // sub-heading and its body must land in the correct canonical section,
  // not get swallowed or bucketed elsewhere.
  const parsed = parseDossierReport(markdownWithDriftAndRepeats, undefined, null);
  const attackNarrative = parsed.sections.find((s) => s.number === 2)!;
  const technicalAnalysis = parsed.sections.find((s) => s.number === 5)!;
  assert.match(attackNarrative.markdownBody, /Secondary lateral movement notes\./);
  assert.match(technicalAnalysis.markdownBody, /Further binary disassembly\./);
});

test("parseDossierReport ignores non-IOC JSON blocks earlier in the report and objects without value, falling back to extractFallbackIocs", () => {
  const markdownWithEarlyJson = `### 1. Executive Summary
Executive overview.

### 3. Specialist Reports
Example payload configuration:
\`\`\`json
[
  { "setting": "debug", "enabled": true }
]
\`\`\`

\`\`\`dot
digraph G {
  "target.exe" [label="target.exe", color="#ef4444"];
  "198.51.100.1" [label="198.51.100.1", color="#ef4444"];
  "target.exe" -> "198.51.100.1" [label="c2_connect"];
}
\`\`\`

### 7. Appendix
\`\`\`json
[
  { "type": "ip", "value": "   ", "notes": "blank value should be discarded" }
]
\`\`\`
`;

  const parsed = parseDossierReport(markdownWithEarlyJson);
  assert.equal(parsed.appendixIocs.length, 2);
  assert.equal(parsed.appendixIocs[0].value, "target.exe");
  assert.equal(parsed.appendixIocs[1].value, "198.51.100.1");
});

test("parseDotToGraph sets threatScore to undefined for non-root nodes and preserves rootGtiScore for root node", () => {
  const dot = `digraph G {
    "malicious.exe" [label="malicious.exe", color="#ef4444"];
    "legit_decoy.dll" [label="legit_decoy.dll\\n(Legitimate)", style="dashed"];
    "suspicious_tool.exe" [label="suspicious_tool.exe\\n(LOLBin)", color="#f59e0b"];
    "unknown_host" [label="unknown_host"];
    "malicious.exe" -> "legit_decoy.dll";
    "malicious.exe" -> "suspicious_tool.exe";
    "malicious.exe" -> "unknown_host";
    "implicit_node" -> "malicious.exe";
  }`;

  const graph = parseDotToGraph(dot, "malicious.exe", 95);
  const rootNode = graph.nodes.find((n) => n.id === "malicious.exe");
  const decoyNode = graph.nodes.find((n) => n.id === "legit_decoy.dll");
  const suspNode = graph.nodes.find((n) => n.id === "suspicious_tool.exe");
  const unkNode = graph.nodes.find((n) => n.id === "unknown_host");
  const implicitNode = graph.nodes.find((n) => n.id === "implicit_node");

  assert.ok(rootNode);
  assert.equal(rootNode.threatScore, 95);
  assert.equal(rootNode.verdict, "MALICIOUS");

  assert.ok(decoyNode);
  assert.equal(decoyNode.threatScore, undefined);
  assert.equal(decoyNode.verdict, "BENIGN");

  assert.ok(suspNode);
  assert.equal(suspNode.threatScore, undefined);
  assert.equal(suspNode.verdict, "SUSPICIOUS");

  assert.ok(unkNode);
  assert.equal(unkNode.threatScore, undefined);
  assert.equal(unkNode.verdict, "UNKNOWN");

  assert.ok(implicitNode);
  assert.equal(implicitNode.threatScore, undefined);
  assert.equal(implicitNode.verdict, "UNKNOWN");
});

test("adaptDotForDarkTheme strips URL and href attributes to sanitize malicious javascript links", () => {
  const maliciousDot = `digraph G {
    "node1" [label="node1", URL="javascript:alert('XSS')", color="#ef4444"];
    "node2" [label="node2", href="javascript:void(0)"];
  }`;

  const adapted = adaptDotForDarkTheme(maliciousDot);
  assert.doesNotMatch(adapted, /\bURL\s*=/i);
  assert.doesNotMatch(adapted, /\bhref\s*=/i);
  assert.doesNotMatch(adapted, /,\s*,/);
  assert.match(adapted, /bgcolor="transparent"/);
  assert.match(adapted, /rankdir=LR/);
});

test("adaptDotForDarkTheme collapses dangling commas when both URL and href are stripped from the same node", () => {
  const maliciousDot = `digraph G {
    "node1" [label="node1", URL="http://evil.example", href="javascript:alert(1)", color="#ef4444"];
  }`;

  const adapted = adaptDotForDarkTheme(maliciousDot);
  assert.doesNotMatch(adapted, /\bURL\s*=/i);
  assert.doesNotMatch(adapted, /\bhref\s*=/i);
  assert.doesNotMatch(adapted, /,\s*,/);
  assert.match(adapted, /"node1"\s*\[label="node1",\s*color="#ef4444"\]/);
});

test("adaptDotForDarkTheme does not corrupt commas or brackets inside quoted label text", () => {
  const dot = `digraph G {
    "node1" [label="Alice, Bob] and Carol", URL="javascript:alert(1)", color="#ef4444"];
  }`;

  const adapted = adaptDotForDarkTheme(dot);
  assert.doesNotMatch(adapted, /\bURL\s*=/i);
  assert.match(adapted, /label="Alice, Bob\] and Carol"/);
});
