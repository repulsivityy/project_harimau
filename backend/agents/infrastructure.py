import asyncio
import os
import json
import re
from contextlib import AsyncExitStack
from typing import Optional, List, Dict, Any, Annotated, TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, BaseMessage
#from langchain_google_vertexai import ChatVertexAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from backend.utils import checkpointer_registry

from backend.graph.state import AgentState
from backend.mcp.client import mcp_manager
from backend.utils.logger import get_logger
from backend.utils.graph_cache import InvestigationCache, extract_gti_summary
from backend.utils.transparency import emit_tool_call, emit_reasoning
from backend.utils.agent_utils import (
    FINAL_ITERATION_PROMPT,
    reduce_messages,
    cap_context_window,
    push_to_rich_intel,
    build_peer_context,
    parse_indicator_string,
)
import backend.tools.webrisk as webrisk

## Global Variables
infra_iterations = 10 # number of iterations the infra agent goes through per set of investigation
unique_targets_limit = 10 # number of unique targets the infra agent investigates per set of investigation

logger = get_logger("agent_infrastructure")

class AnalyzedTargetInfra(BaseModel):
    indicator: Optional[str] = None
    type: Optional[str] = None
    verdict: Optional[str] = None
    behavior: Optional[str] = None
    notes: Optional[str] = None

class InfrastructureSpecialistOutput(BaseModel):
    verdict: str
    threat_score: Optional[float] = 0.0
    categories: Optional[List[str]] = Field(default_factory=list)
    asn_or_registrar: Optional[str] = None
    associated_campaigns: Optional[List[str]] = Field(default_factory=list)
    pivot_findings: Optional[List[str]] = Field(default_factory=list)
    related_indicators: Optional[List[str]] = Field(default_factory=list)
    analyzed_targets: Optional[List[AnalyzedTargetInfra]] = Field(default_factory=list)
    summary: Optional[str] = None

INFRA_ANALYSIS_PROMPT = """
You are an Elite Network Infrastructure Hunter.

**Role:**
You are a threat intelligence analyst specializing in pivoting across adversary infrastructure. You trace the connections between domains, IPs, and URLs to map out the attacker's footprint.
The tools you have comes from Google Threat Intelligence and Webrisk/Safebrowsing. 

**Iteration Context:**
You may be called multiple times during an investigation. Each call:
- You receive your PREVIOUS REPORT (if any) — it contains your findings so far
- You receive NEW targets to investigate — focus your tools on these
- Your output must MERGE prior and new findings into a single cohesive report
- Do NOT re-investigate entities already listed in your previous `analyzed_targets`
- DO update your verdict, summary, and pivot findings if new evidence changes the picture

**Goal:**
Analyze the provided network indicator (Domain, IP, or URL) to assess its maliciousness and find related infrastructure.
1.  **Analyze Primary Indicator:** Use the appropriate report tool (`get_domain_report`, `get_ip_address_report`, etc.) to understand the entity.
    *   **Verdict:** Is it known malicious? What are the categories?
    *   **Context:** Whois data, SSL certificates, passive DNS.
2.  **Find Related Infrastructure (Pivot):**
    *   Use `get_entities_related_to...` tools.
    *   **Hunt Strategy:** "I see a malicious domain. What IPs did it resolve to? Are those IPs hosting other malicious domains?"
    *   **Validation:** Don't just list everything. Filter for suspicious connections (e.g., communicating files that are detected, subdomains with high entropy).
3.  **Attribution:** Are there any known threat actors or campaigns associated with this infrastructure?

**Tools:**
- `get_domain_report`: Get verdict, categories, and DNS details for a domain.
- `get_ip_address_report`: Get verdict, ASN, and geo details for an IP.
- `get_url_report`: Get verdict and analysis stats for a URL.
- `get_entities_related_to_a_domain`: Pivot from a domain (e.g., to resolutions, subdomains).
- `get_entities_related_to_an_ip_address`: Pivot from an IP (e.g., to resolutions, communicating_files).
- `get_entities_related_to_an_url`: Pivot from a URL (e.g., to network_location, downloaded_files).
- `get_webrisk_report`: Check URL for Social Engineering, Malware, or Unwanted Software.

- `shodan_ip_lookup`: Look up an IP in Shodan — open ports, running services, banners, known vulns, and geolocation. Use this to enrich IPs with exposure data that GTI does not provide.
- `shodan_dns_lookup`: Resolve hostnames to IPs via Shodan DNS. Useful when pivoting from a domain to confirm its current resolution.
- `shodan_reverse_dns_lookup`: Resolve IPs to hostnames via Shodan. Use this to discover what domains are co-hosted on a suspicious IP.

**`threat_score`:** Read `gti_assessment.threat_score.value` directly from the GTI tool response and use that value as-is.

**Collaboration with Malware Agent:**
Any file hashes discovered via `communicating_files` or `downloaded_files` relationships MUST be included in `related_indicators` with the prefix `File:` (e.g., `"File: <hash>"`). The Malware Agent reads these on the next iteration to expand its analysis. Include all discovered hashes regardless of verdict — undetected files may be staging tools or living-off-the-land binaries.

**Example Output (JSON):**
{
    "verdict": "Malicious|Suspicious|Benign",
    "threat_score": 85,
    "categories": ["Phishing", "Botnet"],
    "asn_or_registrar": "NameCheap / AS12345 Cloudflare",
    "associated_campaigns": ["Campaign X", "APT29"],
    "pivot_findings": [
        "Resolved to <OBSERVED_IP> (also hosts <OBSERVED_DOMAIN>)",
        "Subdomain <OBSERVED_SUBDOMAIN> used for C2",
        "Hosted file hash <OBSERVED_HASH> (<malware family>)"
    ],
    "related_indicators": ["IP: <OBSERVED_IP>", "Domain: <OBSERVED_DOMAIN>", "File: <OBSERVED_HASH>"],
    "analyzed_targets": [
        {
            "indicator": "<OBSERVED_DOMAIN_OR_IP>",
            "type": "domain",
            "verdict": "Malicious",
            "behavior": "<observed behavior from tools>",
            "notes": "<context from triage or tool output>"
        }
    ],
    "summary": "3-5 paragraph analyst narrative. Paragraph 1: what this infrastructure is, its overall verdict, and its role in the threat. Paragraph 2: what pivoting revealed — resolutions, co-hosted domains, communicating files, and what those connections imply. Paragraph 3: hosting and registration patterns — ASN, registrar, nameservers, geolocation — and what they suggest about the operator. Paragraph 4: attribution context — links to known campaigns, threat actors, or infrastructure clusters, with confidence level. Paragraph 5 (if warranted): recommended hunting pivots and what defenders should monitor. Write in clear, professional prose — no bullet points in this field."
}

**OUTPUT INSTRUCTIONS:**
- Return ONLY a valid JSON object in the exact format above — no markdown fences, no preamble, no explanatory text.
- **JSON ESCAPING [CRITICAL]:** You must properly escape all strings. Use `\n\n` for paragraph breaks within the summary. Do NOT use literal line breaks inside strings. Escape any double quotes (`"`) inside strings as `\"`. Failure to escape strings will break the JSON parser.
- **GROUND YOUR ANALYSIS.** Every verdict, indicator, and claim must come strictly from the triage context or your tool outputs. Do NOT invent IOCs or infer beyond observed evidence.
- **DO NOT HALLUCINATE IOCs.** The example values above are structural placeholders — never use them. Only include indicators explicitly returned by your tools. If none were found, use `[]`.
- **IF TOOLS FAIL:** Still return JSON. Use `"Unknown"`, `[]`, or `"N/A"` for unpopulated fields; note errors in the `summary` field.

**Example when tools fail:**
{
    "verdict": "Unknown",
    "threat_score": 0,
    "categories": [],
    "asn_or_registrar": "Unknown",
    "associated_campaigns": [],
    "pivot_findings": ["Unable to fetch subdomains due to tool error"],
    "related_indicators": [],
    "analyzed_targets": [],
    "summary": "Analysis incomplete due to tool errors. Based on available data: [describe what you know]"
}
"""

def generate_infrastructure_markdown_report(result: dict, ioc: str) -> str:
    """
    Generates a detailed markdown report for Infrastructure Analysis.
    """
    try:
        md = "## Infrastructure Specialist Analysis\n\n"
        
        # Executive Summary
        md += "### Executive Summary\n"
        md += f"{result.get('summary', 'No summary provided.')}\n\n"
        
        # Threat Categories
        categories = result.get("categories", [])
        if categories:
            md += f"**Threat Categories:** {', '.join(categories)}\n\n"
        
        # 1. Pivot Findings
        pivots = result.get("pivot_findings", [])
        if pivots:
            md += "### 🔍 Pivot Findings\n"
            for p in pivots:
                md += f"*   {p}\n"
            md += "\n"
            
        # 2. Campaigns/Actors
        campaigns = result.get("associated_campaigns", [])
        if campaigns:
            md += "### 🏴 Associated Campaigns\n"
            for c in campaigns:
                md += f"*   {c}\n"
            md += "\n"
            
        # 3. Related Indicators (Table)
        indicators = result.get("related_indicators", [])
        if indicators:
            md += "### 🌐 Related Infrastructure\n"
            for ind in indicators:
                 md += f"*   `{ind}`\n"
            md += "\n"
            
        # 4. Appendix: Investigated Targets
        targets = result.get("analyzed_targets", [])
        if targets:
            md += "### 📎 Appendix: Indicators Investigated\n"
            md += "| Indicator Analyzed | Type | Behavior | Verdict | Notes |\n"
            md += "|---|---|---|---|---|\n"
            for t in targets:
                if isinstance(t, dict):
                    md += f"| `{t.get('indicator', 'N/A')}` | {t.get('type', 'N/A')} | {t.get('behavior', 'N/A')} | **{t.get('verdict', 'N/A')}** | {t.get('notes', 'N/A')} |\n"
            md += "\n"
        
        return md
    except Exception as e:
        return f"Error generating infrastructure report: {str(e)}"

class InfraSubgraphState(TypedDict):
    ioc: str
    subtasks: List[Dict[str, Any]]
    specialist_results: Dict[str, Any]
    investigation_graph: Optional[Any]
    metadata: Dict[str, Any]
    job_id: Optional[str]
    iteration: int
    
    # Subgraph local variables
    messages: Annotated[List[BaseMessage], reduce_messages]
    unique_targets: List[Dict[str, Any]]
    loop_step: int
    max_iterations: int
    final_result: Optional[Dict[str, Any]]

# Lazily cached LLM instance — stateless, safe to reuse across invocations.
_infra_base_llm: Optional[ChatGoogleGenerativeAI] = None

async def infrastructure_node(state: AgentState):
    """
    Infrastructure Specialist Agent (Iterative & Graph-Aware Sub-graph wrapper).
    """
    ioc = state["ioc"]
    logger.info("infra_agent_start", ioc=ioc)
    
    try:
        # Initialize cache from state
        cache = InvestigationCache(state.get("investigation_graph"))
        cache_stats_before = cache.get_stats()
        logger.info("infra_cache_loaded", stats=cache_stats_before)
        
        # Retrieve Triage Context
        triage_context = state.get("metadata", {}).get("rich_intel", {}).get("triage_analysis", {})
        triage_summary = triage_context.get("executive_summary", "No triage summary available.")
        key_findings = triage_context.get("key_findings", [])
        logger.info("infra_triage_context_loaded", 
                   has_summary=bool(triage_summary), 
                   findings_count=len(key_findings))
        
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")

        # Setup Tools & Sub-graph dynamic definitions inside MCP session context
        async with AsyncExitStack() as stack:
            session = await stack.enter_async_context(mcp_manager.get_session("gti"))
            shodan_session = await stack.enter_async_context(mcp_manager.get_session("shodan"))
            
            # Domain Tools
            @tool
            async def get_domain_report(domain: str):
                """Get threat report for a domain."""
                job_id = state.get("job_id")
                if job_id:
                    await emit_tool_call(job_id, "infrastructure", "get_domain_report", {"domain": domain})
                try: 
                    res = await session.call_tool("get_domain_report", arguments={"domain": domain})
                    return res.content[0].text if res.content else "{}"
                except Exception as e: return str(e)

            @tool
            async def get_entities_related_to_a_domain(domain: str, relationship: str):
                """Get entities related to a domain. Relationships: resolutions, subdomains, communicating_files."""
                job_id = state.get("job_id")
                if job_id:
                    await emit_tool_call(job_id, "infrastructure", "get_entities_related_to_a_domain", {"domain": domain, "relationship": relationship})
                try:
                    res = await session.call_tool("get_entities_related_to_a_domain", arguments={"domain": domain, "relationship_name": relationship, "descriptors_only": True})
                    if not res.content: return "[]"
                    parsed = json.loads(res.content[0].text)
                    if "error" in parsed: return res.content[0].text
                    
                    found = []
                    for item in parsed.get("data", []):
                        eid = item.get("id")
                        etype = item.get("type", "unknown")
                        if not eid: continue
                        h_type = "ip_address" if etype == "ip_address" else "file" if etype == "file" else "domain"
                        
                        attrs = {"infra_context": f"domain_{relationship}"}
                        attrs.update(extract_gti_summary(item))
                        
                        cache.add_entity(eid, h_type, attrs)
                        cache.add_relationship(domain, eid, relationship, {"source": "infrastructure_analysis_tool"})
                        found.append(eid)
                    return json.dumps(found)
                except Exception as e: return str(e)
                
            # IP Tools
            @tool
            async def get_ip_address_report(ip_address: str):
                """Get threat report for an IP address."""
                job_id = state.get("job_id")
                if job_id:
                    await emit_tool_call(job_id, "infrastructure", "get_ip_address_report", {"ip_address": ip_address})
                try: 
                    res = await session.call_tool("get_ip_address_report", arguments={"ip_address": ip_address})
                    return res.content[0].text if res.content else "{}"
                except Exception as e: return str(e)

            @tool
            async def get_entities_related_to_an_ip_address(ip_address: str, relationship: str):
                """Get entities related to an IP. Relationships: resolutions, communicating_files, referrer_files."""
                job_id = state.get("job_id")
                if job_id:
                    await emit_tool_call(job_id, "infrastructure", "get_entities_related_to_an_ip_address", {"ip_address": ip_address, "relationship": relationship})
                try:
                    res = await session.call_tool("get_entities_related_to_an_ip_address", arguments={"ip_address": ip_address, "relationship_name": relationship, "descriptors_only": True})
                    if not res.content: return "[]"
                    parsed = json.loads(res.content[0].text)
                    if "error" in parsed: return res.content[0].text
                    
                    found = []
                    for item in parsed.get("data", []):
                        eid = item.get("id")
                        etype = item.get("type", "unknown")
                        if not eid: continue
                        h_type = "domain" if etype == "domain" else "file" if etype == "file" else "ip_address"
                        
                        attrs = {"infra_context": f"ip_{relationship}"}
                        attrs.update(extract_gti_summary(item))
                        
                        cache.add_entity(eid, h_type, attrs)
                        cache.add_relationship(ip_address, eid, relationship, {"source": "infrastructure_analysis_tool"})
                        found.append(eid)
                    return json.dumps(found)
                except Exception as e: return str(e)

            # URL Tools
            @tool
            async def get_url_report(url: str):
                """Get threat report for a URL."""
                job_id = state.get("job_id")
                if job_id:
                    await emit_tool_call(job_id, "infrastructure", "get_url_report", {"url": url})
                try: 
                    res = await session.call_tool("get_url_report", arguments={"url": url})
                    return res.content[0].text if res.content else "{}"
                except Exception as e: return str(e)

            @tool
            async def get_entities_related_to_an_url(url: str, relationship: str):
                """Get entities related to a URL. Relationships: downloaded_files, network_location."""
                job_id = state.get("job_id")
                if job_id:
                    await emit_tool_call(job_id, "infrastructure", "get_entities_related_to_an_url", {"url": url, "relationship": relationship})
                try:
                    res = await session.call_tool("get_entities_related_to_an_url", arguments={"url": url, "relationship_name": relationship, "descriptors_only": True})
                    if not res.content: return "[]"
                    parsed = json.loads(res.content[0].text)
                    if "error" in parsed: return res.content[0].text
                    
                    found = []
                    for item in parsed.get("data", []):
                        eid = item.get("id")
                        etype = item.get("type", "unknown")
                        if not eid: continue
                        h_type = "ip_address" if etype == "ip_address" else "file" if etype == "file" else "domain" if etype == "domain" else "url"
                        
                        attrs = {"infra_context": f"url_{relationship}"}
                        attrs.update(extract_gti_summary(item))
                        
                        cache.add_entity(eid, h_type, attrs)
                        cache.add_relationship(url, eid, relationship, {"source": "infrastructure_analysis_tool"})
                        found.append(eid)
                    return json.dumps(found)
                except Exception as e: return str(e)

            @tool
            async def get_webrisk_report(url: str):
                """Check URL against Google Web Risk (Social Engineering/Malware)."""
                job_id = state.get("job_id")
                if job_id:
                    await emit_tool_call(job_id, "infrastructure", "get_webrisk_report", {"url": url})
                try:
                    res = await webrisk.evaluate_uri(url)
                    return json.dumps(res)
                except Exception as e: return str(e)

            @tool
            async def shodan_ip_lookup(ip: str):
                """Look up an IP in Shodan. Returns open ports, services, banners, known vulnerabilities, and geolocation."""
                job_id = state.get("job_id")
                if job_id:
                    await emit_tool_call(job_id, "infrastructure", "shodan_ip_lookup", {"ip": ip})
                try:
                    res = await shodan_session.call_tool("ip_lookup", arguments={"ip": ip})
                    return res.content[0].text if res.content else "{}"
                except Exception as e: return str(e)

            @tool
            async def shodan_dns_lookup(hostnames: str):
                """Resolve one or more hostnames to IPs via Shodan DNS. Accepts comma-separated hostnames."""
                job_id = state.get("job_id")
                if job_id:
                    await emit_tool_call(job_id, "infrastructure", "shodan_dns_lookup", {"hostnames": hostnames})
                try:
                    res = await shodan_session.call_tool("dns_lookup", arguments={"hostnames": hostnames})
                    return res.content[0].text if res.content else "{}"
                except Exception as e: return str(e)

            @tool
            async def shodan_reverse_dns_lookup(ips: str):
                """Resolve one or more IPs to hostnames via Shodan. Accepts comma-separated IPs."""
                job_id = state.get("job_id")
                if job_id:
                    await emit_tool_call(job_id, "infrastructure", "shodan_reverse_dns_lookup", {"ips": ips})
                try:
                    res = await shodan_session.call_tool("reverse_dns_lookup", arguments={"ips": ips})
                    return res.content[0].text if res.content else "{}"
                except Exception as e: return str(e)

            tools = [
                get_domain_report, get_entities_related_to_a_domain,
                get_ip_address_report, get_entities_related_to_an_ip_address,
                get_url_report, get_entities_related_to_an_url,
                get_webrisk_report,
                shodan_ip_lookup, shodan_dns_lookup, shodan_reverse_dns_lookup,
            ]

            global _infra_base_llm
            if _infra_base_llm is None:
                _infra_base_llm = ChatGoogleGenerativeAI(
                    model="gemini-3.1-pro-preview",
                    temperature=0.0,
                    project=project_id,
                    location="global",
                    thinking_level="medium",
                    include_thoughts=True
                )
            base_llm = _infra_base_llm
            llm = base_llm.bind_tools(tools)

            # Node 1: init_node
            def init_node(sub_state: InfraSubgraphState):
                if sub_state.get("messages"):
                    return {}
                
                # --- Identify Targets ---
                targets = []
                
                # 1. Check Root
                is_ip = re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ioc)
                is_domain = not is_ip and "." in ioc and "http" not in ioc
                is_url = "http" in ioc
                
                if is_ip or is_domain or is_url:
                    root_entity = cache.get_entity_full(ioc)
                    if root_entity and "infrastructure" in root_entity.get("analyzed_by", []):
                        logger.info("infra_root_already_investigated", value=ioc)
                    else:
                        targets.append({"type": "root", "value": ioc})
                    
                # 2. Check Subtasks (with Regex Fallback)
                for task in sub_state.get("subtasks", []):
                    if task.get("agent") in ["infrastructure_specialist", "infrastructure"]:
                        val = task.get("entity_id")
                        task_text = task.get("task", "")
                        task_context = task.get("context", "")

                        if val:
                            targets.append({
                                "type": "subtask", 
                                "value": val,
                                "context": task.get("context")
                            })
                        
                        # ALSO scan the task description for additional entities (grouped tasks)
                        ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", task_text)
                        for ip in ips:
                            targets.append({"type": "subtask_extraction", "value": ip, "context": task_context})
                        
                        urls = re.findall(r"https?://[^\s]+", task_text)
                        for url in urls:
                            targets.append({"type": "subtask_extraction", "value": url, "context": task_context})
                        
                        domains = re.findall(r"\b([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b", task_text)
                        ignored_exts = ["exe", "dll", "pdf", "txt", "json", "docx", "png", "jpg", "zip", "rar"]
                        for d in domains:
                            parts = d.split(".")
                            if len(parts) >= 2 and parts[-1].lower() not in ignored_exts and d not in ["e.g", "i.e", "vs."]:
                                 targets.append({"type": "subtask_extraction", "value": d, "context": task_context})

                # 3. SAFETY NET: Scan Triage Key Findings if we have capacity
                if len(targets) < 5:
                    combined_text = triage_summary + " " + " ".join(key_findings)
                    logger.info("infra_safety_net_scanning")
                    
                    ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", combined_text)
                    for ip in ips:
                        e = cache.get_entity_full(ip)
                        if not (e and "infrastructure" in e.get("analyzed_by", [])):
                            targets.append({"type": "safety_net", "value": ip, "context": "Found in Triage Summary"})

                    domains = re.findall(r"\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,})\b", combined_text)
                    for d in domains:
                        if d.lower() not in [ioc.lower(), "google.com", "virustotal.com", "example.com"]:
                            e = cache.get_entity_full(d)
                            if not (e and "infrastructure" in e.get("analyzed_by", [])):
                                targets.append({"type": "safety_net", "value": d, "context": "Found in Triage Summary"})

                # Deduplicate
                unique_targets = []
                seen = set()
                
                def clean_val(v):
                    return v.strip(".,;:").lower()

                for t in targets:
                    raw_val = t["value"]
                    if not raw_val: continue
                    clean = clean_val(raw_val)
                    if clean not in seen:
                        unique_targets.append(t)
                        seen.add(clean)
                        
                unique_targets = unique_targets[:unique_targets_limit]
                logger.info("infra_targets_identified", count=len(unique_targets), targets=[t["value"] for t in unique_targets])
                
                if not unique_targets:
                    logger.warning("infra_no_targets_found")
                    return {"unique_targets": [], "messages": []}

                # Format Triage Context for LLM
                triage_context_str = f"""**TRIAGE SUMMARY:**
{triage_summary}

**KEY FINDINGS FROM TRIAGE:**
"""
                if key_findings:
                    for finding in key_findings:
                        triage_context_str += f"- {finding}\n"
                else:
                    triage_context_str += "- (No specific findings listed)\n"
                
                # Check subtasks for specific instructions
                context = ""
                for task in sub_state.get("subtasks", []):
                    if task.get("agent") in ["infrastructure_specialist", "infrastructure"]:
                        context += f"- Task: {task.get('task')}\n"
                        context += f"- Context: {task.get('context')}\n"
                
                peer_context = build_peer_context(
                    state, sub_state.get("iteration", 0), "infrastructure", "malware",
                    extra_fields=[
                        ("Related Indicators", "related_indicators"),
                        ("Pivot Findings", "pivot_findings"),
                    ],
                    count_key="related_indicators",
                    logger=logger,
                )

                messages = [
                    SystemMessage(content=INFRA_ANALYSIS_PROMPT),
                    HumanMessage(content=f"""
{triage_context_str}

**YOUR PREVIOUS REPORT:**
{sub_state.get("specialist_results", {}).get("infrastructure", {}).get("markdown_report", "No previous report exists. This is your first iteration.")}
{peer_context}

**YOUR ASSIGNMENT:**
You have been tasked to investigate these new uninvestigated nodes based on the triage context above:
{json.dumps(unique_targets, indent=2)}

**SPECIFIC INSTRUCTIONS:**
{context if context else "Perform comprehensive infrastructure analysis on the new targets."}

**CRITICAL REPORTING INSTRUCTION:**
Incorporate all relevant findings from your PREVIOUS REPORT into the JSON fields below. Your output must be a single valid JSON object that merges prior and new intelligence into one cohesive picture.
                    """)
                ]
                
                return {
                    "unique_targets": unique_targets,
                    "messages": messages,
                    "loop_step": 0
                }

            # Node 2: agent_node
            async def agent_node(sub_state: InfraSubgraphState):
                messages = list(sub_state["messages"])
                loop_step = sub_state["loop_step"]
                max_iterations = sub_state["max_iterations"]
                
                if loop_step == max_iterations - 1:
                    logger.info("infra_agent_final_iteration", loop_step=loop_step)
                    messages.append(HumanMessage(content=FINAL_ITERATION_PROMPT))
                
                logger.info("infra_agent_iteration", iteration=loop_step, max_iterations=max_iterations)
                response = await llm.ainvoke(messages)
                
                new_messages = []
                if loop_step == max_iterations - 1:
                    new_messages.append(HumanMessage(content=FINAL_ITERATION_PROMPT))
                new_messages.append(response)
                
                return {
                    "messages": new_messages,
                    "loop_step": loop_step + 1
                }

            # Node 3: post_tool_node
            async def post_tool_node(sub_state: InfraSubgraphState):
                updated_graph = cache.get_state()
                messages = sub_state["messages"]
                capped_messages = cap_context_window(messages)
                
                if len(capped_messages) < len(messages):
                    logger.info("infra_subgraph_capping_context", original=len(messages), capped=len(capped_messages))
                    # Use model_copy to avoid mutating the shared message object in place;
                    # the in-place mutation would persist on the object across invocations.
                    marker = capped_messages[0].model_copy(
                        update={"additional_kwargs": {**capped_messages[0].additional_kwargs, "overwrite_history": True}}
                    )
                    return {
                        "messages": [marker] + list(capped_messages[1:]),
                        "investigation_graph": updated_graph
                    }
                
                return {
                    "investigation_graph": updated_graph
                }

            # Node 4: final_output_node
            async def final_output_node(sub_state: InfraSubgraphState):
                structured_llm = base_llm.with_structured_output(InfrastructureSpecialistOutput)
                response_obj = await structured_llm.ainvoke(sub_state["messages"])
                result = response_obj.model_dump()
                
                # --- Code-enforced accumulation ---
                prev = sub_state["specialist_results"].get("infrastructure") or {}
                if prev:
                    prev_targets = prev.get("analyzed_targets") or []
                    result_targets = result.get("analyzed_targets") or []

                    prev_with_ind = [t for t in prev_targets if isinstance(t, dict) and t.get("indicator")]
                    prev_no_ind = [t for t in prev_targets if isinstance(t, dict) and not t.get("indicator")]

                    new_with_ind = [t for t in result_targets if isinstance(t, dict) and t.get("indicator")]
                    new_no_ind = [t for t in result_targets if isinstance(t, dict) and not t.get("indicator")]

                    prev_by_ind = {t["indicator"]: t for t in prev_with_ind}
                    new_by_ind  = {t["indicator"]: t for t in new_with_ind}
                    
                    merged_with_ind = list({**prev_by_ind, **new_by_ind}.values())
                    result["analyzed_targets"] = merged_with_ind + prev_no_ind + new_no_ind

                    for field in ["pivot_findings", "related_indicators", "associated_campaigns", "categories"]:
                        seen, merged = set(), []
                        prev_list = prev.get(field) or []
                        result_list = result.get(field) or []
                        for v in prev_list + result_list:
                            if v not in seen:
                                seen.add(v)
                                merged.append(v)
                        result[field] = merged
                
                # Generate Markdown report
                result["markdown_report"] = generate_infrastructure_markdown_report(result, ioc)
                
                # Emit reasoning
                job_id = sub_state.get("job_id")
                if job_id:
                    final_text = json.dumps(result, indent=2)
                    await emit_reasoning(job_id, "infrastructure", final_text)
                    
                return {
                    "final_result": result
                }

            # Routers
            def route_after_init(sub_state: InfraSubgraphState):
                if not sub_state.get("unique_targets"):
                    return "end"
                return "agent"

            def route_after_agent(sub_state: InfraSubgraphState):
                messages = sub_state["messages"]
                last_message = messages[-1]
                loop_step = sub_state["loop_step"]
                max_iterations = sub_state["max_iterations"]
                
                if last_message.tool_calls and loop_step < max_iterations:
                    return "tools"
                else:
                    return "final"

            # Construct Sub-graph
            builder = StateGraph(InfraSubgraphState)
            builder.add_node("init", init_node)
            builder.add_node("agent", agent_node)
            builder.add_node("tools", ToolNode(tools))
            builder.add_node("post_tool", post_tool_node)
            builder.add_node("final", final_output_node)
            
            builder.add_edge(START, "init")
            builder.add_conditional_edges(
                "init",
                route_after_init,
                {
                    "agent": "agent",
                    "end": END
                }
            )
            builder.add_conditional_edges(
                "agent",
                route_after_agent,
                {
                    "tools": "tools",
                    "final": "final"
                }
            )
            builder.add_edge("tools", "post_tool")
            builder.add_edge("post_tool", "agent")
            builder.add_edge("final", END)
            
            # Compile Sub-graph
            subgraph = builder.compile(checkpointer=checkpointer_registry.checkpointer)
            
            subgraph_config = {
                "configurable": {
                    "thread_id": f"{state.get('job_id')}_infra_{state.get('iteration', 0)}",
                }
            }
            
            # Check for resumption
            current_sub_state = await subgraph.aget_state(subgraph_config)
            # Only resume if the graph was interrupted mid-run (next is non-empty).
            # A completed graph has next=() — treating it as resumable would re-use
            # stale state from a prior iteration instead of starting fresh.
            is_resuming = bool(current_sub_state and current_sub_state.values and current_sub_state.next)
            
            if is_resuming:
                logger.info("infra_subgraph_resuming")
                saved_graph = current_sub_state.values.get("investigation_graph")
                temp_cache = InvestigationCache(saved_graph or state.get("investigation_graph"))
                cache.graph = temp_cache.graph
                subgraph_input = None
            else:
                # Inputs to subgraph
                subgraph_input = {
                    "ioc": state.get("ioc"),
                    "subtasks": state.get("subtasks", []),
                    "specialist_results": state.get("specialist_results", {}),
                    "investigation_graph": state.get("investigation_graph"),
                    "metadata": state.get("metadata", {}),
                    "job_id": state.get("job_id"),
                    "iteration": state.get("iteration", 0),
                    "messages": [],
                    "unique_targets": [],
                    "loop_step": 0,
                    "max_iterations": infra_iterations,
                    "final_result": None
                }
            
            # Execute sub-graph
            subgraph_output = await subgraph.ainvoke(subgraph_input, config=subgraph_config)
            
            final_result = subgraph_output.get("final_result")
            if final_result:
                if "specialist_results" not in state:
                    state["specialist_results"] = {}
                state["specialist_results"]["infrastructure"] = final_result
                
                # Sync cache/investigation graph
                state["investigation_graph"] = subgraph_output.get("investigation_graph")
                
                # Sync to metadata/rich_intel
                if "metadata" not in state: state["metadata"] = {}
                if "rich_intel" not in state["metadata"]: state["metadata"]["rich_intel"] = {}
                if "relationships" not in state["metadata"]["rich_intel"]: state["metadata"]["rich_intel"]["relationships"] = {}
                
                relationships_data = state["metadata"]["rich_intel"]["relationships"]
                
                # Sync related indicators from infrastructure analysis
                final_targets = subgraph_output.get("unique_targets") or []
                primary_target = final_targets[0]["value"] if final_targets else ioc
                for indicator in final_result.get("related_indicators", []):
                    try:
                        entity_type, ind_value = parse_indicator_string(indicator)
                        if entity_type:
                            push_to_rich_intel(relationships_data, "related_infrastructure", entity_type, ind_value, primary_target, {"infra_context": "related_indicator"})
                        else:
                            logger.warning("infra_indicator_unmatched", indicator=str(indicator)[:50])
                    except Exception as e:
                        logger.warning("infra_indicator_parse_failed", indicator=str(indicator)[:50], error=str(e))
                
                # Mark targets as investigated
                cache = InvestigationCache(state["investigation_graph"])
                for target_info in final_targets:
                    cache.mark_as_investigated(target_info["value"], "infrastructure")
                    logger.info("infra_marked_investigated", entity=target_info["value"])
                
                state["investigation_graph"] = cache.get_state()
                cache_stats_after = cache.get_stats()
                logger.info("infra_graph_updated", 
                           before=cache_stats_before, 
                           after=cache_stats_after)
                
                logger.info("infra_agent_success", verdict=final_result.get("verdict"))
            else:
                # Subgraph yielded no final result (no targets identified)
                pass

    except Exception as e:
        logger.error("infra_node_fatal_error", error=str(e))
        import traceback
        tb = traceback.format_exc()
        if "specialist_results" not in state: state["specialist_results"] = {}
        state["specialist_results"]["infrastructure"] = {
            "verdict": "System Error",
            "summary": f"Fatal error in Infrastructure Specialist: {str(e)}",
            "markdown_report": f"## System Error\n\nThe Infrastructure Specialist encountered a fatal error.\n\n### Error Details\n```\n{str(e)}\n```\n\n### Traceback\n```\n{tb}\n```"
        }

    return state
