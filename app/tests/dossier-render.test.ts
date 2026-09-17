import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DossierMasthead } from "../src/components/investigation/DossierMasthead";
import { SpecialistReportsGrid } from "../src/components/investigation/SpecialistReportsGrid";
import { DossierCompanionRail } from "../src/components/investigation/DossierCompanionRail";
import { AttackFlowSection } from "../src/components/investigation/AttackFlowSection";
import { TacticalSwimLanes } from "../src/components/investigation/TacticalSwimLanes";
import { DecoyInsightBanner } from "../src/components/investigation/DecoyInsightBanner";
import { AppendixIocTable } from "../src/components/investigation/AppendixIocTable";
import { deriveSwimLanes, parseDossierReport } from "../src/lib/dossier-utils";
import type { DossierJob } from "../src/lib/dossier-types";

function loadSampleJob(filename: string): DossierJob {
  const samplePath = path.resolve(process.cwd(), "tests", "fixtures", filename);
  const raw = fs.readFileSync(samplePath, "utf8");
  return JSON.parse(raw) as DossierJob;
}

test("DossierMasthead renders GTI score, VT Detections card, and GTI Threat Assessment callout", () => {
  const job = loadSampleJob("clickfix_example.json");
  const html = renderToStaticMarkup(
    React.createElement(DossierMasthead, { job, graphEntityCount: 14 })
  );

  assert.match(html, /id="bento-gti-score"/);
  assert.match(html, /id="bento-vt-detections"/);
  assert.match(html, /14 Nodes/);
  if (job.rich_intel?.gti_description || job.rich_intel?.triage_summary) {
    assert.match(html, /GTI Threat Assessment &amp; Triage Context/);
  }
});

test("TacticalSwimLanes renders --num-stages CSS custom property and all active stage columns", () => {
  const job = loadSampleJob("clickfix_example.json");
  const parsed = parseDossierReport(job.final_report || "", job);
  const stages = deriveSwimLanes(parsed.parsedDotGraph, job.ioc, job);

  const html = renderToStaticMarkup(
    React.createElement(TacticalSwimLanes, {
      activeStages: stages,
      onJumpToNode: () => {},
      onCopyIoc: () => {},
    })
  );

  assert.match(html, /--num-stages:5/);
  assert.match(html, /Ingress &amp; Delivery Vector/);
  assert.match(html, /Execution &amp; Tool Transfer/);
  assert.match(html, /Decoy &amp; Dual-Use Infra/);
  assert.match(html, /Unpacked \/ Dropped Files/);
  assert.match(html, /C2 Callbacks &amp; Staging/);
});

test("DecoyInsightBanner renders T1036 Evasion banner when decoyCount > 0 and nothing when 0", () => {
  const htmlPositive = renderToStaticMarkup(
    React.createElement(DecoyInsightBanner, { decoyCount: 2 })
  );
  assert.match(htmlPositive, /T1036/);
  assert.match(htmlPositive, /2 Decoy Nodes/);

  const htmlZero = renderToStaticMarkup(
    React.createElement(DecoyInsightBanner, { decoyCount: 0 })
  );
  assert.equal(htmlZero, "");
});

test("Full 7-section Dossier render produces zero duplicate section-1..7 DOM IDs", () => {
  const job = loadSampleJob("clickfix_example.json");
  const parsed = parseDossierReport(job.final_report || "", job);
  const stages = deriveSwimLanes(parsed.parsedDotGraph, job.ioc, job);

  const fullTree = React.createElement(
    "div",
    { className: "dossier-surface" },
    React.createElement(DossierMasthead, { job, graphEntityCount: 14 }),
    parsed.sections.map((sec) =>
      React.createElement(
        "section",
        { key: sec.id, id: sec.id },
        React.createElement("h3", null, sec.title),
        sec.number === 3
          ? React.createElement(SpecialistReportsGrid, {
              job,
              onJumpToNode: () => {},
              onCopyIoc: () => {},
            })
          : null,
        sec.number === 6
          ? React.createElement(AttackFlowSection, {
              job,
              rawDotCode: parsed.rawDotCode,
              parsedGraph: parsed.parsedDotGraph,
              swimLanes: stages,
              onJumpToNode: () => {},
              onCopyIoc: () => {},
            })
          : null,
        sec.number === 7
          ? React.createElement(AppendixIocTable, {
              iocs: parsed.appendixIocs,
              onJumpToNode: () => {},
              onCopyIoc: () => {},
            })
          : null
      )
    ),
    React.createElement(DossierCompanionRail, {
      job,
      onOpenCanvasTab: () => {},
      onJumpToNode: () => {},
      onCopyIoc: () => {},
    })
  );

  const html = renderToStaticMarkup(fullTree);

  const canonicalIds = [
    "section-1-executive-summary",
    "section-2-attack-narrative",
    "section-3-specialist-reports",
    "section-4-investigation-timeline",
    "section-5-technical-analysis",
    "section-6-attack-flow-diagram",
    "section-7-appendix",
  ];

  for (const id of canonicalIds) {
    const idAttrRegex = new RegExp(`id="${id}"`, "g");
    const matches = html.match(idAttrRegex) || [];
    assert.equal(
      matches.length,
      1,
      `Expected exactly 1 occurrence of id="${id}", found ${matches.length}`
    );
  }
});
