import os
from backend.utils.logger import get_logger
from backend.utils.entity_identity import normalise_entity_id

logger = get_logger("graph-formatter")


def format_graph_from_cache(job_id: str, job: dict) -> dict:
    """
    Build frontend graph data from the persisted NetworkX investigation_graph.

    Reads the full GTI attribute set and specialist provenance stored in
    InvestigationCache (`investigation_graph` JSONB column). When called while a
    job is still running (before `investigation_graph` is persisted), returns a
    single-node seed graph for the root IOC.
    """
    from backend.utils.graph_cache import InvestigationCache, normalize_verdict

    ioc = job.get("ioc", "Unknown")
    ioc_type = job.get("ioc_type", "Unknown")

    graph_data = job.get("investigation_graph")
    if not graph_data:
        if ioc_type == "URL":
            root_label = f"URL: {ioc}" if len(ioc) < 64 else f"URL: {ioc[:60]}..."
        elif ioc_type in ("File", "IP", "Domain"):
            root_label = f"{ioc_type}: {ioc}"
        else:
            root_label = ioc
        return {
            "nodes": [
                {
                    "id": ioc,
                    "label": root_label,
                    "color": "#FF4B4B",
                    "size": 35,
                    "title": f"IOC: {ioc}\nType: {ioc_type}",
                    "isRoot": True,
                    "inReport": True,
                }
            ],
            "edges": [],
        }

    norm_ioc = normalise_entity_id(ioc)

    cache = InvestigationCache(graph_data)
    stats = cache.get_stats()
    logger.info("graph_from_cache", job_id=job_id,
                nodes=stats["nodes"], edges=stats["edges"])

    COLOR_MAP = {
        "file":       "#9B59B6",  # Purple
        "domain":     "#E67E22",  # Orange
        "ip_address": "#3498DB",  # Blue (differentiated from domain)
        "url":        "#2ECC71",  # Green
        "collection": "#F39C12",  # Amber
    }

    nodes = []
    edges = []
    included_node_ids = set()
    edge_registry: set = set()

    for node_id, data in cache.graph.nodes(data=True):
        etype = data.get("entity_type", "unknown")
        is_root = (normalise_entity_id(node_id, data.get("entity_type")) == norm_ioc)

        # ── Label ──────────────────────────────────────────────────────────
        if is_root:
            if ioc_type == "URL":
                label = f"URL: {ioc}" if len(ioc) < 64 else f"URL: {ioc[:60]}..."
            elif ioc_type in ("File", "IP", "Domain"):
                label = f"{ioc_type}: {ioc}"
            else:
                label = ioc
        elif etype == "domain":
            label = data.get("host_name", node_id)
        elif etype == "ip_address":
            label = node_id
        elif etype == "url":
            label = data.get("last_final_url") or data.get("url") or node_id
        elif etype == "file":
            name = data.get("meaningful_name") or (data.get("names") or [None])[0]
            if name:
                base, ext = os.path.splitext(name)
                truncated = (base[:48] + "..." + ext) if len(base) > 48 else name
                label = f"{node_id}\n({truncated})"
            else:
                label = node_id
        else:
            label = data.get("name") or data.get("title") or node_id

        # ── Threat fields from raw GTI attribute structure ─────────────────
        gti_raw = data.get("gti_assessment")
        gti = gti_raw if isinstance(gti_raw, dict) else {}
        verdict_raw = gti.get("verdict") or {}
        verdict = verdict_raw.get("value") if isinstance(verdict_raw, dict) else None
        score_raw = gti.get("threat_score") or {}
        threat_score = score_raw.get("value") if isinstance(score_raw, dict) else None
        analysis_stats = data.get("last_analysis_stats") or {}
        malicious_count = analysis_stats.get("malicious", 0) if isinstance(analysis_stats, dict) else 0

        # ── Tooltip ────────────────────────────────────────────────────────
        if is_root:
            tooltip = f"IOC: {ioc}\nType: {ioc_type}"
        else:
            lines = []
            specialist_ctx = data.get("malware_context") or data.get("infra_context")
            if specialist_ctx:
                lines.append(f"🚩 Specialist Finding: {specialist_ctx.replace('_', ' ').title()}")
            if threat_score:
                lines.append(f"Threat Score: {threat_score}")
            if malicious_count:
                s = "s" if malicious_count != 1 else ""
                lines.append(f"{malicious_count} vendor{s} detected as malicious")
            if etype == "file":
                fname = data.get("meaningful_name") or (data.get("names") or [None])[0]
                if fname:
                    lines.append(f"Filename: {fname}")
                ftype = data.get("type_description")
                if ftype:
                    lines.append(f"Type: {ftype}")
                fsize = data.get("size")
                if fsize:
                    lines.append(f"Size: {fsize / (1024 * 1024):.2f} MB")
            elif etype == "url":
                cats = data.get("categories")
                if cats:
                    if isinstance(cats, dict):
                        cat_list = ", ".join(cats.values())
                    elif isinstance(cats, list):
                        cat_list = ", ".join(cats)
                    else:
                        cat_list = str(cats)
                    lines.append(f"Categories: {cat_list}")
            if verdict:
                lines.append(f"Verdict: {verdict}")
            tooltip = "\n".join(lines) if lines else f"{etype.title()}: {node_id}"

        # ── isMalicious ────────────────────────────────────────────────────
        is_malicious = bool(
            (malicious_count and malicious_count > 0)
            or (normalize_verdict(verdict) == "malicious")
            or (threat_score and isinstance(threat_score, (int, float)) and threat_score >= 70)
        )

        # ── Relevance Filter ───────────────────────────────────────────────
        specialist_results = job.get("specialist_results", {})
        lead_report = job.get("lead_hunter_report", "")
        full_report_text = f"{specialist_results} {lead_report}".lower()

        # 1. Root IOC
        # 2. Evaluated by specialist and flagged (specialist_ctx)
        # 3. Malicious
        # 4. Specialist or Lead Hunter flags it as relevant (mentioned in reports)
        is_relevant = (
            is_root or 
            bool(specialist_ctx) or 
            is_malicious or 
            (str(node_id).lower() in full_report_text)
        )

        # ── Vendor detection stats for detail panel ─────────────────────
        total_vendors = sum(analysis_stats.get(k, 0) for k in ("malicious", "suspicious", "undetected", "harmless")) if isinstance(analysis_stats, dict) else 0

        included_node_ids.add(node_id)
        nodes.append({
            "id":              node_id,
            "label":           label,
            "color":           "#FF4B4B" if is_root else COLOR_MAP.get(etype, "#95A5A6"),
            "entityType":      etype,
            "size":            35 if is_root else 20,
            "title":           tooltip,
            "isRoot":          is_root,
            "isMalicious":     is_malicious,
            "inReport":        is_relevant,
            "threatScore":     threat_score,
            "verdict":         verdict,
            "vendorDetections": f"{malicious_count}/{total_vendors}" if total_vendors else None,
        })

    # ── Edges ──────────────────────────────────────────────────────────────
    for source, target, edata in cache.graph.edges(data=True):
        # Include all edges for nodes we are keeping
        if source not in included_node_ids or target not in included_node_ids:
            continue
            
        rel = edata.get("relationship") or ""
        key = (source, target, rel)
        if key not in edge_registry:
            edges.append({
                "source": source,
                "target": target,
                "label":  rel.replace("_", " "),
            })
            edge_registry.add(key)

    logger.info("graph_from_cache_complete", job_id=job_id,
                total_nodes=len(nodes), total_edges=len(edges))
    return {"nodes": nodes, "edges": edges}

