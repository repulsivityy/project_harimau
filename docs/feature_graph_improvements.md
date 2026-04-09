# Feature: Graph Improvements

This document tracks the implementation of the network graph improvements in Project Harimau's frontend.

## 1. Physics-Based Layout Engine
- [x] Investigate and integrate a physics-based layout engine (e.g., `d3-force` or similar) with `ReactFlow`.
- [x] Nodes should repel each other and edges should act as springs, creating an organic, VirusTotal-like graph layout.
- [x] Ensure layout updates smoothly and handles initial loading properly.
- [x] Ensure all nodes are connected to to the center of the graph

## 2. Custom Node Components (Icons & Rich Data)
- [x] Create a custom React component for nodes in `ReactFlow`.
- [x] Integrate icons based on entity type (e.g., globe for domain, terminal for IP, file for hash).
- [x] Display rich data on mouse hover (e.g., risk score, subtitles).

## 3. Node Selection and Detail Panel
- [ ] Implement `onNodeClick` handler for graph nodes.
- [ ] Create a detail panel that pops up or updates to show specific LangGraph intelligence data for the clicked node.

## 4. Visual Flourishes (fitView & Recenter)
- [ ] Add `fitView` to the `<ReactFlow>` components so it auto-zooms and pans on load.
- [ ] Implement a "Recenter" button that triggers `fitView` when the graph panel is expanded or when clicked by the user.

## 5. Control Panel & Legends
- [ ] Add a small control panel overlay (e.g., using `ReactFlow`'s `<Panel>` component).
- [ ] Include a legend to explain node colors/icons.
- [ ] Implement toggles to filter nodes (e.g., "Hide Clean Nodes", "Show Only Infrastructure").

---

**Current Status:** Step 2 completed. Moving to Step 3.
