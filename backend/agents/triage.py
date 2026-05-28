import os
import json
import re
import asyncio

from langchain_core.messages import SystemMessage, HumanMessage
#from langchain_google_vertexai import ChatVertexAI
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.graph.state import AgentState
from backend.utils.logger import get_logger
import backend.tools.gti as gti
import backend.tools.webrisk as webrisk
from backend.utils.graph_cache import InvestigationCache
from backend.utils.transparency import emit_tool_call, emit_reasoning

logger = get_logger("agent_triage")

# Graph growth control
MAX_ENTITIES_PER_RELATIONSHIP = 10  # Max entities per relationship sent to LLM
MAX_TOTAL_ENTITIES = 150  # Hard cap (not yet enforced — tracked for future use)

# Signal filter thresholds for LLM context (NetworkX graph is always fully populated)
SIGNAL_MALICIOUS_VENDORS = 3   # Include if malicious vendor count is >= this value

# Relationship types whose entities are attribution/context objects (campaigns, actors,
# malware families) that do NOT have gti_assessment or last_analysis_stats.
# These are always passed through to the LLM without signal filtering.
UNFILTERED_RELATIONSHIPS = {
    "associations",
    "malware_families",
    "attack_techniques",
    "campaigns",
    "related_threat_actors",
}

# Define priority relationships for each IOC type
# Based on alpha version patterns + analytical depth requirements
PRIORITY_RELATIONSHIPS = {
    "File": [
        # Core attribution (critical for threat context)
        "associations",           # Campaigns/Threat Actors
        "malware_families",       # Malware classification
        "attack_techniques",      # MITRE ATT&CK techniques
        
        # C2 Infrastructure (critical for pivot)
        "contacted_domains",      # C2 domains
        "contacted_ips",          # C2 IPs
        "contacted_urls",       # URLs contacted (covered by domains/IPs)
        
        # Malware behavior & propagation (analytical depth)
        "dropped_files",          # Files created during execution
        "embedded_domains",       # Domains embedded in file
        "embedded_ips",           # IPs embedded in file
        "execution_parents",      # Parent processes
        "itw_domains",            # In-the-wild domains
        "itw_ips",                # In-the-wild IPs
        
        # Commented out for token optimization (re-enable if needed)
        # "bundled_files",        # Files bundled together (low priority)
        # "embedded_urls",        # Embedded URLs (covered by domains/IPs)
        # "email_attachments",    # Email-related relationships
        # "email_parents",        # Email-related relationships
        # "itw_urls",             # In-the-wild URLs (covered by domains/IPs)
        # "memory_pattern_domains", # Memory patterns (specialized)
        "memory_pattern_ips",     # Memory patterns (specialized)
        "memory_pattern_urls",    # Memory patterns (specialized)
    ],
    "IP": [
        "communicating_files",
        "downloaded_files",
        "historical_whois",
        "referrer_files",
        "resolutions",
        "urls",
    ],
    "Domain": [
        "associations",
        "caa_records",
        "cname_records",
        "communicating_files",
        "downloaded_files",
        "immediate_parent",
        "referrer_files",
        "resolutions",
        "siblings",
        "subdomains",
        "urls",
        "malware_families",
    ],
    "URL": [
        "communicating_files",
        "contacted_domains",
        "contacted_ips",
        "downloaded_files",
        "last_serving_ip_address",
        "network_location",
        "redirects_to",
        "referrer_files",
        "referrer_urls",
    ]
}

TRIAGE_ANALYSIS_PROMPT = """
You are a Senior Threat Intelligence Analyst performing comprehensive TRIAGE analysis.

**Your Role:**
You are the FIRST analyst to review this IOC. Your analysis will be used to decide
which specialist teams are dispatched and what they focus on.
You must provide a clear threat assessment, actionable key findings, and identify
which related entities are most important for deeper investigation.

**Available Intelligence:**
You have COMPLETE data from Google Threat Intelligence:
- Base threat indicators (verdict, score, stats)
- ALL priority relationships have been fetched and provided
- Full context about associated threats, infrastructure, and campaigns
- NOTE: Relationship entities have been pre-filtered to only include indicators
  with a malicious/suspicious verdict or significant vendor detections.

**Your Tasks:**

1. **THREAT ASSESSMENT**
   - Determine overall verdict (Malicious/Suspicious/Undetected/Benign)
   - Assess confidence level (High/Medium/Low)
   - Identify threat severity (Critical/High/Medium/Low)

2. **FIRST-LEVEL ANALYSIS**
   - Identify key threat indicators from the provided relationships
   - Recognize attack patterns (if malicious)
   - Map threat landscape (campaigns, actors, families)
   - Identify critical infrastructure elements (C2 domains/IPs, drop servers)
   - Flag high-priority entities in `priority_entities`

3. **CONTEXTUALIZATION**
   - Link to known campaigns/actors from associations
   - Identify behavioral patterns from relationship data
   - Assess operational context (is this active? recent?)
   - Determine attack stage (recon, delivery, exploitation, C2, etc.)

**Confidence Calibration:**
- **High**: 10+ vendor detections AND threat_score > 70 AND known malware family identified
- **Medium**: Some detections OR GTI flags it BUT missing corroborating signals
- **Low**: Few/no detections, relies on heuristic or contextual signals only

**Output Format (JSON):**
{
    "ioc_type": "IP|Domain|File|URL",
    "verdict": "Malicious|Suspicious|Undetected|Benign",
    "confidence": "High|Medium|Low",
    "severity": "Critical|High|Medium|Low",
    "threat_score": <number>,

    "executive_summary": "One to three paragraphs: verdict + key findings + recommended action",

    "key_findings": [
        "Finding 1 with specific entity IDs/names",
        "Finding 2 with context from relationships",
        "Finding 3 with threat actor/campaign attribution"
    ],

    "threat_context": {{
        "campaigns": ["Campaign names from associations"],
        "threat_actors": ["Actor names from associations"],
        "malware_families": ["Family names"],
        "attack_techniques": ["MITRE ATT&CK IDs/names"],
        "infrastructure_notes": "Brief description of C2/hosting infrastructure"
    }},

    "priority_entities": [
        {{
            "entity_id": "specific ID from relationships",
            "entity_type": "file|domain|ip_address|url",
            "reason": "Why this entity is important for specialist investigation",
            "relationship": "Which relationship it came from"
        }}
    ],

    "investigation_notes": "Additional context or caveats for specialists"
}

**OUTPUT INSTRUCTIONS:**
- Return ONLY valid JSON (no additional text before or after)
- Do not include markdown formatting in the output
- Only reference entities that appear in the provided relationship data — do NOT hallucinate IOCs
"""


def extract_triage_data(data: dict, ioc_type: str) -> dict:
    """Deterministically extracts 'Triage Data' for the Frontend."""
    triage_data = {}
    
    def get_val(d, path):
        keys = path.split('.')
        curr = d
        for k in keys:
            if isinstance(curr, dict):
                curr = curr.get(k)
                if curr is None: return None
            else:
                return None
        return curr
        
    triage_data["id"] = data.get("id")
    stats = get_val(data, "attributes.last_analysis_stats") or {}
    triage_data["malicious_stats"] = stats.get("malicious", 0)
    triage_data["total_stats"] = (
        stats.get("malicious", 0) + 
        stats.get("harmless", 0) + 
        stats.get("suspicious", 0) + 
        stats.get("undetected", 0) + 
        stats.get("timeout", 0)
    )

    triage_data["threat_score"] = get_val(data, "attributes.gti_assessment.threat_score.value")
    triage_data["verdict"] = get_val(data, "attributes.gti_assessment.verdict.value")
    triage_data["description"] = get_val(data, "attributes.gti_assessment.description")
    triage_data["crowdsourced_ai_results"] = get_val(data, "attributes.crowdsourced_ai_results")

    return triage_data

# --- DETERMINISTIC SUBTASK GENERATION ---
# Entity types that route to each specialist agent
MALWARE_ENTITY_TYPES = {"file"}
INFRA_ENTITY_TYPES = {"domain", "ip_address", "url"}

def generate_initial_subtasks(
    ioc: str,
    ioc_type: str,
    relationships_data: dict,
    priority_entities: list | None = None,
) -> list[dict]:
    """
    Deterministically generates first-round subtasks from the filtered
    relationship data. Only entities that passed the signal filter
    (malicious/suspicious verdict or >3 malicious vendors) are present
    in relationships_data, so every subtask targets a genuine indicator.

    Routing rules:
      - file entities      → malware_specialist
      - domain/ip/url      → infrastructure_specialist
      - root IOC           → appropriate specialist (always included)

    If the triage LLM returned priority_entities, those are preferred
    (they carry analyst context). Otherwise we build from relationships_data.
    """
    subtasks: list[dict] = []
    seen_entities: set[str] = set()

    def _agent_for_type(entity_type: str) -> str | None:
        t = entity_type.lower()
        if t in MALWARE_ENTITY_TYPES:
            return "malware_specialist"
        if t in INFRA_ENTITY_TYPES:
            return "infrastructure_specialist"
        return None

    def _add_subtask(entity_id: str, entity_type: str, context: str):
        if entity_id in seen_entities:
            return
        agent = _agent_for_type(entity_type)
        if not agent:
            return
        seen_entities.add(entity_id)
        subtasks.append({
            "agent": agent,
            "entity_id": entity_id,
            "task": f"Analyze {entity_type} indicator: {entity_id}",
            "context": context,
        })

    # 1. Always include the root IOC
    root_type_map = {"File": "file", "IP": "ip_address", "Domain": "domain", "URL": "url"}
    root_entity_type = root_type_map.get(ioc_type, "file")
    _add_subtask(ioc, root_entity_type, "Root IOC — primary target of investigation")

    # 2. If LLM provided priority_entities, route those first
    if priority_entities:
        for pe in priority_entities:
            eid = pe.get("entity_id")
            etype = pe.get("entity_type", "")
            reason = pe.get("reason", "Flagged by triage analysis")
            if eid:
                _add_subtask(eid, etype, reason)

    # 3. Backfill from filtered relationships_data (covers entities the LLM may have missed)
    for rel_name, entities in relationships_data.items():
        for entity in entities:
            eid = entity.get("id")
            etype = entity.get("type", "")
            if eid and eid not in seen_entities:
                _add_subtask(eid, etype, f"Discovered via '{rel_name}' relationship")

    logger.info(
        "deterministic_subtask_generation",
        total_subtasks=len(subtasks),
        malware_tasks=sum(1 for s in subtasks if s["agent"] == "malware_specialist"),
        infra_tasks=sum(1 for s in subtasks if s["agent"] == "infrastructure_specialist"),
    )
    return subtasks


def prepare_detailed_context_for_llm(relationships_data: dict) -> dict:
    """
    [TOKEN OPTIMIZATION] Prepare minimal context for LLM analysis.
    Filter out display-only fields to reduce token usage.
    """
    detailed_context = {}
    
    # Fields to keep for LLM (exclude display-only fields)
    llm_fields = ["id", "type", "display_name", "verdict", "threat_score", 
                  "malicious_count", "file_type", "reputation", "name"]
    
    for rel_name, entities in relationships_data.items():
        # Filter entities to only include LLM-relevant fields
        filtered_entities = []
        for entity in entities:
            filtered = {k: v for k, v in entity.items() if k in llm_fields}
            filtered_entities.append(filtered)
        
        detailed_context[rel_name] = {
            "count": len(entities),
            "entities": filtered_entities
        }
    
    return detailed_context

def generate_markdown_report_locally(analysis: dict, ioc: str, ioc_type: str, triage_data: dict = None) -> str:
    """
    Generates a markdown report from the structured JSON analysis.
    This avoids JSON parsing errors caused by large markdown strings in LLM output.
    """
    try:
        md = f"## IOC Triage Report\n\n"
        
        # 1. Detection Summary (GTI + VT)
        md += "### Detection Summary\n"
        verdict = analysis.get('verdict', triage_data.get('verdict') if triage_data else 'Unknown')
        score = analysis.get('threat_score', triage_data.get('threat_score') if triage_data else None)
        score_str = f"`{score}/100`" if score is not None else "`Unknown`"
        
        # Color-coded verdict (emoji-based for markdown)
        v_emoji = "✅"
        if verdict.lower() == "malicious": v_emoji = "🔴"
        elif verdict.lower() == "suspicious": v_emoji = "🟠"
        
        md += f"*   **GTI Verdict:** {v_emoji} **{verdict}**\n"
        md += f"*   **Threat Score:** {score_str}\n"
        
        if triage_data and triage_data.get("total_stats"):
            m = triage_data.get("malicious_stats", 0)
            t = triage_data["total_stats"]
            ratio = (m / t) * 100 if t > 0 else 0
            md += f"*   **VT Detection Ratio:** `{m}/{t}` ({ratio:.1f}%)\n"
        
        md += f"*   **Confidence:** {analysis.get('confidence', 'Unknown')}\n"
        md += f"*   **Severity:** {analysis.get('severity', 'Unknown')}\n\n"
        
        # 2. Executive Summary
        md += "### Executive Summary\n"
        md += f"{analysis.get('executive_summary', 'No summary provided.')}\n\n"
        
        # 3. Key Findings
        if analysis.get("key_findings"):
            md += "### Key Findings\n"
            for finding in analysis["key_findings"]:
                md += f"*   {finding}\n"
            md += "\n"
            
        # 4. Threat Context
        context = analysis.get("threat_context", {})
        md += "### Threat Context\n"
        if context.get("campaigns"):
            md += f"*   **Campaigns:** {', '.join(str(c) for c in context['campaigns'])}\n"
        if context.get("threat_actors"):
            md += f"*   **Threat Actors:** {', '.join(str(c) for c in context['threat_actors'])}\n"
        if context.get("malware_families"):
            md += f"*   **Malware Families:** {', '.join(str(c) for c in context['malware_families'])}\n"
        
        techniques = context.get("attack_techniques", [])
        if techniques:
            md += "*   **Attack Techniques (MITRE ATT&CK):**\n"
            for tech in techniques:
                md += f"    *   {tech}\n"
        
        if context.get("infrastructure_notes"):
            md += f"*   **Infrastructure Notes:** {context['infrastructure_notes']}\n"
        md += "\n"
            
        # 5. Priority Entities table
        entities = analysis.get("priority_entities", [])
        if entities:
            md += "### Priority Entities\n"
            md += "| Entity ID | Entity Type | Reason |\n"
            md += "| :--- | :--- | :--- |\n"
            for e in entities:
                md += f"| `{e.get('entity_id')}` | {e.get('entity_type')} | {e.get('reason')} |\n"
            md += "\n"
            
        # 6. Investigation Notes
        if analysis.get("investigation_notes"):
            md += "### Investigation Notes\n"
            md += f"{analysis.get('investigation_notes')}\n"
            
            
        # 7. WebRisk Analysis (if available)
        wr_result = analysis.get("webrisk_result")
        if wr_result:
            md += "### Google Web Risk Analysis\n"
            if "scores" in wr_result:
                is_safe = True
                for score in wr_result["scores"]:
                    threat = score.get("threatType", "Unknown")
                    confidence = score.get("confidenceLevel", "Unknown")
                    md += f"*   **{threat}:** {confidence}\n"
                    if confidence != "SAFE":
                        is_safe = False
                
                if not is_safe:
                    md += "\n> ⚠️ **WebRisk Warning**: One or more threat types detected.\n"
            elif "error" in wr_result:
                 md += f"⚠️ API Error: {wr_result['error']}\n"
            else:
                 md += "✅ No threats detected by WebRisk.\n"
            md += "\n"
            
        return md
    except Exception as e:
        return f"Error generating markdown report: {str(e)}"

async def comprehensive_triage_analysis(
    ioc: str,
    ioc_type: str,
    triage_data: dict,
    relationships_data: dict,
    state: dict = None  # Added to access job_id
) -> dict:
    """
    PHASE 2: Comprehensive first-level analysis by triage LLM.
    Provides deep analysis that guides specialist investigations.
    """
    logger.info("phase2_start_comprehensive_analysis",
                ioc=ioc,
                relationships_found=len(relationships_data),
                total_entities=sum(len(entities) for entities in relationships_data.values()))
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is missing.")
    
#    location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")
#    llm = ChatVertexAI(
#        model="gemini-2.5-flash",
#        #model="gemini-3-flash-preview",
#        temperature=0.0, # recommend to remove for gemini 3
#        project=project_id,
#        location=location
#    )
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        temperature=0,
        #max_tokens=1024,
        project=project_id,
        location="global",
        #vertexai=True,  # Explicitly use Vertex AI
    )
    
    # Prepare detailed context (not just counts)
    detailed_context = prepare_detailed_context_for_llm(relationships_data)
    
    messages = [
        SystemMessage(content=TRIAGE_ANALYSIS_PROMPT),
        HumanMessage(content=f"""
**IOC Under Investigation:**
{ioc} ({ioc_type})

**Base Threat Assessment:**
{json.dumps(triage_data, indent=2)}

**Complete Relationship Data:**
ALL priority relationships have been fetched. Here is the complete intelligence:

{json.dumps(detailed_context, indent=2)}

**Statistics:**
- Total relationships checked: {len(PRIORITY_RELATIONSHIPS.get(ioc_type, []))}
- Relationships with data: {len(relationships_data)}
- Total entities found: {sum(len(entities) for entities in relationships_data.values())}

Perform comprehensive first-level triage analysis now.
        """)
    ]
    
    # Emit reasoning event before LLM call
    job_id = state.get("job_id") if 'state' in locals() else None
    if job_id:
        await emit_tool_call(job_id, "triage", "comprehensive_analysis_llm", {
            "model": "gemini-2.5-flash",
            "ioc": ioc,
            "relationships_count": len(relationships_data)
        })
    
    response = await llm.ainvoke(messages)
    
    # Parse response
    try:
        if isinstance(response.content, list):
            parts = []
            for block in response.content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if isinstance(text, (dict, list)):
                        parts.append(json.dumps(text))
                    else:
                        parts.append(str(text))
                else:
                    parts.append(str(block))
            final_text = "".join(parts)
        else:
            final_text = str(response.content)
        
        clean_content = final_text.replace("```json", "").replace("```", "").strip()
        analysis = json.loads(clean_content)
        
        # [NEW] WebRisk Check for URLs
        if ioc_type == "URL":
            verdict = analysis.get("verdict", "").lower()
            reasoning = final_text.lower()
            should_check = (
                verdict in ["suspicious", "malicious"] or
                "phishing" in reasoning or
                "social engineering" in reasoning
            )
            
            if should_check:
                logger.info("triage_webrisk_check_triggered", ioc=ioc)
                try:
                    # Emit WebRisk tool call
                    if job_id:
                        await emit_tool_call(job_id, "triage", "webrisk.evaluate_uri", {"url": ioc})
                    
                    wr_result = await webrisk.evaluate_uri(ioc)
                    analysis["webrisk_result"] = wr_result
                except Exception as e:
                    logger.error("triage_webrisk_failed", error=str(e))
                    analysis["webrisk_result"] = {"error": str(e)}
        
        analysis["markdown_report"] = generate_markdown_report_locally(analysis, ioc, ioc_type, triage_data)
        analysis["_llm_reasoning"] = final_text  # Store for transparency
        
        # Emit LLM reasoning for real-time transparency
        if job_id:
            await emit_reasoning(job_id, "triage", final_text)
        
        logger.info("phase2_analysis_complete",
                   verdict=analysis.get("verdict"),
                   confidence=analysis.get("confidence"),
                   severity=analysis.get("severity"),
                   key_findings=len(analysis.get("key_findings", [])),
                   priority_entities=len(analysis.get("priority_entities", [])),
                   subtasks=len(analysis.get("subtasks", [])))
        
        return analysis
        
    except Exception as e:
        logger.error("phase2_parse_error", error=str(e), raw=str(response.content)[:500])
        
        # Fallback with error visibility
        import traceback
        tb = traceback.format_exc()
        
        analysis = {
            "ioc_type": ioc_type,
            "verdict": triage_data.get("verdict", "Unknown"),
            "confidence": "Low",
            "severity": "Medium",
            "threat_score": triage_data.get("threat_score", "N/A"),
            "executive_summary": f"Analysis failed: {str(e)}",
            "key_findings": [
                f"Found {len(entities)} entities in {rel_name}"
                for rel_name, entities in relationships_data.items()
            ],
            "threat_context": {},
            "priority_entities": [],
            "subtasks": [],
            "investigation_notes": f"System Error: {str(e)}",
            "_llm_reasoning": f"## Parsing Error\n\nThe LLM output could not be parsed:\n\n```\n{str(e)}\n```\n\n### Raw Output\n```\n{final_text if 'final_text' in locals() else str(response.content)}\n```\n\n### Traceback\n```\n{tb}\n```"
        }
        analysis["markdown_report"] = generate_markdown_report_locally(analysis, ioc, ioc_type, triage_data)
        return analysis


async def triage_node(state: AgentState):
    """
    HYBRID APPROACH:
    - Phase 1: Pure Python fetches ALL relationships (deterministic)
    - Phase 2: Triage LLM does comprehensive first-level analysis (intelligent)
    - Result: Complete graph + actionable intelligence for specialists
    """
    ioc = state["ioc"]
    logger.info("triage_start", ioc=ioc, mode="hybrid_comprehensive")
    
    try:
        # 1. IOC Identification
        url_pattern = r"^https?://.+"
        ipv4_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
        ipv6_pattern = r"^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^(?:[0-9a-fA-F]{1,4}:)*:[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4})*$"
        hash_pattern = r"^[a-fA-F0-9]{32,64}$"
        domain_pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
        
        config = {}
        
        if re.match(url_pattern, ioc, re.IGNORECASE):
            config = {"type": "URL", "direct_tool": gti.get_url_report, 
                     "rel_tool": "get_entities_related_to_an_url", "arg": "url"}
        elif re.match(ipv4_pattern, ioc) or re.match(ipv6_pattern, ioc):
            config = {"type": "IP", "direct_tool": gti.get_ip_report, 
                     "rel_tool": "get_entities_related_to_an_ip_address", "arg": "ip_address"}
        elif re.match(hash_pattern, ioc):
             config = {"type": "File", "direct_tool": gti.get_file_report, 
                      "rel_tool": "get_entities_related_to_a_file", "arg": "hash"}
        elif re.match(domain_pattern, ioc):
             config = {"type": "Domain", "direct_tool": gti.get_domain_report, 
                      "rel_tool": "get_entities_related_to_a_domain", "arg": "domain"}
        else:
             # Fallback to file if it doesn't match other formats, as hashes can sometimes be weird
             config = {"type": "File", "direct_tool": gti.get_file_report, 
                      "rel_tool": "get_entities_related_to_a_file", "arg": "hash"}
             
        logger.info("triage_detected_type", type=config["type"])
        
        priority_rels = PRIORITY_RELATIONSHIPS.get(config["type"], ["associations"])
        
        # 2. Get base facts AND relationships in one Super-Bundle call
        logger.info("triage_fetching_super_bundle", ioc=ioc, rel_count=len(priority_rels))
        
        # Emit tool invocation for transparency
        job_id = state.get("job_id")
        if job_id:
            await emit_tool_call(job_id, "triage", f"gti.{config['direct_tool'].__name__}", {
                "ioc": ioc,
                "relationships": priority_rels[:5]  # Show first 5 to avoid huge logs
            })
        
        # Pass priority_rels to the tool to trigger bundling
        base_data = await config["direct_tool"](ioc, relationships=priority_rels)
        
        if not base_data or "data" not in base_data:
             logger.warning("triage_direct_api_empty", ioc=ioc)
             base_data = {"id": ioc}
        else:
             base_data = base_data["data"]

        triage_data = extract_triage_data(base_data, config["type"])
        
        # Initialize metadata
        if "metadata" not in state: state["metadata"] = {} # Safety check
        state["metadata"]["risk_level"] = "Assessing..." 
        state["metadata"]["gti_score"] = triage_data.get("threat_score")
        state["metadata"]["rich_intel"] = triage_data
        
        # ========================================
        # PHASE 1: Super-Bundle Relationship Parsing
        # ========================================
        # Initialize NetworkX cache from state or create new
        cache = InvestigationCache(state.get("investigation_graph"))
        
        # Store root IOC in cache with full base_data attributes
        cache.add_entity(
            entity_id=ioc,
            entity_type=config["type"].lower(),
            attributes=base_data.get("attributes", {})
        )
        logger.info("networkx_cached_root", ioc=ioc, type=config["type"])
        
        relationships_data = {}
        tool_call_trace = []
        
        raw_relationships = base_data.get("relationships", {})
        
        for rel_name, rel_content in raw_relationships.items():
            # Check if relationship has actual data (list of entities)
            entities_list = rel_content.get("data")
            
            if entities_list and isinstance(entities_list, list) and len(entities_list) > 0:
                # [NETWORKX] Store FULL entities in cache (all attributes)
                # [LLM] Extract minimal fields for token optimization
                parsed_entities = []
                for entity in entities_list:
                    entity_id = entity.get("id")
                    entity_type = entity.get("type")
                    full_attrs = entity.get("attributes", {})
                    
                    # STORE FULL ENTITY IN NETWORKX CACHE
                    cache.add_entity(
                        entity_id=entity_id,
                        entity_type=entity_type,
                        attributes=full_attrs
                    )
                    # Add relationship edge
                    cache.add_relationship(ioc, entity_id, rel_name)
                    
                    # Now parse minimal + display fields for LLM and graph UI
                    attrs = full_attrs
                    
                    # Base entity (always include)
                    parsed = {
                        "id": entity_id,
                        "type": entity_type,
                    }
                    
                    # [GRAPH VIZ] Add display fields for visualization
                    # Store fields needed for display AND mouseover
                    
                    # URL entities
                    if entity_type == "url":
                        url_value = attrs.get("url") or attrs.get("last_final_url")
                        if url_value:
                            parsed["url"] = url_value  # Store full URL
                            parsed["display_name"] = url_value
                        else:
                            parsed["display_name"] = entity_id
                        
                        # Add categories for mouseover
                        if attrs.get("categories"):
                            parsed["categories"] = attrs["categories"]
                    
                    # File entities
                    elif entity_type == "file":
                        # Store filename(s)
                        if attrs.get("meaningful_name"):
                            parsed["meaningful_name"] = attrs["meaningful_name"]
                            parsed["display_name"] = attrs["meaningful_name"]
                        elif attrs.get("names") and len(attrs["names"]) > 0:
                            parsed["names"] = attrs["names"][:3]  # Store up to 3 names
                            parsed["display_name"] = attrs["names"][0]
                        else:
                            parsed["display_name"] = entity_id[:16] + "..."
                        
                        # Store size and file type for mouseover
                        if attrs.get("size"):
                            parsed["size"] = attrs["size"]
                        if attrs.get("type_description"):
                            parsed["file_type"] = attrs["type_description"]
                    
                    # Domain/IP entities
                    elif entity_type in ["domain", "ip_address"]:
                        parsed["display_name"] = entity_id
                        if attrs.get("reputation"):
                            parsed["reputation"] = attrs["reputation"]
                    
                    # Campaign/Threat Actor entities
                    elif entity_type in ["collection", "campaign", "threat_actor"]:
                        name = attrs.get("name") or attrs.get("title")
                        if name:
                            parsed["name"] = name
                            parsed["display_name"] = name
                        else:
                            parsed["display_name"] = entity_id
                    
                    # Default for other types
                    else:
                        parsed["display_name"] = entity_id
                    
                    # Add GTI verdict fields (for all entity types)
                    gti_data = attrs.get("gti_assessment", {})
                    if gti_data.get("verdict"):
                        parsed["verdict"] = gti_data["verdict"].get("value")
                    if gti_data.get("threat_score"):
                        parsed["threat_score"] = gti_data["threat_score"].get("value")
                    
                    # Add malicious count
                    stats = attrs.get("last_analysis_stats", {})
                    if stats.get("malicious", 0) > 0:
                        parsed["malicious_count"] = stats["malicious"]
                    
                    parsed_entities.append(parsed)

                # --- SIGNAL FILTER ---
                # NetworkX already has the full entity set above.
                # For LLM context we apply a strict signal filter so only
                # meaningful indicators reach the prompt.
                # Attribution relationship types are exempt — their entities
                # (campaigns, actors, families) have no gti_assessment.
                if rel_name not in UNFILTERED_RELATIONSHIPS:
                    pre_filter_count = len(parsed_entities)
                    parsed_entities = [
                        e for e in parsed_entities
                        if (
                            str(e.get("verdict") or "").lower() in {"malicious", "suspicious"}
                            or (e.get("malicious_count") or 0) >= SIGNAL_MALICIOUS_VENDORS
                        )
                    ]
                    filtered_count = pre_filter_count - len(parsed_entities)
                    if filtered_count > 0:
                        logger.debug(
                            "triage_entity_filter",
                            rel=rel_name,
                            dropped=filtered_count,
                            kept=len(parsed_entities),
                        )

                # Sort survivors by threat score (highest first) before capping,
                # so the most dangerous indicators are never pushed out.
                parsed_entities.sort(
                    key=lambda e: (e.get("threat_score") or 0), reverse=True
                )

                # SAFETY SLICE: cap to prevent token overflow
                if len(parsed_entities) > MAX_ENTITIES_PER_RELATIONSHIP:
                    parsed_entities = parsed_entities[:MAX_ENTITIES_PER_RELATIONSHIP]

                # Skip relationships where filtering removed all entities —
                # no point sending an empty list to the LLM.
                if not parsed_entities:
                    logger.debug("triage_relationship_skipped_all_filtered", rel=rel_name)
                    continue

                relationships_data[rel_name] = parsed_entities

                # Add to trace
                tool_call_trace.append({
                    "relationship": rel_name,
                    "status": "success",
                    "entities_found": len(parsed_entities),
                    "sample_entity": {"id": parsed_entities[0]["id"], "type": parsed_entities[0]["type"]}
                })
        
        # Log cache statistics
        cache_stats = cache.get_stats()
        logger.info("phase1_super_bundle_complete", 
                    relationships_found=len(relationships_data),
                    total_entities=sum(len(e) for e in relationships_data.values()),
                    networkx_cache=cache_stats)

        # Store in state for graph building
        state["metadata"]["rich_intel"]["relationships"] = relationships_data
        state["metadata"]["tool_call_trace"] = tool_call_trace
        state["investigation_graph"] = cache.get_state()  # Persist cache in state
        
        # ========================================
        # PHASE 2: Comprehensive Triage Analysis
        # ========================================
        analysis = await comprehensive_triage_analysis(
            ioc=ioc,
            ioc_type=config["type"],
            triage_data=triage_data,
            relationships_data=relationships_data,
            state=state  # Pass state for job_id access
        )
        
        # Update state with comprehensive analysis
        state["ioc_type"] = analysis.get("ioc_type")

        # ========================================
        # PHASE 3: Deterministic Subtask Generation
        # ========================================
        # Subtasks are generated from the filtered relationships_data,
        # informed by the LLM's priority_entities. This replaces the
        # previous approach where the triage LLM generated subtasks directly.
        state["subtasks"] = generate_initial_subtasks(
            ioc=ioc,
            ioc_type=config["type"],
            relationships_data=relationships_data,
            priority_entities=analysis.get("priority_entities", []),
        )
        state["tasked_entities"] = [t["entity_id"] for t in state["subtasks"] if "entity_id" in t]
        
        # Store comprehensive triage findings
        state["metadata"]["rich_intel"]["triage_analysis"] = {
            "executive_summary": analysis.get("executive_summary"),
            "key_findings": analysis.get("key_findings", []),
            "threat_context": analysis.get("threat_context", {}),
            "priority_entities": analysis.get("priority_entities", []),
            "confidence": analysis.get("confidence"),
            "severity": analysis.get("severity"),
            "investigation_notes": analysis.get("investigation_notes", ""),
            "markdown_report": analysis.get("markdown_report", ""),
            "_llm_reasoning": analysis.get("_llm_reasoning"),
        }
        
        # Maintain backward compatibility
        state["metadata"]["rich_intel"]["triage_summary"] = analysis.get("executive_summary")
        state["metadata"]["risk_level"] = analysis.get("verdict", "Unknown")
        
        # [REPORT INIT] Initialize final_report with triage findings
        state["final_report"] = analysis.get("markdown_report", "")
        # Initialize iteration if not present
        if "iteration" not in state: state["iteration"] = 1

        
        logger.info("triage_complete",
                   verdict=state["metadata"]["risk_level"],
                   confidence=analysis.get("confidence"),
                   severity=analysis.get("severity"),
                   key_findings=len(analysis.get("key_findings", [])),
                   priority_entities=len(analysis.get("priority_entities", [])),
                   subtasks=len(state["subtasks"]),
                   relationships=len(relationships_data),
                   total_entities=sum(len(entities) for entities in relationships_data.values()))
                
    except Exception as e:
        logger.error("triage_fatal_error", error=str(e))
        if "metadata" not in state: state["metadata"] = {} # Ensuring metadata exists on error
        state["metadata"]["risk_level"] = "Error"
        if "rich_intel" not in state["metadata"]: state["metadata"]["rich_intel"] = {}
        
        # Fatal error visibility
        import traceback
        tb = traceback.format_exc()
        state["metadata"]["rich_intel"]["triage_analysis"] = {
            "executive_summary": f"Fatal System Error: {str(e)}",
            "_llm_reasoning": f"## Fatal Error\n\nA critical system error occurred:\n\n```\n{str(e)}\n```\n\n### Traceback\n```\n{tb}\n```"
        }
        
    return state
