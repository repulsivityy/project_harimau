# Documentation Index

*Last updated: 2026-03-21*

Welcome to the Project Harimau documentation. This index helps you navigate the technical documentation for our AI-powered threat intelligence analysis platform.

## Quick Links

| Document | Purpose | Audience |
|----------|---------|----------|
| [PRD.md](./PRD.md) | Product requirements and roadmap | Product, Management |
| [architecture.md](./architecture.md) | System design and data flow | Engineers, Architects |
| [agent_implementation.md](./agent_implementation.md) | Agent coding patterns and examples | Developers |
| [agent_debugging_guide.md](./agent_debugging_guide.md) | Troubleshooting and fixes | DevOps, On-call Engineers |
| [implementation_plan.md](./implementation_plan.md) | Feature development plan | Development Team |
| [CHANGELOG.md](./CHANGELOG.md) | Version history and releases | All stakeholders |
| [dependency_graph.md](./dependency_graph.md) | Codebase architecture and module dependency map | Developers, Architects |
| [FRAMEWORK.md](./FRAMEWORK.md) | Standards for maintaining the implementation plan | Developers |
| [roadmap_rethinking_attack_chain.md](./roadmap_rethinking_attack_chain.md) | Architectural roadmap for open agent context & synthetic scoring | Architects, Researchers |
| [reference_report/etherrat_tuktuk_yardstick.md](./reference_report/etherrat_tuktuk_yardstick.md) | Canonical sample threat intelligence report | Analysts, Stakeholders |

---

## Documentation by Scenario

### 🛠️ "I'm debugging a production issue"
1. Start with [agent_debugging_guide.md](./agent_debugging_guide.md)
2. Check [CHANGELOG.md](./CHANGELOG.md) for recent changes
3. Reference [agent_implementation.md](./agent_implementation.md) for expected behavior

### 📝 "I'm implementing a new feature"
1. Review [PRD.md](./PRD.md) for requirements
2. Consult [architecture.md](./architecture.md) for design patterns
3. Follow templates in [agent_implementation.md](./agent_implementation.md)

### 🧭 "I'm onboarding to the project"
1. Read [PRD.md](./PRD.md) - Understand what and why
2. Study [architecture.md](./architecture.md) - Understand how
3. Skim [agent_implementation.md](./agent_implementation.md) - See code patterns
4. Inspect [dependency_graph.md](./dependency_graph.md) - Understand module relationships

### 🚀 "I'm deploying changes"
1. Check deployment checklist in [agent_debugging_guide.md](./agent_debugging_guide.md)
2. Update [CHANGELOG.md](./CHANGELOG.md) with your changes
3. Verify against patterns in [agent_implementation.md](./agent_implementation.md)

---

## Recent Updates (2026-08-03)

### Core Architectural Enhancements
- ✨ **Deterministic Graphviz Skeleton**: Integrated `dot_builder.py` directly from NetworkX cache with structural validation to prevent diagram hallucinations.
- ✨ **LangGraph ToolNode Subgraphs**: Migrated specialist agents to native `ToolNode` subgraphs with strict Pydantic `with_structured_output()`.
- ✨ **Tool Containment & SSE Robustness**: Added `@tool_timeout(20.0)` guardrails and guarded SSE broadcast with monotonic progress clamping.
- ✨ **Next.js 15+ App Router Dashboard**: Full interactive tactical UI with D3 Graphviz, ReactFlow knowledge graph, and real-time SSE streaming.
- ✨ **Pinned Dependency Matrix**: Pinned all backend dependencies in `requirements.txt` to prevent breaking upstream releases.

---

## Document Summaries

### PRD.md
Product Requirements Document covering:
- Vision and objectives
- User personas and workflows
- Feature specifications
- Success metrics
- Optimization roadmap

### architecture.md
Technical architecture including:
- High-level system design
- Component breakdown (Next.js Frontend, FastAPI Backend, LangGraph)
- Data layer (NetworkX cache, Cloud SQL persistence, AsyncPostgresSaver checkpointer)
- Token optimization and dual-layer data model
- Complete API specifications

### agent_implementation.md
Implementation reference with:
- Specialist agent structure pattern (ToolNode subgraphs)
- Structured output via Pydantic schemas
- MCP tool integration and uniform error envelopes
- Error handling strategies and tool timeout guards
- Shared agent utilities (`agent_utils.py`)

### agent_debugging_guide.md
Debugging handbook covering:
- Common issues and solutions
- JSON parsing and structured output handling
- MCP validation and parameter alignment
- Missing reports troubleshooting
- Best practices and deployment checklists

### implementation_plan.md
Development roadmap detailing:
- Completed features across 8 architectural pillars
- In-progress work and capability milestones
- Planned enhancements and technical debt tracking

### CHANGELOG.md
Version history including:
- Release notes by version
- Bug fixes, enhancements, and breaking changes
- Deployment revision tracking

### dependency_graph.md
Module dependency map covering:
- Next.js frontend route structure and API proxy
- LangGraph orchestration, agents, and state reducers
- Embedded MCP servers and utility modules

### FRAMEWORK.md
Governance rules for maintaining the implementation plan across pillars and capability milestones.

### roadmap_rethinking_attack_chain.md
Roadmap and technical PRD proposing open agent context tagging and synthetic baseline scoring to replace static relationship strings.

---

## Contributing to Documentation

When updating docs:

1. **Keep them concise**: Remove outdated information
2. **Use examples**: Code snippets over prose
3. **Link strategically**: Cross-reference related sections
4. **Update the index**: Add new documents here
5. **Date your changes**: Include "Last updated" dates

---

## Support

For questions or issues:
- **Technical**: Check [agent_debugging_guide.md](./agent_debugging_guide.md)
- **Architecture**: See [architecture.md](./architecture.md)
- **Product**: Refer to [PRD.md](./PRD.md)
