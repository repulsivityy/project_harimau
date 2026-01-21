import os
import json
import re
import asyncio

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_vertexai import ChatVertexAI
from backend.graph.state import AgentState
from backend.mcp.client import mcp_manager
from backend.utils.logger import get_logger
import backend.tools.gti as gti

logger = get_logger("agent_triage")

# Graph growth control
MAX_ENTITIES_PER_RELATIONSHIP = 10  # Increased from 5 to fetch more entities per relationship
MAX_TOTAL_ENTITIES = 150  # Increased from 50 to accommodate 52 relationship types
MIN_THREAT_SCORE = 0  # TODO: Add smart filtering (Option B) - prioritize by threat score
REQUIRE_MALICIOUS_VERDICT = False  # TODO: Add smart filtering (Option B) - prioritize malicious entities

# Define priority relationships for each IOC type
PRIORITY_RELATIONSHIPS = {
    "File": [
        "associations",
        "bundled_files",
        "contacted_domains",
        "contacted_ips",
        "contacted_urls",
        "dropped_files",
        "embedded_domains",
        "embedded_ips",
        "embedded_urls",
        "email_attachments",
        "email_parents",
        "execution_parents",
        "itw_domains",
        "itw_ips",
        "itw_urls",
        "malware_families",
        "memory_pattern_domains",
        "memory_pattern_ips",
        "memory_pattern_urls",
        "attack_techniques",
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
        "historical_ssl_certificates",
        "immediate_parent",
        "parent",
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
        "embedded_js_files",
        "last_serving_ip_address",
        "memory_pattern_parents",
        "network_location",
        "redirecting_urls",
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

**Analysis Framework:**

For MALICIOUS files:
- What does it do? (dropped_files, contacted_* relationships)
- Who made it? (associations → campaigns/actors)
- How does it work? (attack_techniques)
- Where is the infrastructure? (contacted_domains/ips)

For MALICIOUS infrastructure (IP/Domain):
- What's hosted here? (downloaded_files, urls)
- Who connects to it? (communicating_files)
- What's the infrastructure map? (resolutions, subdomains)
- What campaigns use it? (associations)

For SUSPICIOUS/UNDETECTED:
- What's uncertain? (missing data, conflicting signals)
- What needs verification? (specific relationships to check)
- What's the risk if true positive? (potential impact)

**Output Format (JSON):**
{{
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
            "agent": "malware_specialist|infrastructure_specialist",
            "priority": "high|medium|low",
            "task": "Specific task with entity IDs and focus areas",
            "context": "What you found that makes this task necessary"
        }}
    ],
    
    "investigation_notes": "Additional context or caveats for specialists"
}}

**CRITICAL REMINDERS:**
- You have COMPLETE data - use all of it
- Be specific - include entity IDs and names
- Provide context - don't make specialists rediscover your findings
- Prioritize - what's most important for specialists to examine?
- Be actionable - subtasks should be concrete and focused
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

    return triage_data


def filter_entities_by_severity(entities: list, rel_name: str) -> list:
    """Filter entities by threat score and verdict to control graph growth."""
    if not entities:
        return []
    
    filtered = []
    for entity in entities:
        entity_type = entity.get("type", "")
        if entity_type == "collection":
            filtered.append(entity)
            continue
        
        attrs = entity.get("attributes", {})
        
        if REQUIRE_MALICIOUS_VERDICT:
            gti_verdict = attrs.get("gti_assessment", {}).get("verdict", {}).get("value", "")
            if gti_verdict.lower() != "malicious":
                continue
        
        if MIN_THREAT_SCORE > 0:
            threat_score = attrs.get("gti_assessment", {}).get("threat_score", {}).get("value", 0)
            if threat_score < MIN_THREAT_SCORE:
                continue
        
        filtered.append(entity)
    
    if len(filtered) < len(entities):
        logger.info("filter_entities_by_severity", 
                   rel=rel_name,
                   original=len(entities),
                   filtered=len(filtered))
    
    return filtered


def parse_mcp_tool_response(res_txt: str, logger, rel_name: str) -> list:
    """Parse MCP tool response into entity list."""
    if not res_txt or not res_txt.strip():
        logger.info("parse_mcp_empty_response", rel=rel_name)
        return []
    
    try:
        parsed = json.loads(res_txt)
    except json.JSONDecodeError as e:
        logger.warning("parse_mcp_json_error", rel=rel_name, error=str(e))
        return []
    
    if isinstance(parsed, list):
        logger.info("parse_mcp_format", rel=rel_name, format="direct_array", count=len(parsed))
        return parsed
    
    if isinstance(parsed, dict):
        if "error" in parsed:
            logger.info("parse_mcp_error_response", rel=rel_name, error=parsed["error"])
            return []
        
        if "data" in parsed:
            data = parsed["data"]
            if isinstance(data, list):
                logger.info("parse_mcp_format", rel=rel_name, format="wrapped_array", count=len(data))
                return data
            elif isinstance(data, dict):
                logger.info("parse_mcp_format", rel=rel_name, format="wrapped_single", count=1)
                return [data]
        
        if rel_name in parsed and isinstance(parsed[rel_name], list):
            logger.info("parse_mcp_format", rel=rel_name, format="relationship_keyed", count=len(parsed[rel_name]))
            return parsed[rel_name]
        
        if "type" in parsed and "id" in parsed:
            logger.info("parse_mcp_format", rel=rel_name, format="single_entity", count=1)
            return [parsed]
        
        for key, value in parsed.items():
            if isinstance(value, list) and len(value) > 0:
                logger.info("parse_mcp_format", rel=rel_name, format="found_array_in_dict", key=key, count=len(value))
                return value
    
    logger.info("parse_mcp_no_data_found", rel=rel_name)
    return []


async def fetch_all_relationships(
    ioc: str, 
    ioc_type: str, 
    rel_tool: str, 
    arg_name: str, 
    priority_rels: list,
    session
) -> tuple[dict, list]:
    """
    PHASE 1: Parallel relationship fetching.
    Uses asyncio.gather to fetch relationships concurrently for high performance.
    Returns: (relationships_data, tool_call_trace)
    """
    logger.info("phase1_start_parallel_fetch", 
                ioc=ioc,
                ioc_type=ioc_type,
                total_relationships=len(priority_rels))
    
    # Concurrency control
    sem = asyncio.Semaphore(10)  # limit concurrent calls
    
    async def fetch_single_relationship(rel_name: str):
        async with sem:
            try:
                # logger.info("phase1_fetching", rel=rel_name) # noisy
                res = await session.call_tool(rel_tool, arguments={
                    arg_name: ioc,
                    "relationship_name": rel_name,
                    "descriptors_only": False,
                    "limit": MAX_ENTITIES_PER_RELATIONSHIP
                })
                
                if not res.content:
                    return {"relationship": rel_name, "status": "empty", "entities_found": 0}, None
                
                res_txt = res.content[0].text
                entities = parse_mcp_tool_response(res_txt, logger, rel_name)
                
                if not entities:
                     return {"relationship": rel_name, "status": "no_entities", "entities_found": 0}, None
                
                filtered_entities = filter_entities_by_severity(entities, rel_name)
                
                if not filtered_entities:
                     return {"relationship": rel_name, "status": "filtered", "entities_found": 0, "before_filter": len(entities)}, None
                
                # Success
                trace = {
                    "relationship": rel_name,
                    "status": "success",
                    "entities_found": len(filtered_entities),
                    "sample_entity": {"id": filtered_entities[0].get("id"), "type": filtered_entities[0].get("type")} if filtered_entities else None
                }
                return trace, (rel_name, filtered_entities)

            except Exception as e:
                logger.warning("phase1_fetch_error", rel=rel_name, error=str(e))
                return {"relationship": rel_name, "status": "error", "error": str(e)}, None

    # Execute all fetches in parallel
    tasks = [fetch_single_relationship(rel) for rel in priority_rels]
    results = await asyncio.gather(*tasks)
    
    # Aggregate results
    relationships_data = {}
    tool_call_trace = []
    total_entities_stored = 0
    
    for trace, data in results:
        tool_call_trace.append(trace)
        if data:
            rel_name, entities = data
            
            # Global Limit Check
            remaining_capacity = MAX_TOTAL_ENTITIES - total_entities_stored
            if remaining_capacity <= 0:
                logger.info("phase1_global_limit_reached", rel=rel_name)
                continue
                
            if len(entities) > remaining_capacity:
                entities = entities[:remaining_capacity]
                
            relationships_data[rel_name] = entities
            total_entities_stored += len(entities)
    
    logger.info("phase1_complete",
                relationships_attempted=len(priority_rels),
                relationships_with_data=len(relationships_data),
                total_entities=total_entities_stored)
    
    return relationships_data, tool_call_trace


def prepare_detailed_context_for_llm(relationships_data: dict) -> dict:
    """
    Prepare rich context for LLM analysis.
    Instead of just counts, provide actual entity details for deeper analysis.
    """
    detailed_context = {}
    
    for rel_name, entities in relationships_data.items():
        detailed_context[rel_name] = {
            "count": len(entities),
            "entities": []
        }
        
        # Provide more detail for analysis
        for entity in entities:
            entity_summary = {
                "id": entity.get("id"),
                "type": entity.get("type"),
            }
            
            attrs = entity.get("attributes", {})
            
            # Add threat assessment if available
            gti_assessment = attrs.get("gti_assessment", {})
            if gti_assessment:
                entity_summary["threat_score"] = gti_assessment.get("threat_score", {}).get("value")
                entity_summary["verdict"] = gti_assessment.get("verdict", {}).get("value")
            
            # Add name/title if available (for collections/campaigns)
            if attrs.get("name"):
                entity_summary["name"] = attrs["name"]
            if attrs.get("title"):
                entity_summary["title"] = attrs["title"]
            
            # Add last analysis stats if available (for files/domains/IPs)
            if attrs.get("last_analysis_stats"):
                entity_summary["malicious_count"] = attrs["last_analysis_stats"].get("malicious", 0)
            
            # Add meaningful context based on type
            if entity.get("type") == "file":
                entity_summary["file_type"] = attrs.get("type_description")
                entity_summary["size"] = attrs.get("size")
            elif entity.get("type") in ["domain", "ip_address"]:
                entity_summary["reputation"] = attrs.get("reputation")
            
            detailed_context[rel_name]["entities"].append(entity_summary)
    
    return detailed_context


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
        temperature=0.0,
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
        
        # Fallback with basic analysis
        return {
            "ioc_type": ioc_type,
            "verdict": triage_data.get("verdict", "Unknown"),
            "confidence": "Low",
            "severity": "Medium",
            "threat_score": triage_data.get("threat_score", "N/A"),
            "executive_summary": f"Analysis of {ioc} found {len(relationships_data)} relationship types with {sum(len(entities) for entities in relationships_data.values())} entities. Further investigation recommended.",
            "key_findings": [
                f"Found {len(entities)} entities in {rel_name}"
                for rel_name, entities in relationships_data.items()
            ],
            "threat_context": {},
            "priority_entities": [],
            "subtasks": [],
            "investigation_notes": "Automated analysis failed. Manual review recommended."
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
    
    try:
        # 2. Get base facts
        logger.info("triage_fetching_base_report")
        base_data = await config["direct_tool"](ioc)
        
        if not base_data or "data" not in base_data:
             logger.warning("triage_direct_api_empty", ioc=ioc)
             base_data = {"id": ioc}
        else:
             base_data = base_data["data"]

        triage_data = extract_triage_data(base_data, config["type"])
        
        # Initialize metadata
        state["metadata"]["risk_level"] = "Assessing..." 
        state["metadata"]["gti_score"] = triage_data["threat_score"] or "N/A"
        state["metadata"]["rich_intel"] = triage_data
        state["metadata"]["rich_intel"]["relationships"] = {}
        
        # ========================================
        # PHASE 1: Deterministic Relationship Fetching
        # ========================================
        async with mcp_manager.get_session("gti") as session:
            relationships_data, tool_call_trace = await fetch_all_relationships(
                ioc=ioc,
                ioc_type=config["type"],
                rel_tool=config["rel_tool"],
                arg_name=config["arg"],
                priority_rels=priority_rels,
                session=session
            )
        
        # Store in state for graph building
        state["metadata"]["rich_intel"]["relationships"] = relationships_data
        state["metadata"]["tool_call_trace"] = tool_call_trace  # For transparency
        
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
            "_llm_reasoning": analysis.get("_llm_reasoning")
        }
        
        # Maintain backward compatibility
        state["metadata"]["rich_intel"]["triage_summary"] = analysis.get("executive_summary")
        state["metadata"]["risk_level"] = analysis.get("verdict", "Unknown")
        
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
        state["metadata"]["risk_level"] = "Error"
        
    return state
