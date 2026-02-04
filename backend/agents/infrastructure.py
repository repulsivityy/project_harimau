import os
import json
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_google_vertexai import ChatVertexAI
from langchain_core.tools import tool

from backend.graph.state import AgentState
from backend.mcp.client import mcp_manager
from backend.utils.logger import get_logger
from backend.utils.graph_cache import InvestigationCache

## Global Variables
infra_iterations = 10 #number of iterations the infra agent goes through per set of investigation

logger = get_logger("agent_infrastructure")

INFRA_ANALYSIS_PROMPT = """
You are an Elite Network Infrastructure Hunter.

**Role:**
You are a threat intelligence analyst specializing in pivoting across adversary infrastructure. You trace the connections between domains, IPs, and URLs to map out the attacker's footprint.

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

**Example Output (JSON):**
{
    "verdict": "Malicious|Suspicious|Benign",
    "threat_score": 85,
    "categories": ["Phishing", "Botnet"],
    "asn_or_registrar": "NameCheap / AS12345 Cloudflare",
    "associated_campaigns": ["Campaign X", "APT29"],
    "pivot_findings": [
        "Resolved to 1.2.3.4 (also hosts malicious.com)",
        "Subdomain admin.evil.com used for C2",
        "Hosted file hash 9f8a... (Ransomware)"
    ],
    "related_indicators": ["IP: 1.2.3.4", "Domain: malicious.com", "File: 9f8a..."],
    "summary": "Detailed technical summary of the infrastructure and its role in the attack..."
}

**CRITICAL OUTPUT INSTRUCTIONS:**
- You MUST ALWAYS return valid JSON in the exact format shown above.
- Do NOT include markdown formatting, code blocks, or explanatory text.
- **IF TOOLS FAIL OR ERROR:** Still return JSON! Use "Unknown", empty arrays [], or "N/A" for fields you couldn't populate.
- **NEVER provide narrative explanations instead of JSON.** If you encountered errors, mention them in the "summary" field.
- When you're done analyzing, respond with ONLY the JSON object - nothing else.

**Example when tools fail:**
{
    "verdict": "Unknown",
    "threat_score": 0,
    "categories": [],
    "asn_or_registrar": "Unknown",
    "associated_campaigns": [],
    "pivot_findings": ["Unable to fetch subdomains due to tool error"],
    "related_indicators": [],
    "summary": "Analysis incomplete due to tool errors. Based on available data: [describe what you know]"
}
"""

def generate_infrastructure_markdown_report(result: dict, ioc: str) -> str:
    """
    Generates a detailed markdown report for Infrastructure Analysis.
    """
    try:
        md = "## Infrastructure Specialist Analysis\n\n"
        #md += f"### Target: `{ioc}`\n\n"
        
        # 1. Verdict & Context
        #verdict = result.get("verdict", "Unknown")
        #score = result.get("threat_score", "N/A")
        #owner = result.get("asn_or_registrar", "Unknown")
        
        #icon = "🔴" if str(verdict).lower() == "malicious" else "🟡" if str(verdict).lower() == "suspicious" else "🟢"
        
        #md += f"**Verdict:** {icon} {verdict} (Score: {score})\n"
        #md += f"**Owner/ASN:** {owner}\n"
        
        #cats = result.get("categories", [])
        #if cats:
        #    md += f"**Categories:** {', '.join(cats)}\n"
        #md += "\n"
        
        # 2. Executive Summary
        md += "### Executive Summary\n"
        md += f"{result.get('summary', 'No summary provided.')}\n\n"
        
        # 3. Pivot Findings
        pivots = result.get("pivot_findings", [])
        if pivots:
            md += "### 🔍 Pivot Findings\n"
            for p in pivots:
                md += f"*   {p}\n"
            md += "\n"
            
        # 4. Campaigns/Actors
        campaigns = result.get("associated_campaigns", [])
        if campaigns:
            md += "### 🏴 Associated Campaigns\n"
            for c in campaigns:
                md += f"*   {c}\n"
            md += "\n"
            
        # 5. Related Indicators (Table)
        indicators = result.get("related_indicators", [])
        if indicators:
            md += "### 🌐 Related Infrastructure\n"
            for ind in indicators:
                 md += f"*   `{ind}`\n"
        
        return md
    except Exception as e:
        return f"Error generating infrastructure report: {str(e)}"

async def infrastructure_node(state: AgentState):
    """
    Infrastructure Specialist Agent (Iterative & Graph-Aware).
    Now includes: Triage context reading + Relationship expansion.
    """
    ioc = state["ioc"]
    logger.info("infra_agent_start", ioc=ioc)
    
    try:
        # Initialize cache from state
        cache = InvestigationCache(state.get("investigation_graph"))
        cache_stats_before = cache.get_stats()
        logger.info("infra_cache_loaded", stats=cache_stats_before)
        
        # [NEW] Retrieve Triage Context
        triage_context = state.get("metadata", {}).get("rich_intel", {}).get("triage_analysis", {})
        triage_summary = triage_context.get("executive_summary", "No triage summary available.")
        key_findings = triage_context.get("key_findings", [])
        logger.info("infra_triage_context_loaded", 
                   has_summary=bool(triage_summary), 
                   findings_count=len(key_findings))
        
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_REGION", "asia-southeast1")

        # --- Identify Targets ---
        # Primary logic: if IOC is IP/Domain/URL or if explicitly tasked
        targets = []
        
        # 1. Check Root
        import re
        # Simple heuristics
        is_ip = re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ioc)
        is_domain = not is_ip and "." in ioc and "http" not in ioc
        is_url = "http" in ioc
        
        if is_ip or is_domain or is_url:
            targets.append({"type": "root", "value": ioc})
            
        # 2. Check Subtasks (with Regex Fallback)
        for task in state.get("subtasks", []):
            if task.get("agent") in ["infrastructure_specialist", "infrastructure"]:
                val = task.get("entity_id")
                
                # Fallback: Extract from task description if missing
                if not val and task.get("task"):
                    task_text = task.get("task")
                    # Try IP
                    ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", task_text)
                    if ip_match: val = ip_match.group(0)
                    # Try URL (simple)
                    elif "http" in task_text:
                        url_match = re.search(r"https?://[^\s]+", task_text)
                        if url_match: val = url_match.group(0)
                    # Try Domain (very basic, avoid common words)
                    elif "." in task_text:
                         dom_match = re.search(r"\b([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b", task_text)
                         if dom_match and dom_match.group(1) not in ["e.g", "i.e"]: val = dom_match.group(1)

                if val:
                    targets.append({
                        "type": "subtask", 
                        "value": val,
                        "context": task.get("context")
                    })
                
        # Deduplicate
        unique_targets = []
        seen = set()
        for t in targets:
            if t["value"] and t["value"] not in seen:
                unique_targets.append(t)
                seen.add(t["value"])
                
        # Limit
        unique_targets = unique_targets[:3]
        logger.info("infra_targets_identified", count=len(unique_targets))
        
        if not unique_targets:
            logger.warning("infra_no_targets_found")
            return state

        # --- Define Tools ---
        async with mcp_manager.get_session("gti") as session:
            
            # Domain Tools
            @tool
            async def get_domain_report(domain: str):
                """Get threat report for a domain."""
                try: 
                    res = await session.call_tool("get_domain_report", arguments={"domain": domain})
                    return res.content[0].text if res.content else "{}"
                except Exception as e: return str(e)

            @tool
            async def get_entities_related_to_a_domain(domain: str, relationship: str):
                """Get entities related to a domain. Relationships: resolutions, subdomains, communicating_files."""
                try:
                    res = await session.call_tool("get_entities_related_to_a_domain", arguments={"domain": domain, "relationship_name": relationship, "descriptors_only": True})
                    return res.content[0].text if res.content else "[]"
                except Exception as e: return str(e)
                
            # IP Tools
            @tool
            async def get_ip_address_report(ip_address: str):
                """Get threat report for an IP address."""
                try: 
                    res = await session.call_tool("get_ip_address_report", arguments={"ip_address": ip_address})
                    return res.content[0].text if res.content else "{}"
                except Exception as e: return str(e)

            @tool
            async def get_entities_related_to_an_ip_address(ip_address: str, relationship: str):
                """Get entities related to an IP. Relationships: resolutions, communicating_files, referrer_files."""
                try:
                    res = await session.call_tool("get_entities_related_to_an_ip_address", arguments={"ip_address": ip_address, "relationship_name": relationship, "descriptors_only": True})
                    return res.content[0].text if res.content else "[]"
                except Exception as e: return str(e)

            # URL Tools
            @tool
            async def get_url_report(url: str):
                """Get threat report for a URL."""
                try: 
                    res = await session.call_tool("get_url_report", arguments={"url": url})
                    return res.content[0].text if res.content else "{}"
                except Exception as e: return str(e)

            @tool
            async def get_entities_related_to_an_url(url: str, relationship: str):
                """Get entities related to a URL. Relationships: downloaded_files, network_location."""
                try:
                    res = await session.call_tool("get_entities_related_to_an_url", arguments={"url": url, "relationship_name": relationship, "descriptors_only": True})
                    return res.content[0].text if res.content else "[]"
                except Exception as e: return str(e)

            # Build LLM
            tools = [
                get_domain_report, get_entities_related_to_a_domain,
                get_ip_address_report, get_entities_related_to_an_ip_address,
                get_url_report, get_entities_related_to_an_url
            ]
            
            llm = ChatVertexAI(model="gemini-2.5-flash", temperature=0.0, project=project_id, location=location).bind_tools(tools)
            
            # [NEW] Format Triage Context for LLM
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
            for task in state.get("subtasks", []):
                if task.get("agent") in ["infrastructure_specialist", "infrastructure"]:
                    context += f"- Task: {task.get('task')}\n"
                    context += f"- Context: {task.get('context')}\n"
            
            messages = [
                SystemMessage(content=INFRA_ANALYSIS_PROMPT),
                HumanMessage(content=f"""
{triage_context_str}

**YOUR ASSIGNMENT:**
Analyze the following infrastructure indicators based on the triage context above:
{json.dumps(unique_targets, indent=2)}

**SPECIFIC INSTRUCTIONS:**
{context if context else "Perform comprehensive infrastructure analysis."}
                """)
            ]
            
            # --- Robust Loop (Increased to 7 iterations for comprehensive analysis) ---
            final_content = ""
            max_iterations = infra_iterations
            logger.info("infra_agent_loop_start", max_iterations=max_iterations)
            
            for iteration in range(max_iterations):
                logger.info("infra_agent_iteration", iteration=iteration, max_iterations=max_iterations)
                
                if iteration == max_iterations - 1:
                    logger.info("infra_agent_final_iteration", iteration=iteration)
                    messages.append(HumanMessage(content="This is the FINAL iteration. You MUST stop using tools now.\n\nBased on all the information you've gathered, provide your comprehensive analysis in valid JSON format.\n\nDo NOT make any more tool calls. Return ONLY the JSON structure as specified in the system prompt.\n\nIf you don't have enough information, provide your best analysis based on what you've gathered so far."))

                response = await llm.ainvoke(messages)
                messages.append(response)
                
                if response.tool_calls:
                    logger.info("infra_agent_tool_calls", iteration=iteration, num_tools=len(response.tool_calls), tools=[tc["name"] for tc in response.tool_calls])
                    for tc in response.tool_calls:
                        tool_name = tc["name"]
                        args = tc["args"]
                        logger.info("infra_invoking_tool", iteration=iteration, tool=tool_name, args=args)
                        
                        # Invoke the right tool
                        result_txt = ""
                        if tool_name == "get_domain_report": result_txt = await get_domain_report.ainvoke(args)
                        elif tool_name == "get_entities_related_to_a_domain": result_txt = await get_entities_related_to_a_domain.ainvoke(args)
                        elif tool_name == "get_ip_address_report": result_txt = await get_ip_address_report.ainvoke(args)
                        elif tool_name == "get_entities_related_to_an_ip_address": result_txt = await get_entities_related_to_an_ip_address.ainvoke(args)
                        elif tool_name == "get_url_report": result_txt = await get_url_report.ainvoke(args)
                        elif tool_name == "get_entities_related_to_an_url": result_txt = await get_entities_related_to_an_url.ainvoke(args)
                        else:
                            result_txt = f"Error: Tool {tool_name} not found"
                            logger.warning("infra_unknown_tool", tool=tool_name)
                        
                        messages.append(ToolMessage(content=result_txt, tool_call_id=tc["id"]))
                        logger.info("infra_tool_response", iteration=iteration, tool=tool_name, response_length=len(result_txt))
                else:
                    logger.info("infra_agent_no_tools", iteration=iteration, has_content=bool(response.content))
                    final_content = response.content
                    if final_content: break
            
            # Enhanced fallback logic with detailed logging
            if not final_content and messages:
                logger.warning("infra_no_final_content_using_fallback", total_messages=len(messages))
                
                # Strategy 1: Find AIMessage with content but NO tool_calls (preferred)
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                        final_content = msg.content
                        logger.info("infra_fallback_strategy_1", found=True)
                        break
                
                # Strategy 2: If still empty, accept ANY AIMessage with content (even if it has tool_calls)
                if not final_content:
                    logger.warning("infra_fallback_strategy_2_trying")
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage) and msg.content:
                            final_content = msg.content
                            logger.info("infra_fallback_strategy_2", found=True, had_tool_calls=bool(msg.tool_calls))
                            break
                
                # Log final status
                if not final_content:
                    logger.error("infra_fallback_failed", ai_message_count=sum(1 for m in messages if isinstance(m, AIMessage)))

            # --- Parsing & Reporting ---
            try:
                # Handle potential list of content blocks (Gemini/Vertex)
                if isinstance(final_content, list):
                    # Extract text from list of dicts or strings
                    text_parts = []
                    for block in final_content:
                        if isinstance(block, dict):
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                        else:
                            text_parts.append(str(block))
                    final_text = "".join(text_parts).strip()
                else:
                    final_text = str(final_content or "").strip()

                if not final_text:
                    raise ValueError("LLM returned empty content.")

                # Clean markdown
                clean_content = final_text
                if "```json" in clean_content:
                    clean_content = clean_content.split("```json")[-1].split("```")[0].strip()
                elif "```" in clean_content:
                    clean_content = clean_content.split("```")[1].strip() if clean_content.count("```") >= 2 else clean_content
                
                # Try to detect if it's an array or object
                array_start = clean_content.find("[")
                object_start = clean_content.find("{")
                
                # Determine if we have an array or object (whichever comes first)
                if array_start != -1 and (object_start == -1 or array_start < object_start):
                    # It's a JSON array
                    end_idx = clean_content.rfind("]")
                    if end_idx != -1:
                        clean_content = clean_content[array_start:end_idx+1]
                        # Parse array and take first element
                        parsed = json.loads(clean_content)
                        if isinstance(parsed, list) and len(parsed) > 0:
                            result = parsed[0]
                        else:
                            raise ValueError(f"JSON array is empty or invalid")
                    else:
                        raise ValueError(f"No closing bracket found for JSON array")
                elif object_start != -1:
                    # It's a JSON object
                    end_idx = clean_content.rfind("}")
                    if end_idx != -1:
                        clean_content = clean_content[object_start:end_idx+1]
                        result = json.loads(clean_content)
                    else:
                        raise ValueError(f"No closing brace found for JSON object")
                else:
                    # No JSON structure found
                    raise ValueError(f"No JSON structure found in LLM output. Content starts with: {final_text[:100]}")

                
                # Generate Report
                result["markdown_report"] = generate_infrastructure_markdown_report(result, ioc)
                
                # --- Graph Population (Related Indicators) ---
                related = result.get("related_indicators", [])
                for ind in related:
                    try:
                        # "IP: 1.2.3.4" -> type=ip_address, value=1.2.3.4
                        parts = ind.split(":", 1)
                        if len(parts) == 2:
                            ind_type_raw = parts[0].strip().lower()
                            ind_value = parts[1].strip()
                            
                            ent_type = "unknown"
                            if "ip" in ind_type_raw: ent_type = "ip_address"
                            elif "domain" in ind_type_raw: ent_type = "domain"
                            elif "file" in ind_type_raw: ent_type = "file"
                            
                            if ent_type != "unknown":
                                # Add to NetworkX Cache
                                cache.add_entity(ind_value, ent_type, {"infra_context": "related_indicator"})
                                # Link to the SOURCE target that was analyzed
                                source_node = unique_targets[0]["value"]
                                cache.add_relationship(source_node, ind_value, "related_infrastructure", {"source": "infrastructure_analysis"})
                    except Exception as e:
                        logger.warning("infra_indicator_parse_error", error=str(e))
                
                # [NEW] RELATIONSHIP EXPANSION
                # For each analyzed entity, fetch its relationships and expand the graph
                from backend.tools import gti
                import re
                
                for target in unique_targets:
                    target_value = target["value"]
                    logger.info("infra_expanding_relationships", target=target_value)
                    
                    try:
                        # Determine entity type and fetch appropriate relationships
                        is_ip = re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", target_value)
                        is_url = "http" in target_value
                        is_domain = not is_ip and not is_url and "." in target_value
                        
                        rel_data = None
                        
                        if is_ip:
                            # Fetch IP relationships
                            rel_data = await gti.get_ip_address_report(
                                target_value,
                                relationships=["resolutions", "communicating_files", "downloaded_files"]
                            )
                        elif is_domain:
                            # Fetch domain relationships
                            rel_data = await gti.get_domain_report(
                                target_value,
                                relationships=["resolutions", "subdomains", "communicating_files", "downloaded_files"]
                            )
                        elif is_url:
                            # Fetch URL relationships
                            rel_data = await gti.get_url_report(
                                target_value,
                                relationships=["network_location", "downloaded_files", "contacted_domains", "contacted_ips"]
                            )
                        
                        if rel_data and "data" in rel_data:
                            raw_rels = rel_data["data"].get("relationships", {})
                            new_entities_count = 0
                            
                            for rel_name, rel_content in raw_rels.items():
                                entities = rel_content.get("data", [])
                                for entity in entities:
                                    entity_id = entity.get("id")
                                    entity_type = entity.get("type")
                                    entity_attrs = entity.get("attributes", {})
                                    
                                    # Add to cache
                                    cache.add_entity(
                                        entity_id=entity_id,
                                        entity_type=entity_type,
                                        attributes=entity_attrs
                                    )
                                    cache.add_relationship(target_value, entity_id, rel_name)
                                    new_entities_count += 1
                            
                            logger.info("infra_graph_expanded", 
                                       target=target_value, 
                                       new_entities=new_entities_count,
                                       relationships=list(raw_rels.keys()))
                    except Exception as expand_err:
                        logger.error("infra_expansion_error", target=target_value, error=str(expand_err))
                
                # [NEW] Mark all analyzed targets as investigated (for Lead Hunter tracking)
                for target_info in unique_targets:
                    cache.mark_as_investigated(target_info["value"], "infrastructure")
                    logger.info("infra_marked_investigated", entity=target_info["value"])
                
                # Persist expanded graph back to state
                state["investigation_graph"] = cache.graph
                cache_stats_after = cache.get_stats()
                logger.info("infra_graph_updated", 
                           before=cache_stats_before, 
                           after=cache_stats_after)
                
                # --- SYNC CACHE TO STATE (Frontend Graph Visibility) ---
                # Ensure structure exists
                if "metadata" not in state: 
                    state["metadata"] = {}
                if "rich_intel" not in state["metadata"]: 
                    state["metadata"]["rich_intel"] = {}
                if "relationships" not in state["metadata"]["rich_intel"]: 
                    state["metadata"]["rich_intel"]["relationships"] = {}
                
                relationships_data = state["metadata"]["rich_intel"]["relationships"]
                
                def push_to_rich_intel(rel_name, entity_type, value, source_id, attributes={}):
                    if rel_name not in relationships_data:
                        relationships_data[rel_name] = []
                    
                    # Avoid duplicates
                    exists = any(
                        e.get("id") == value and e.get("source_id") == source_id 
                        for e in relationships_data[rel_name]
                    )
                    if not exists:
                        relationships_data[rel_name].append({
                            "id": value,
                            "type": entity_type,
                            "source_id": source_id,
                            "attributes": attributes
                        })
                
                # Sync related indicators from infrastructure analysis
                for indicator in result.get("related_indicators", []):
                    try:
                        # Parse "IP: 1.2.3.4" or "Domain: evil.com"
                        parts = indicator.split(":", 1)
                        if len(parts) == 2:
                            ind_type_raw = parts[0].strip().lower()
                            ind_value = parts[1].strip()
                            
                            entity_type = "unknown"
                            if "ip" in ind_type_raw: 
                                entity_type = "ip_address"
                            elif "domain" in ind_type_raw: 
                                entity_type = "domain"
                            elif "url" in ind_type_raw:
                                entity_type = "url"
                            elif "file" in ind_type_raw:
                                entity_type = "file"
                            
                            if entity_type != "unknown":
                                # Get primary target for source_id
                                primary_target = unique_targets[0]["value"] if unique_targets else ioc
                                
                                # Infrastructure relationships
                                push_to_rich_intel(
                                    "related_infrastructure", 
                                    entity_type, 
                                    ind_value, 
                                    primary_target,
                                    {"infra_context": "related_indicator"}
                                )
                    except (KeyError, ValueError, IndexError, TypeError) as e:
                        logger.warning("infra_indicator_parse_failed", 
                                     indicator=ind.get("id", "unknown") if isinstance(ind, dict) else str(ind)[:50],
                                     error=str(e))
                        pass
                
                # [RACE CONDITION FIX] Do not update final_report here.
                # Lead Hunter will assemble it to avoid race conditions.

                
                # Update Subtask Status
                new_subtasks = []
                for task in state.get("subtasks", []):
                    if task.get("agent") in ["infrastructure_specialist", "infrastructure"]:
                        task["status"] = "completed"
                        task["result_summary"] = result.get("summary")
                    new_subtasks.append(task)
                state["subtasks"] = new_subtasks
                
                logger.info("infra_agent_success", verdict=result.get("verdict"))
            except Exception as e:
                logger.error("infra_parsing_error", error=str(e))
                import traceback
                tb = traceback.format_exc()
                result = {
                    "verdict": "System Error",
                    "summary": f"Failed to parse analysis results: {str(e)}",
                    "markdown_report": f"## Analysis Failed\n\nThe Infrastructure Agent encountered an error while processing the results.\n\n**Error Details:**\n```\n{str(e)}\n```\n\n**Raw Output:**\n```\n{str(final_text)[:2000] if 'final_text' in locals() else str(final_content)[:2000]}\n```"
                }
    except Exception as e:
        logger.error("infra_node_fatal_error", error=str(e))
        import traceback
        tb = traceback.format_exc()
        result = {
            "verdict": "System Error",
            "summary": f"Fatal error in Infrastructure Specialist: {str(e)}",
            "markdown_report": f"## System Error\n\nThe Infrastructure Specialist encountered a fatal error.\n\n### Error Details\n```\n{str(e)}\n```\n\n### Traceback\n```\n{tb}\n```"
        }
    
    # Consolidated State Update - Single source of truth
    if "specialist_results" not in state:
        state["specialist_results"] = {}
    state["specialist_results"]["infrastructure"] = result
    
    return state
