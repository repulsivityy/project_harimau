# Project Harimau

Cloud-Native AI Threat Hunter using LangGraph, Vertex AI (Gemini 3.0 Pro), and NetworkX.
**Status**: Live on Google Cloud Run (Phase 1).
See `docs/` for detailed documentation.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure `.env` (see `.env.example`).
3. Run CLI:
   ```bash
   python backend/cli.py investigate <IOC>
   ```
