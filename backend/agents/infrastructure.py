import os
import json
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_google_vertexai import ChatVertexAI
from langchain_core.tools import tool

from backend.graph.state import AgentState
from backend.mcp.client import mcp_manager
from backend.utils.logger import get_logger
from backend.utils.graph_cache import InvestigationCache

logger = get_logger("agent_infrastructure")

INFRA_ANALYSIS_PROMPT = """
You are an Elite Network Infrastructure Hunter (V2 Structured Data).

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

**Output (JSON):**
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

**OUTPUT INSTRUCTIONS:**
- Return ONLY valid JSON.
- Do NOT include markdown formatting in the output.
"""

def generate_infrastructure_markdown_report(result: dict, ioc: str) -> str:
    """
    Generates a detailed markdown report for Infrastructure Analysis.
    """
    try:
        md = "## Infrastructure Specialist Analysis\n\n"
        md += f"### Target: `{ioc}`\n\n"
        
        # 1. Verdict & Context
        verdict = result.get("verdict", "Unknown")
        score = result.get("threat_score", "N/A")
        owner = result.get("asn_or_registrar", "Unknown")
        
        icon = "🔴" if str(verdict).lower() == "malicious" else "mod_detect_suspicious" if str(verdict).lower() == "suspicious" else "🟢"
        
        md += f"**Verdict:** {icon} {verdict} (Score: {score})\n"
        md += f"**Owner/ASN:** {owner}\n"
        
        cats = result.get("categories", [])
        if cats:
            md += f"**Categories:** {', '.join(cats)}\n"
        md += "\n"
        
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
    Infrastructure Specialist Agent.
    """
    ioc = state["ioc"]
    logger.info("infra_agent_start", ioc=ioc)
    
    try:
        # Initialize cache from state
        cache = InvestigationCache(state.get("investigation_graph"))
        
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
            
            messages = [
                SystemMessage(content=INFRA_ANALYSIS_PROMPT),
                HumanMessage(content=f"Analyze these targets:\n{json.dumps(unique_targets, indent=2)}")
            ]
            
            # --- Robust Loop (Increased to 7 iterations for comprehensive analysis) ---
            final_content = ""
            max_iterations = 7
            logger.info("infra_agent_loop_start", max_iterations=max_iterations)
            
            for iteration in range(max_iterations):
                logger.info("infra_agent_iteration", iteration=iteration, max_iterations=max_iterations)
                
                if iteration == max_iterations - 1:
                    logger.info("infra_agent_final_iteration", iteration=iteration)
                    messages.append(HumanMessage(content="This is the final iteration. Please provide the comprehensive JSON structure based on the findings gathered so far."))

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
            
            if not final_content and messages:
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                        final_content = msg.content
                        break

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
                
                # Store in State
                if "specialist_results" not in state: state["specialist_results"] = {}
                state["specialist_results"]["infrastructure"] = result
                
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
                                # Link to the SOURCE target that was analyzed (usually unique_targets[0] or root)
                                source_node = unique_targets[0]["value"]
                                cache.add_relationship(source_node, ind_value, "related_infrastructure", {"source": "infrastructure_analysis"})
                                
                                # Sync to Rich Intel for Frontend
                                if "metadata" not in state: state["metadata"] = {}
                                if "rich_intel" not in state["metadata"]: state["metadata"]["rich_intel"] = {}
                                if "relationships" not in state["metadata"]["rich_intel"]: state["metadata"]["rich_intel"]["relationships"] = {}
                                
                                rels_data = state["metadata"]["rich_intel"]["relationships"]
                                rel_name = "related_infrastructure"
                                
                                if rel_name not in rels_data: rels_data[rel_name] = []
                                
                                 # Dedupe
                                exists = any(e.get("id") == ind_value and e.get("source_id") == source_node for e in rels_data[rel_name])
                                if not exists:
                                    rels_data[rel_name].append({
                                        "id": ind_value,
                                        "type": ent_type,
                                        "source_id": source_node,
                                        "attributes": {"infra_context": "related_indicator"}
                                    })
                                    
                    except Exception as e:
                        logger.warning("infra_indicator_parse_error", error=str(e))
                
                # Update Subtask Status
                new_subtasks = []
                for task in state.get("subtasks", []):
                    if task.get("agent") in ["infrastructure_specialist", "infrastructure"]:
                        task["status"] = "completed"
                        task["result_summary"] = result.get("summary")
                    new_subtasks.append(task)
                state["subtasks"] = new_subtasks
                
            except Exception as e:
                logger.error("infra_parsing_error", error=str(e))
                import traceback
                tb = traceback.format_exc()
                state["specialist_results"] = state.get("specialist_results", {})
                state["specialist_results"]["infrastructure"] = {
                    "verdict": "System Error",
                    "summary": f"Failed to parse analysis results: {str(e)}",
                    "markdown_report": f"## Analysis Failed\n\nThe Infrastructure Agent encountered an error while processing the results.\n\n**Error Details:**\n```\n{str(e)}\n```\n\n**Raw Output:**\n```\n{str(final_text)[:2000] if 'final_text' in locals() else str(final_content)[:2000]}\n```"
                }
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
