# Documentation Index

*Last updated: 2026-02-03*

Welcome to the Project Harimau documentation. This index helps you navigate the technical documentation for our AI-powered threat intelligence analysis platform.

## Quick Links

| Document | Purpose | Audience |
|----------|---------|----------|
| [PRD.md](./PRD.md) | Product requirements and roadmap | Product, Management |
| [architecture.md](./architecture.md) | System design and data flow | Engineers, Architects |
| [agent_implementation.md](./agent_implementation.md) | Agent coding patterns and examples | Developers |
| [agent_debugging_guide.md](./agent_debugging_guide.md) | Troubleshooting and fixes | DevOps, On-call Engineers |
| [implementation_plan.md](./implementation_plan.md) | Feature development plan | Development Team |
| [../CHANGELOG.md](../CHANGELOG.md) | Version history and releases | All stakeholders |

---

## Documentation by Scenario

### 🛠️ "I'm debugging a production issue"
1. Start with [agent_debugging_guide.md](./agent_debugging_guide.md)
2. Check [CHANGELOG.md](../CHANGELOG.md) for recent changes
3. Reference [agent_implementation.md](./agent_implementation.md) for expected behavior

### 📝 "I'm implementing a new feature"
1. Review [PRD.md](./PRD.md) for requirements
2. Consult [architecture.md](./architecture.md) for design patterns
3. Follow templates in [agent_implementation.md](./agent_implementation.md)

### 🧭 "I'm onboarding to the project"
1. Read [PRD.md](./PRD.md) - Understand what and why
2. Study [architecture.md](./architecture.md) - Understand how
3. Skim [agent_implementation.md](./agent_implementation.md) - See code patterns

### 🚀 "I'm deploying changes"
1. Check deployment checklist in [agent_debugging_guide.md](./agent_debugging_guide.md)
2. Update [CHANGELOG.md](../CHANGELOG.md) with your changes
3. Verify against patterns in [agent_implementation.md](./agent_implementation.md)

---

## Recent Updates (2026-01-30)

### New Documents
- ✨ **agent_debugging_guide.md**: Comprehensive troubleshooting reference
- ✨ **agent_implementation.md**: Agent coding patterns and templates
- ✨ **CHANGELOG.md**: Version history and deployment tracking

### Updated Sections
- Enhanced error handling documentation
- Added MCP tool integration patterns
- Documented JSON parsing strategies
- Included deployment best practices

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
- Component breakdown (Frontend, Backend, LangGraph)
- Data layer and caching strategy
- Token optimization approach
- API specifications

### agent_implementation.md
Implementation reference with:
- Specialist agent structure pattern
- JSON parsing implementation
- MCP tool integration guide
- Error handling strategies
- Testing checklists

### agent_debugging_guide.md
Debugging handbook covering:
- Common issues and solutions
- JSON parsing errors
- MCP validation errors
- Missing reports troubleshooting
- Best practices and anti-patterns
- Deployment checklists

### implementation_plan.md
Development roadmap detailing:
- Completed features
- In-progress work
- Planned enhancements
- Technical debt tracking

### CHANGELOG.md
Version history including:
- Release notes by version
- Bug fixes and enhancements
- Breaking changes
- Deployment revision tracking

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
