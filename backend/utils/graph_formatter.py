import json
from backend.utils.logger import get_logger

logger = get_logger("graph-formatter")

def format_investigation_graph(job_id: str, job: dict) -> dict:
    """
    Returns graph data with improved naming conventions for visualization.
    Extracts nodes and edges from job's rich_intel and subtasks.
    """
    
    logger.info("graph_request", job_id=job_id)
    
    ioc = job.get("ioc", "Unknown")
    ioc_type = job.get("ioc_type", "Unknown")
    subtasks = job.get("subtasks", [])
    rich_intel = job.get("rich_intel", {})
    
    # 1. Central Node (The IOC) with better label
    root_label = ioc
    if ioc_type == "File":
        root_label = f"File: {ioc}"
    elif ioc_type == "IP":
        root_label = f"IP: {ioc}"
    elif ioc_type == "Domain":
        root_label = f"Domain: {ioc}"
    elif ioc_type == "URL":
        root_label = f"URL: {ioc}" if len(ioc) < 64 else f"URL: {ioc[:60]}..."
    
    root_id = ioc
    nodes = [
        {
            "id": root_id, 
            "label": root_label, 
            "color": "#FF4B4B",  # Red for IOC
            "size": 35,
            "title": f"IOC: {ioc}\nType: {ioc_type}",
            "isRoot": True
        }
    ]
    edges = []
    
    # Track existing nodes to prevent dups and enable merging
    node_registry = set([root_id]) 
    edge_registry = set() # Track edges to prevent dups: (source, target, label)

    # Note: Agent subtasks are NOT added to graph - only IOC relationships
    logger.info("graph_config", agent_nodes_disabled=True, reason="only_show_ioc_relationships")
    
    # 3. Relationship Nodes with Visual Enhancements
    relationships = rich_intel.get("relationships", {})
    
    # Exclude non-graph relationships
    EXCLUDE_RELATIONSHIPS = ["attack_techniques", "malware_families", "associations", "campaigns", "related_threat_actors"]
    filtered_relationships = {
        k: v for k, v in relationships.items() 
        if k not in EXCLUDE_RELATIONSHIPS and v
    }
    
    logger.info("graph_building", 
                total_rels=len(relationships),
                showing_rels=len(filtered_relationships))

    # Helper: Entity Labeler
    def get_entity_label(entity: dict) -> str:
        ent_type = entity.get("type", "unknown")
        ent_id = entity.get("id", "unknown")
        attrs = entity.get("attributes", {})
        
        if ent_type == "url":
            # 1. Try attributes.last_final_url (Best)
            if attrs.get("last_final_url"):
                return attrs.get("last_final_url")

            # 2. Try attributes.url
            if attrs.get("url"):
                return attrs.get("url")
            
            # 3. Try context_attributes (Backup)
            context_attrs = entity.get("context_attributes", {})
            if context_attrs.get("url"):
                return context_attrs.get("url")
            
            # 4. Fallback: Full ID (Hash)
            return ent_id
            
        elif ent_type == "file":
            # Format: Full SHA256\n(truncated_filename.ext)
            
            # 1. meaningful_name
            name = attrs.get("meaningful_name")
            
            # 2. names list (take first)
            if not name and attrs.get("names"):
                name = attrs.get("names")[0]
                
            if name:
                # Smart truncation: Keep first 24 chars + extension
                import os
                base, ext = os.path.splitext(name)
                if len(base) > 48:
                    # Truncate to 48 chars, keep extension
                    truncated = base[:48] + "..." + ext
                else:
                    truncated = name
                return f"{ent_id}\n({truncated})"  # Full hash + truncated filename
            
            return ent_id  # Full hash if no filename
            
        elif ent_type == "domain":
            return attrs.get("host_name", ent_id)
            
        elif ent_type == "ip_address":
            return ent_id
            
        return ent_id  # Default: show full ID

    # Process Relationships with clustering and source awareness
    for rel_type, entities in filtered_relationships.items():
        logger.info("graph_processing_relationship", 
                   rel_type=rel_type, 
                   entity_count=len(entities))
        
        # Add entities (limit to 15 to prevent graph overload)
        display_entities = entities[:15]
        
        # Group entities by source to allow accurate clustering
        sources = {}
        for entity in display_entities:
            s_id = entity.get("source_id", root_id)
            if s_id not in sources: sources[s_id] = []
            sources[s_id].append(entity)

        for s_id, s_entities in sources.items():
            use_clustering = len(s_entities) > 2 # Cluster if source has many of same relationship
            target_source_id = s_id
            
            if use_clustering:
                group_id = f"group_{s_id}_{rel_type}"
                group_label = rel_type.replace("_", " ").title()
                
                if group_id not in node_registry:
                    nodes.append({
                        "id": group_id,
                        "label": group_label,
                        "color": "#2C3E50",
                        "size": 25,
                        "shape": "box",
                        "title": f"{group_label}\n{len(s_entities)} entities from {s_id}"
                    })
                    node_registry.add(group_id)
                    
                    # Link group to source
                    edge_key = (s_id, group_id, "")
                    if edge_key not in edge_registry and s_id != group_id:
                        edges.append({"source": s_id, "target": group_id, "label": ""})
                        edge_registry.add(edge_key)
                
                target_source_id = group_id

            for entity in s_entities:
                ent_id = entity.get("id")
                if not ent_id or ent_id == s_id: continue
                
                ent_type = entity.get("type", "unknown")
                
                # Add node if it doesn't exist
                if ent_id not in node_registry:
                    # Color Palette
                    color_map = {
                        "file": "#9B59B6", "domain": "#E67E22", "ip_address": "#E67E22", "url": "#2ECC71", "collection": "#3498DB"
                    }
                    color = color_map.get(ent_type, "#95A5A6")
                    
                    # Build human-readable mouseover tooltip
                    attrs = entity.get("attributes", {})
                    tooltip_lines = []
                    
                    # 0. Specialist Context (High Visibility)
                    specialist_ctx = attrs.get("malware_context") or entity.get("malware_context") or \
                                   attrs.get("infra_context") or entity.get("infra_context")
                                   
                    if specialist_ctx:
                        ctx_label = specialist_ctx.replace("_", " ").title()
                        tooltip_lines.append(f"🚩 Specialist Finding: {ctx_label}")

                    # 1. Threat Score
                    score = attrs.get("threat_score") or entity.get("threat_score")
                    if score:
                        tooltip_lines.append(f"Threat Score: {score}")
                    
                    # 2. Vendor Detections
                    m_count = attrs.get("malicious_count") or entity.get("malicious_count")
                    if m_count:
                        tooltip_lines.append(f"{m_count} vendor{'s' if m_count != 1 else ''} detected as malicious")
                    
                    # 3. File-specific info
                    if ent_type == "file":
                        fname = attrs.get("meaningful_name") or entity.get("meaningful_name")
                        if not fname and (attrs.get("names") or entity.get("names")):
                            names = attrs.get("names") or entity.get("names")
                            fname = names[0]
                        if fname:
                            tooltip_lines.append(f"Filename: {fname}")
                        
                        f_type = attrs.get("file_type") or entity.get("file_type")
                        if f_type:
                            tooltip_lines.append(f"Type: {f_type}")
                        
                        size = attrs.get("size") or entity.get("size")
                        if size:
                            size_mb = size / (1024 * 1024)
                            tooltip_lines.append(f"Size: {size_mb:.2f} MB")
                    
                    # 4. URL categories
                    elif ent_type == "url":
                        cats = attrs.get("categories") or entity.get("categories")
                        if cats:
                            if isinstance(cats, dict):
                                cat_list = ", ".join(cats.values())
                            else:
                                cat_list = ", ".join(cats) if isinstance(cats, list) else str(cats)
                            tooltip_lines.append(f"Categories: {cat_list}")
                    
                    # 5. Verdict
                    verdict = attrs.get("verdict") or entity.get("verdict")
                    if verdict:
                        tooltip_lines.append(f"Verdict: {verdict}")
                    
                    tooltip_text = "\n".join(tooltip_lines) if tooltip_lines else f"{ent_type.title()}: {ent_id}"
                    
                    nodes.append({
                        "id": ent_id,
                        "label": get_entity_label(entity),
                        "color": color,
                        "size": 20,
                        "title": tooltip_text
                    })
                    node_registry.add(ent_id)

                # Always add edge unless it exists
                rel_label = "" if use_clustering else rel_type.replace("_", " ")
                edge_key = (target_source_id, ent_id, rel_label)
                if edge_key not in edge_registry:
                    edges.append({
                        "source": target_source_id,
                        "target": ent_id,
                        "label": rel_label
                    })
                    edge_registry.add(edge_key)
        
        # If truncated, add "+X more" indicator node
        if len(entities) > 15:
            remaining = len(entities) - 15
            overflow_id = f"overflow_{rel_type}"
            
            nodes.append({
                "id": overflow_id,
                "label": f"+{remaining} more",
                "color": "#BDC3C7",  # Light grey
                "size": 15,
                "shape": "box",
                "title": f"{remaining} additional {rel_type} entities not shown"
            })
            
            edges.append({
                "source": root_id, # Default to root for general overflows
                "target": overflow_id,
                "label": "",
                "dashes": True
            })

    return {"nodes": nodes, "edges": edges}
