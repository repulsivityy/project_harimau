"""
NetworkX-based investigation cache for storing full entity context.

This module provides an in-memory graph cache that stores complete entity
attributes from GTI API, enabling:
1. Token-optimized LLM context (query minimal fields)
2. Rich graph visualization (query display fields)
3. Specialist agent efficiency (no re-fetching)
"""

import networkx as nx
from typing import Dict, List, Any, Optional
import json
from backend.utils.logger import get_logger
from backend.utils.entity_identity import gti_url_id, is_http_url, normalise_entity_id

logger = get_logger("graph_cache")

def _normalise_id(entity_id: Optional[Any], entity_type: Optional[str] = None) -> Optional[str]:
    """Compatibility wrapper for the typed investigation identity contract."""
    return normalise_entity_id(entity_id, entity_type)


def _json_value(value: Any) -> Any:
    """Preserve JSON tool output as structured data when possible."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _append_unique_record(records: List[Any], record: Dict[str, Any]) -> List[Any]:
    """Append a JSON-compatible evidence record exactly once, in call order."""
    key = json.dumps(record, sort_keys=True, default=str)
    for existing in records:
        if json.dumps(existing, sort_keys=True, default=str) == key:
            return records
    return [*records, record]


def _contains_error(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value.get("error")) or any(_contains_error(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_error(item) for item in value)
    if isinstance(value, str):
        parsed = _json_value(value)
        return parsed is not value and _contains_error(parsed)
    return False


def _tool_status(output: Any) -> str:
    """Keep failed, explicit no-data, and useful tool results distinguishable."""
    if _contains_error(output):
        return "failed"
    if output in (None, "", [], {}):
        return "no_data"
    if isinstance(output, dict) and output.get("data") == []:
        return "no_data"
    return "succeeded"


def _attempt_sort_key(record: Dict[str, Any]) -> tuple:
    attempt = record.get("attempt") or {}
    return (int(attempt.get("iteration", -1)), str(attempt.get("id") or ""))


def latest_specialist_outcomes(records: List[Any]) -> Dict[str, Dict[str, Any]]:
    """Derive each agent's latest outcome from append-only attempt history."""
    latest: Dict[str, Dict[str, Any]] = {}
    for record in records or []:
        if not isinstance(record, dict) or not record.get("agent"):
            continue
        agent = record["agent"]
        if agent not in latest or _attempt_sort_key(record) >= _attempt_sort_key(latest[agent]):
            latest[agent] = record
    return latest


def format_specialist_evidence_summary(node: Dict[str, Any]) -> str:
    """Return a bounded planner-facing summary; never expose raw tool payloads."""
    findings = node.get("specialist_findings") or []
    if not isinstance(findings, list):
        return ""
    summaries = []
    for finding in findings[-2:]:
        if not isinstance(finding, dict):
            continue
        agent = finding.get("agent") or "specialist"
        evidence = finding.get("evidence") or {}
        verdict = evidence.get("verdict")
        detail = evidence.get("behavior") or evidence.get("notes")
        bits = [str(agent)]
        if verdict:
            bits.append(f"verdict={verdict}")
        if detail:
            bits.append(str(detail).replace("\n", " ")[:240])
        summaries.append("; ".join(bits))
    return " | ".join(summaries)


def format_validated_graph_evidence(cache: "InvestigationCache", limit: int = 12) -> str:
    """Bounded tool-backed target evidence for synthesis fallback reports."""
    lines = []
    for node_id, node in cache.graph.nodes(data=True):
        outcomes = latest_specialist_outcomes(node.get("specialist_outcome_history") or [])
        for finding in node.get("specialist_findings") or []:
            if not isinstance(finding, dict):
                continue
            agent = finding.get("agent")
            outcome = outcomes.get(agent) or {}
            if outcome.get("status") != "succeeded" or finding.get("attempt") != outcome.get("attempt"):
                continue
            evidence = finding.get("evidence") or {}
            detail = evidence.get("behavior") or evidence.get("notes") or "target-specific finding retained"
            tools = [
                item.get("tool") for item in node.get("specialist_tool_evidence") or []
                if item.get("agent") == agent and item.get("status") == "succeeded"
                and item.get("attempt", {}).get("iteration") == outcome.get("attempt", {}).get("iteration")
            ]
            lines.append(
                f"- {node_id} | {agent} | verdict={evidence.get('verdict') or 'unknown'} "
                f"| evidence={str(detail).replace(chr(10), ' ')[:240]} | tools={', '.join(dict.fromkeys(tools)) or 'recorded'}"
            )
            if len(lines) >= limit:
                return "\n".join(lines)
    return "\n".join(lines) or "No validated graph-backed specialist evidence retained."

# Ordered (not a set) so the substring fallback below is deterministic.
KNOWN_VERDICTS = ["malicious", "suspicious", "benign", "undetected", "unknown"]

def normalize_verdict(raw: Optional[Any]) -> Optional[str]:
    """
    Normalise a raw GTI verdict value (e.g. 'VERDICT_MALICIOUS') to a canonical
    lowercase token (e.g. 'malicious'). Returns None if raw is falsy or unrecognised.
    """
    if not raw:
        return None
    v = str(raw).strip().lower()
    v = v[len("verdict_"):] if v.startswith("verdict_") else v
    if v in KNOWN_VERDICTS:
        return v
    # Forward-compat: fall back to substring containment, then log so an
    # unrecognised GTI verdict format doesn't silently resolve to "no signal" again.
    for known in KNOWN_VERDICTS:
        if known in v:
            return known
    logger.warning("verdict_unrecognized", raw=raw)
    return None

def extract_gti_summary(rel_item: dict) -> dict:
    """Extract key GTI attributes from a relationship response item.

    NOTE ON A STRUCTURAL DATA LIMITATION (pivot-discovered entities):
    Callers that populate `rel_item` from the GTI relationship-listing tools
    (`get_entities_related_to_a_domain`/`_an_ip_address`/`_an_url`/`_a_file` in
    backend/mcp/gti/tools/{netloc,files,urls}.py) are required by those tools'
    own docstrings to pass `descriptors_only=True` whenever the *target*
    object type is file/domain/url/ip_address/collection ("Must be True when
    the target object type is one of file, domain, url, ip_address or
    collection"). That is exactly the set of relationship targets that matter
    for scoring (see verdict_engine.REAL_INDICATOR_TYPES). In descriptor mode
    the GTI API returns a minimal object (essentially `type`/`id`, optionally
    `context_attributes`) rather than the full `attributes` block a direct
    per-entity report (get_domain_report/get_file_report/...) or triage.py's
    "Super-Bundle" fetch (backend/tools/gti.py:_enrich_with_relationships,
    which follows up each relationship's "related" link to fetch full
    objects) would return. Extending the key list below only helps for the
    fields that a descriptor response can actually carry (if any land in
    `context_attributes`) — it CANNOT recover fields that the API simply does
    not transmit in this mode. Getting the full set would require a
    supplementary per-entity fetch (extra API calls per pivot-discovered
    entity), which is an architecture/cost decision out of scope here — see
    backend/agents/infrastructure.py call sites for the same note.
    """
    summary = {}
    if not isinstance(rel_item, dict): return summary

    # GTI sometimes nests the actual entity data under 'context_attributes' or leaves it at root
    attrs = rel_item.get("context_attributes", {}) or rel_item.get("attributes", {}) or rel_item

    # Core fields (pre-existing). Extended below with fields verdict_engine's
    # attribution/sandbox/staleness heuristics read (_has_attribution,
    # _has_sandbox_behavior, _is_stale in backend/utils/verdict_engine.py) plus
    # a few extra descriptor-friendly fields (creation_date, tld,
    # first_submission_date, times_submitted, last_https_certificate) that
    # signal_filter.get_signal_reason reads for triage-discovered entities and
    # that may occasionally be present on a richer descriptor/context_attributes
    # payload even when the bulk `attributes` block is withheld. These are
    # captured opportunistically; for the common descriptors_only=True case
    # most will simply be absent (see module-level note above) and are
    # harmlessly skipped by the `if key in attrs` guard.
    for key in [
        "gti_assessment", "meaningful_name", "names", "last_analysis_stats",
        "malware_families", "related_threat_actors", "associations", "campaigns",
        "sandbox_verdicts", "behaviour_summary", "crowdsourced_ids_results",
        "last_analysis_date", "creation_date", "tld", "first_seen_itw_date",
        "first_submission_date", "times_submitted", "last_https_certificate",
    ]:
        if key in attrs:
            summary[key] = attrs[key]

    # Also grab the raw ID/Type if it's there for context
    if "id" in rel_item: summary["gti_id"] = rel_item["id"]
    if "type" in rel_item: summary["gti_type"] = rel_item["type"]

    return summary


def _merge_graph_attributes(existing: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    """Merge migration collisions without discarding persisted evidence."""
    for key, value in incoming.items():
        if key not in existing:
            existing[key] = value
        elif isinstance(existing[key], dict) and isinstance(value, dict):
            _merge_graph_attributes(existing[key], value)
        elif isinstance(existing[key], list) and isinstance(value, list):
            for item in value:
                if item not in existing[key]:
                    existing[key].append(item)


def _canonical_url_node_id(node_id: Any, data: Dict[str, Any]) -> Optional[str]:
    """Best-effort recovery of a URL node from old checkpoint representations."""
    for value in (data.get("gti_id"), data.get("gti_url_id")):
        decoded = normalise_entity_id(value, "url")
        if decoded and not decoded.startswith("gti-url:"):
            return decoded
    # Older cache keys were lowercased URL strings. URL attributes are the
    # only source that can recover their original path/query casing.
    for value in (data.get("url"), data.get("last_final_url"), node_id):
        canonical = normalise_entity_id(value, "url")
        if canonical and not canonical.startswith("gti-url:"):
            return canonical
    return normalise_entity_id(node_id, "url")


def _migrate_graph_identities(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Upgrade persisted graph keys and endpoints to the typed identity contract.

    Checkpoints created before typed URL identities can contain a lowercased
    raw URL node, a separate GTI base64-id node, and edges to either form.
    Rebuild atomically so aliases collapse into one canonical node and no edge
    retains a phantom endpoint.
    """
    if not isinstance(graph, nx.MultiDiGraph):
        return graph

    aliases: Dict[str, str] = {}
    for node_id, data in graph.nodes(data=True):
        if data.get("entity_type") != "url":
            continue
        canonical = _canonical_url_node_id(node_id, data)
        if not canonical:
            continue
        # last_final_url describes a redirect destination, not another spelling
        # of this URL. Treating it as an alias collapses two distinct resources.
        for alias in (node_id, data.get("gti_id"), data.get("gti_url_id"), data.get("url")):
            if alias is not None and str(alias).strip():
                aliases[str(alias).strip()] = canonical
        generated_id = gti_url_id(canonical)
        if generated_id:
            aliases[generated_id] = canonical

    node_map: Dict[Any, str] = {}
    for node_id, data in graph.nodes(data=True):
        raw = str(node_id).strip()
        node_map[node_id] = aliases.get(raw) or (
            _canonical_url_node_id(node_id, data)
            if data.get("entity_type") == "url"
            else _normalise_id(node_id, data.get("entity_type"))
        ) or raw

    migrated = nx.MultiDiGraph()
    for node_id, data in graph.nodes(data=True):
        canonical = node_map[node_id]
        attributes = dict(data)
        if attributes.get("entity_type") == "url":
            attributes.setdefault("gti_url_id", gti_url_id(canonical))
            raw = str(node_id).strip()
            if raw != canonical and not is_http_url(raw):
                attributes.setdefault("gti_id", raw)
        if canonical in migrated:
            _merge_graph_attributes(migrated.nodes[canonical], attributes)
        else:
            migrated.add_node(canonical, **attributes)

    for source, target, data in graph.edges(data=True):
        canonical_source = node_map.get(source, aliases.get(str(source).strip()) or _normalise_id(source))
        canonical_target = node_map.get(target, aliases.get(str(target).strip()) or _normalise_id(target))
        if not canonical_source or not canonical_target:
            continue
        relationship = data.get("relationship")
        matched = False
        if migrated.has_edge(canonical_source, canonical_target):
            for _, existing in migrated[canonical_source][canonical_target].items():
                if existing.get("relationship") == relationship:
                    _merge_graph_attributes(existing, dict(data))
                    matched = True
                    break
        if not matched:
            migrated.add_edge(canonical_source, canonical_target, **data)
    return migrated


class InvestigationCache:
    """NetworkX-based cache for investigation entities with full attributes."""
    
    def __init__(self, graph: Optional[Any] = None):
        """
        Initialize investigation cache.
        
        Args:
            graph: Existing NetworkX graph to reuse, a state dict, or None to create new
        """
        if isinstance(graph, dict) and ("nodes" in graph or "edges" in graph or "links" in graph):
            self.graph = nx.node_link_graph(graph)
        elif isinstance(graph, nx.MultiDiGraph):
            self.graph = graph
        else:
            self.graph = nx.MultiDiGraph()
        self.graph = _migrate_graph_identities(self.graph)

    def get_state(self) -> Dict[str, Any]:
        """Get the graph as a dictionary for state persistence."""
        return nx.node_link_data(self.graph)

    def _resolve_entity_id(self, entity_id: Any, entity_type: Optional[str] = None) -> Optional[str]:
        """Resolve a graph key, including a GTI URL id already admitted to it."""
        resolved = _normalise_id(entity_id, entity_type)
        if resolved in self.graph:
            return resolved
        raw = str(entity_id).strip() if entity_id is not None else ""
        if not raw:
            return resolved
        # Relationship descriptors frequently name URL objects by GTI's base64
        # id while specialists use the raw URL.  Match only explicit URL
        # aliases retained on a URL node; never fuzzy-match arbitrary IDs.
        for node_id, data in self.graph.nodes(data=True):
            if data.get("entity_type") != "url":
                continue
            aliases = {str(data.get("gti_id") or "").strip(), str(data.get("gti_url_id") or "").strip()}
            if raw in aliases:
                return node_id
        return resolved
    
    def add_entity(self, entity_id: str, entity_type: str, attributes: Dict[str, Any]):
        """
        Store full entity with all GTI attributes.
        
        Args:
            entity_id: Unique entity identifier (e.g., SHA256, IP, domain)
            entity_type: Entity type (file, ip_address, domain, url, etc.)
            attributes: Complete attributes dictionary from GTI API
        """
        # Deduplication: Check if entity already exists
        raw_id = str(entity_id).strip() if entity_id is not None else ""
        entity_id = _normalise_id(entity_id, entity_type)
        if not entity_id:
            return
        attributes = dict(attributes or {})
        if entity_type == "url":
            # Graph identity is the canonical raw URL. Keep GTI's opaque id as
            # provenance/lookup metadata, never as a competing graph node.
            attributes.setdefault("gti_url_id", gti_url_id(entity_id))
            if raw_id and raw_id != entity_id:
                attributes.setdefault("gti_id", raw_id)
        if entity_id in self.graph:
            # Entity exists - merge attributes instead of overwriting
            existing_data = self.graph.nodes[entity_id]

            # Deep merge: preserve existing data, add new fields
            for key, value in attributes.items():
                if key not in existing_data:
                    existing_data[key] = value
                elif isinstance(value, dict) and isinstance(existing_data[key], dict):
                    existing_data[key].update(value)
                elif isinstance(value, list) and isinstance(existing_data[key], list):
                    for item in value:
                        if item not in existing_data[key]:
                            existing_data[key].append(item)
                # If types mismatch or simple value, keep existing (first-write wins)
            logger.debug("entity_merged", entity_id=entity_id, entity_type=entity_type)
        else:
            # New entity - add it
            self.graph.add_node(
                entity_id,
                entity_type=entity_type,
                **attributes
            )
            logger.debug("entity_added", entity_id=entity_id, entity_type=entity_type)
    
    def add_relationship(self, source_id: str, target_id: str, rel_type: str, 
                        metadata: Optional[Dict[str, Any]] = None):
        """
        Add relationship edge between entities.
        
        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            rel_type: Relationship type (e.g., contacted_domains, dropped_files)
            metadata: Optional edge metadata
        """
        source_id = self._resolve_entity_id(source_id)
        target_id = self._resolve_entity_id(target_id)
        if not source_id or not target_id:
            return
        if self.graph.has_edge(source_id, target_id):
            for edge_key, edge_data in self.graph[source_id][target_id].items():
                if edge_data.get("relationship") == rel_type:
                    if metadata:
                        edge_data.update(metadata)
                    logger.debug("relationship_updated", source=source_id, target=target_id, rel_type=rel_type)
                    return

        edge_data = {"relationship": rel_type}
        if metadata:
            edge_data.update(metadata)

        self.graph.add_edge(source_id, target_id, **edge_data)
        logger.debug("relationship_added", source=source_id, target=target_id, rel_type=rel_type)
    
    def get_entity_minimal(self, entity_id: str, fields: List[str]) -> Dict[str, Any]:
        """
        Get minimal fields for LLM context (token-optimized).
        
        Args:
            entity_id: Entity ID to query
            fields: List of field names to extract
            
        Returns:
            Dictionary with only requested fields
        """
        entity_id = self._resolve_entity_id(entity_id)
        if not entity_id or entity_id not in self.graph:
            return {}
        
        node_data = self.graph.nodes[entity_id]
        return {field: node_data.get(field) for field in fields if field in node_data}
    
    def get_entity_full(self, entity_id: str) -> Dict[str, Any]:
        """
        Get full entity with all attributes (for specialists).
        
        Args:
            entity_id: Entity ID to query
            
        Returns:
            Dictionary with all stored attributes
        """
        entity_id = self._resolve_entity_id(entity_id)
        if not entity_id or entity_id not in self.graph:
            return {}
        
        return dict(self.graph.nodes[entity_id])
    
    def get_neighbors(self, entity_id: str, relationship: Optional[str] = None) -> List[str]:
        """
        Get related entities by relationship type.
        
        Args:
            entity_id: Entity ID to query
            relationship: Optional relationship type filter
            
        Returns:
            List of neighbor entity IDs
        """
        entity_id = self._resolve_entity_id(entity_id)
        if not entity_id or entity_id not in self.graph:
            return []
        
        neighbors = list(self.graph.neighbors(entity_id))
        
        if relationship:
            # Filter by relationship type
            filtered = []
            for neighbor in neighbors:
                # Check all edges between source and target (MultiDiGraph)
                for edge_key, edge_data in self.graph[entity_id][neighbor].items():
                    if edge_data.get('relationship') == relationship:
                        filtered.append(neighbor)
                        break  # Only add once even if multiple edges
            return filtered
        
        return neighbors
    
    def get_neighbors_with_data(self, entity_id: str, relationship: Optional[str] = None,
                                fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Get neighbors with their entity data.
        
        Args:
            entity_id: Entity ID to query
            relationship: Optional relationship type filter
            fields: Optional list of fields to extract (None = all fields)
            
        Returns:
            List of neighbor entity dictionaries
        """
        neighbor_ids = self.get_neighbors(entity_id, relationship)
        
        neighbors_data = []
        for neighbor_id in neighbor_ids:
            if fields:
                entity_data = self.get_entity_minimal(neighbor_id, fields)
            else:
                entity_data = self.get_entity_full(neighbor_id)
            
            if entity_data:
                entity_data["id"] = neighbor_id  # Ensure ID is present
                neighbors_data.append(entity_data)
        
        return neighbors_data
    
    def get_all_entities_by_type(self, entity_type: str) -> List[str]:
        """
        Get all entity IDs of a specific type.
        
        Args:
            entity_type: Type to filter by (file, domain, ip_address, url)
            
        Returns:
            List of entity IDs matching the type
        """
        return [
            node for node, data in self.graph.nodes(data=True)
            if data.get('entity_type') == entity_type
        ]
    
    def has_entity(self, entity_id: str) -> bool:
        """Check if entity exists in cache."""
        entity_id = self._resolve_entity_id(entity_id)
        if not entity_id:
            return False
        return entity_id in self.graph
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        entity_types = {}
        analyzed_count = 0
        
        for node, data in self.graph.nodes(data=True):
            etype = data.get('entity_type', 'unknown')
            entity_types[etype] = entity_types.get(etype, 0) + 1
            
            # Count analyzed nodes (for Lead Hunter tracking)
            if data.get("analyzed_by"):
                analyzed_count += 1
        
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "total_entities": self.graph.number_of_nodes(),  # Backward compat
            "total_relationships": self.graph.number_of_edges(),  # Backward compat
            "entity_types": entity_types,
            "nodes_by_type": entity_types,  # For Lead Hunter
            "analyzed_count": analyzed_count
        }
        
    def mark_as_investigated(self, entity_id: str, agent: str):
        """
        Mark an entity as investigated by a specific agent.
        
        Args:
            entity_id: The entity ID
            agent: The agent name (e.g., 'malware', 'infrastructure')
        """
        entity_id = self._resolve_entity_id(entity_id)
        if not entity_id or entity_id not in self.graph:
            return

        node = self.graph.nodes[entity_id]
        analyzed_by = set(node.get("analyzed_by", []))
        analyzed_by.add(agent)

        # Update node attribute (convert back to list for JSON serialization)
        self.graph.nodes[entity_id]["analyzed_by"] = list(analyzed_by)
        logger.info("entity_marked_investigated", entity_id=entity_id, agent=agent)

    def record_target_outcomes(self, outcomes: Dict[str, Dict[str, Any]],
                               attempt: Optional[Dict[str, Any]] = None):
        """Append attempt-aware outcome metadata without clobbering prior attempts."""
        for outcome in (outcomes or {}).values():
            target_id = self._resolve_entity_id(outcome.get("target_id"))
            agent = outcome.get("agent")
            if not target_id or not agent or target_id not in self.graph:
                continue
            recorded = dict(outcome)
            recorded.pop("target_id", None)
            recorded["agent"] = agent
            recorded["target_id"] = target_id
            recorded["source"] = "specialist_target_outcome"
            recorded["attempt"] = dict(attempt or {})
            history = list(self.graph.nodes[target_id].get("specialist_outcome_history") or [])
            self.graph.nodes[target_id]["specialist_outcome_history"] = _append_unique_record(history, recorded)
            self.graph.nodes[target_id]["specialist_outcomes"] = latest_specialist_outcomes(
                self.graph.nodes[target_id]["specialist_outcome_history"]
            )

    def record_tool_evidence(self, agent: str, tool: str, target_id: str,
                             output: Any, *, source: Optional[str] = None,
                             attempt: Optional[Dict[str, Any]] = None):
        """Persist a specialist tool result on its requested target node.

        ToolNode messages are transient and are not reliably available after a
        parallel fan-in or checkpoint resume. Keeping the exact JSON-compatible
        output here lets later planning and synthesis distinguish a grounded
        finding from a narrative-only assertion. Raw payloads stay out of LLM
        contexts; ``format_specialist_evidence_summary`` emits only bounded
        structured-result details.
        """
        target_id = self._resolve_entity_id(target_id)
        if not target_id:
            return
        # A tool call on an unadmitted/model-invented IOC must not create a
        # graph node. Triage/pivot tools establish nodes before specialists
        # enrich them; evidence is attached only to that grounded graph.
        if target_id not in self.graph:
            logger.warning("tool_evidence_target_not_in_graph", agent=agent, tool=tool, target_id=target_id)
            return
        evidence = {
            "source": source or f"{agent}_analysis_tool",
            "agent": agent,
            "tool": tool,
            "target_id": target_id,
            "output": _json_value(output),
            "attempt": dict(attempt or {}),
        }
        evidence["status"] = _tool_status(evidence["output"])
        existing = list(self.graph.nodes[target_id].get("specialist_tool_evidence") or [])
        self.graph.nodes[target_id]["specialist_tool_evidence"] = _append_unique_record(existing, evidence)

    def record_specialist_result(self, agent: str, result: Dict[str, Any],
                                 outcomes: Dict[str, Dict[str, Any]],
                                 attempt: Dict[str, Any]):
        """Attach only outcome-validated structured evidence to admitted nodes."""
        if not isinstance(result, dict):
            return
        common = {
            key: value for key, value in result.items()
            if key not in {"analyzed_targets", "markdown_report", "summary"}
        }
        summary = str(result.get("summary") or "").replace("\n", " ")[:600]
        targets = {
            self._resolve_entity_id(target.get("indicator") or target.get("value")): target
            for target in result.get("analyzed_targets") or []
            if isinstance(target, dict) and self._resolve_entity_id(target.get("indicator") or target.get("value"))
        }
        for outcome in (outcomes or {}).values():
            if outcome.get("agent") != agent or outcome.get("status") != "succeeded":
                continue
            target_id = self._resolve_entity_id(outcome.get("target_id"))
            target = targets.get(target_id)
            if not target_id or not target or target_id not in self.graph:
                continue
            record = {
                "source": f"{agent}_specialist_structured_output",
                "agent": agent,
                "attempt": dict(attempt),
                "outcome": {
                    "status": outcome.get("status"),
                    "reason": outcome.get("reason"),
                    "evidence": outcome.get("evidence") or {},
                },
                "evidence": {
                    key: value for key, value in target.items()
                    if value not in (None, "", [], {})
                },
                "findings": common,
                "summary": summary,
            }
            existing = list(self.graph.nodes[target_id].get("specialist_findings") or [])
            self.graph.nodes[target_id]["specialist_findings"] = _append_unique_record(existing, record)
        
    def get_uninvestigated_nodes(self, agent_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get nodes that have NOT been fully investigated.
        
        Args:
            agent_filter: If provided, only returns nodes NOT analyzed by this specific agent.
            
        Returns:
            List of node dictionaries with their data.
        """
        uninvestigated = []
        for node_id, data in self.graph.nodes(data=True):
            analyzed_by = data.get("analyzed_by", [])
            
            # If agent_filter is specific, check if THIS agent has analyzed it
            if agent_filter:
                if agent_filter not in analyzed_by:
                    # Return full data
                    node_data = dict(data)
                    node_data["id"] = node_id
                    uninvestigated.append(node_data)
            else:
                # If no filter, return if NO ONE has analyzed it (fresh node)
                if not analyzed_by:
                    node_data = dict(data)
                    node_data["id"] = node_id
                    uninvestigated.append(node_data)
                    
        return uninvestigated

    def export_for_visualization(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Export graph data for frontend visualization.
        
        Returns:
            Dictionary with 'nodes' and 'edges' lists
        """
        nodes = []
        edges = []
        
        # Export nodes
        for node_id, data in self.graph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "type": data.get("entity_type"),
                **{k: v for k, v in data.items() if k != "entity_type"}
            })
        
        # Export edges
        for source, target, data in self.graph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "relationship": data.get("relationship"),
                **{k: v for k, v in data.items() if k != "relationship"}
            })
        
        return {"nodes": nodes, "edges": edges}
