import os
import json
import re
import asyncio

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_vertexai import ChatVertexAI
from backend.graph.state import AgentState
from backend.utils.logger import get_logger
import backend.tools.gti as gti
from backend.utils.graph_cache import InvestigationCache

logger = get_logger("agent_triage")

# Graph growth control
MAX_ENTITIES_PER_RELATIONSHIP = 10  # Increased from 5 to fetch more entities per relationship
MAX_TOTAL_ENTITIES = 150  # Increased from 50 to accommodate 52 relationship types
MIN_THREAT_SCORE = 0  # TODO: Add smart filtering (Option B) - prioritize by threat score
REQUIRE_MALICIOUS_VERDICT = False  # TODO: Add smart filtering (Option B) - prioritize malicious entities

# Define priority relationships for each IOC type
# [TOKEN OPTIMIZATION] Reduced from 20 to 11 critical relationships
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
        # "contacted_urls",       # URLs contacted (covered by domains/IPs)
        # "embedded_urls",        # Embedded URLs (covered by domains/IPs)
        # "email_attachments",    # Email-related relationships
        # "email_parents",        # Email-related relationships
        # "itw_urls",             # In-the-wild URLs (covered by domains/IPs)
        # "memory_pattern_domains", # Memory patterns (specialized)
        # "memory_pattern_ips",     # Memory patterns (specialized)
        # "memory_pattern_urls",    # Memory patterns (specialized)
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
        # "historical_ssl_certificates",
        "immediate_parent",
        # "parent",
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
        # "embedded_js_files",
        "last_serving_ip_address",
        # "memory_pattern_parents",
        "network_location",
        # "redirecting_urls",
        "redirects_to",
        "referrer_files",
        "referrer_urls",
    ]
}

TRIAGE_ANALYSIS_PROMPT = """
You are a Senior Threat Intelligence Analyst performing comprehensive TRIAGE analysis.

**Your Role:**
You are the FIRST analyst to review this IOC. Your analysis will guide specialist teams.
You must provide actionable intelligence and clear direction for deep-dive investigations.

**Available Intelligence:**
You have COMPLETE data from Google Threat Intelligence:
- Base threat indicators (verdict, score, stats)
- ALL priority relationships have been fetched and provided
- Full context about associated threats, infrastructure, and campaigns

**Your Tasks:**

1. **THREAT ASSESSMENT**
   - Determine overall verdict (Malicious/Suspicious/Undetected/Benign)
   - Assess confidence level (High/Medium/Low)
   - Identify threat severity

2. **FIRST-LEVEL ANALYSIS** (This is critical!)
   - Identify key threat indicators from relationships
   - Recognize attack patterns (if malicious)
   - Map threat landscape (campaigns, actors, families)
   - Identify critical infrastructure elements
   - Flag high-priority entities for specialist investigation

3. **CONTEXTUALIZATION**
   - Link to known campaigns/actors from associations
   - Identify behavioral patterns from relationship data
   - Assess operational context (is this active? recent?)
   - Determine attack stage (recon, delivery, exploitation, etc.)

4. **ROUTING & PRIORITIZATION**
   - Generate specific, actionable subtasks for specialists
   - Prioritize what specialists should focus on first
   - Provide context specialists need (don't make them rediscover)
   - Include key entity IDs specialists should examine
   - YOU MUST ONLY ASSIGN TASKS TO AVAILABLE AGENTS.
   - **AVAILABLE AGENTS:**
     * `malware_specialist`: For file analysis, YARA scanning, and code reverse engineering.
     * `infrastructure_specialist`: For IP/Domain pivots, passive DNS, and mapping hosting infrastructure.
   - If no specialist is needed, leave "subtasks" empty.

**Analysis Framework:**

For MALICIOUS files:
- What does it do? (dropped_files, contacted_* relationships)
- Who made it? (associations → campaigns/actors)
- How does it work? (attack_techniques)
- Where is the infrastructure? (contacted_domains/ips)
- **ACTION**: Assign to `malware_specialist` if file analysis is needed.
- **ACTION**: Assign to `infrastructure_specialist` if critical C2 IPs/Domains need deep pivoting.

For MALICIOUS infrastructure (IP/Domain):
- What's hosted here? (downloaded_files, urls)
- Who connects to it? (communicating_files)
- What's the infrastructure map? (resolutions, subdomains)
- What campaigns use it? (associations)
- **ACTION**: Assign to `infrastructure_specialist`.

For SUSPICIOUS/UNDETECTED:
- What's uncertain? (missing data, conflicting signals)
- What needs verification? (specific relationships to check)
- What's the risk if true positive? (potential impact)

**Output Format (JSON):**
{
    "ioc_type": "IP|Domain|File|URL",
    "verdict": "Malicious|Suspicious|Undetected|Benign",
    "confidence": "High|Medium|Low",
    "severity": "Critical|High|Medium|Low",
    "threat_score": <number>,
    
    "executive_summary": "One paragraph: verdict + key findings + recommended action",
    
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
            "entity_type": "file|domain|ip",
            "reason": "Why this entity is important",
            "relationship": "Which relationship it came from"
        }}
    ],
    
    "subtasks": [
        {{
            "agent": "malware_specialist",
            "priority": "high|medium|low",
            "entity_id": "Exact ID of the entity to analyze (e.g. 1.2.3.4, malicious.com, or hash)",
            "task": "Specific task with entity IDs and focus areas",
            "context": "What you found that makes this task necessary"
        }
    ],
    
    "investigation_notes": "Additional context or caveats for specialists"
}

**OUTPUT INSTRUCTIONS:**
- Return ONLY valid JSON (no additional text before or after)
- Do not include markdown formatting in the output
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
    triage_data["malicious_stats"] = get_val(data, "attributes.last_analysis_stats.malicious")
    stats = get_val(data, "attributes.last_analysis_stats") or {}
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

def generate_markdown_report_locally(analysis: dict, ioc: str, ioc_type: str) -> str:
    """
    Generates a markdown report from the structured JSON analysis.
    This avoids JSON parsing errors caused by large markdown strings in LLM output.
    """
    try:
        md = f"# IOC Triage Report\n\n"
        
        # 1. IOC Summary
        md += "## IOC Summary\n"
        md += f"*   **IOC Type:** {ioc_type}\n"
        md += f"*   **IOC Value:** `{ioc}`\n"
        md += f"*   **Verdict:** {analysis.get('verdict', 'Unknown')}\n"
        md += f"*   **Confidence:** {analysis.get('confidence', 'Unknown')}\n"
        md += f"*   **Severity:** {analysis.get('severity', 'Unknown')}\n"
        md += f"*   **Threat Score:** {analysis.get('threat_score', 'N/A')}\n\n"
        
        # 2. Executive Summary
        md += "## Executive Summary\n"
        md += f"{analysis.get('executive_summary', 'No summary provided.')}\n\n"
        
        # 3. Key Findings
        if analysis.get("key_findings"):
            md += "## Key Findings\n"
            for finding in analysis["key_findings"]:
                md += f"*   {finding}\n"
            md += "\n"
            
        # 4. Threat Context
        context = analysis.get("threat_context", {})
        md += "## Threat Context\n"
        if context.get("campaigns"):
            md += f"*   **Campaigns:** {', '.join(context['campaigns'])}\n"
        if context.get("threat_actors"):
            md += f"*   **Threat Actors:** {', '.join(context['threat_actors'])}\n"
        if context.get("malware_families"):
            md += f"*   **Malware Families:** {', '.join(context['malware_families'])}\n"
        
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
            md += "## Priority Entities\n"
            md += "| Entity ID | Entity Type | Reason |\n"
            md += "| :--- | :--- | :--- |\n"
            for e in entities:
                md += f"| `{e.get('entity_id')}` | {e.get('entity_type')} | {e.get('reason')} |\n"
            md += "\n"
            
        # 6. Investigation Notes
        if analysis.get("investigation_notes"):
            md += "## Investigation Notes\n"
            md += f"{analysis.get('investigation_notes')}\n"
            
        return md
    except Exception as e:
        return f"Error generating markdown report: {str(e)}"

async def comprehensive_triage_analysis(
    ioc: str,
    ioc_type: str,
    triage_data: dict,
    relationships_data: dict
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
    
    location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")
    llm = ChatVertexAI(
        model="gemini-2.5-flash",
        #model="gemini-3-flash-preview",
        temperature=0.0, # recommend to remove for gemini 3
        project=project_id,
        location=location
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
    
    response = await llm.ainvoke(messages)
    
    # Parse response
    try:
        if isinstance(response.content, list):
            final_text = "".join([
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in response.content
            ])
        else:
            final_text = str(response.content)
        
        clean_content = final_text.replace("```json", "").replace("```", "").strip()
        analysis = json.loads(clean_content)
        
        # [FIX] Generate Markdown Report Locally
        # This is more robust than asking the LLM to put markdown inside JSON
        analysis["markdown_report"] = generate_markdown_report_locally(analysis, ioc, ioc_type)
        analysis["_llm_reasoning"] = final_text  # Store for transparency
        
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
        
        return {
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
        ipv4_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
        config = {}
        
        if "http" in ioc or "/" in ioc:
            config = {"type": "URL", "direct_tool": gti.get_url_report, 
                     "rel_tool": "get_entities_related_to_an_url", "arg": "url"}
        elif re.match(ipv4_pattern, ioc):
            config = {"type": "IP", "direct_tool": gti.get_ip_report, 
                     "rel_tool": "get_entities_related_to_an_ip_address", "arg": "ip_address"}
        elif "." in ioc:
             config = {"type": "Domain", "direct_tool": gti.get_domain_report, 
                      "rel_tool": "get_entities_related_to_a_domain", "arg": "domain"}
        else:
             config = {"type": "File", "direct_tool": gti.get_file_report, 
                      "rel_tool": "get_entities_related_to_a_file", "arg": "hash"}
             
        logger.info("triage_detected_type", type=config["type"])
        
        priority_rels = PRIORITY_RELATIONSHIPS.get(config["type"], ["associations"])
        
        # 2. Get base facts AND relationships in one Super-Bundle call
        logger.info("triage_fetching_super_bundle", ioc=ioc, rel_count=len(priority_rels))
        
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
        state["metadata"]["gti_score"] = triage_data["threat_score"] or "N/A"
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
                
                # Apply severity filter if needed (reuse existing logic if possible or keep simple)
                # SAFETY SLICE: Prevent token overflow by limiting entities
                if len(parsed_entities) > MAX_ENTITIES_PER_RELATIONSHIP:
                    parsed_entities = parsed_entities[:MAX_ENTITIES_PER_RELATIONSHIP]
                    
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
        state["investigation_graph"] = cache.graph  # Persist cache in state
        
        # ========================================
        # PHASE 2: Comprehensive Triage Analysis
        # ========================================
        analysis = await comprehensive_triage_analysis(
            ioc=ioc,
            ioc_type=config["type"],
            triage_data=triage_data,
            relationships_data=relationships_data
        )
        
        # Update state with comprehensive analysis
        state["ioc_type"] = analysis.get("ioc_type")
        state["subtasks"] = analysis.get("subtasks", [])
        
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
            "_llm_reasoning": analysis.get("_llm_reasoning")
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
