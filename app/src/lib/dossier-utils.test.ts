import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  deriveSwimLanes,
  extractFallbackIocs,
  normalizeReportSections,
  parseDossierReport,
  parseDotToGraph,
} from "./dossier-utils";

import type { DossierJob } from "./dossier-types";

function loadSampleJson(filename: string): DossierJob {
  const filePath = path.resolve(process.cwd(), "..", "prototype", "data", filename);
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
