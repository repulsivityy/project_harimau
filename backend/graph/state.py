from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
import operator

def merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Merges two dictionaries (shallow merge)."""
    return {**a, **b}

def last_value(a: Any, b: Any) -> Any:
    """Reducer that returns the last value (for scalar fields in parallel execution)."""
    return b if b is not None else a

def union_lists(a: Optional[List[str]], b: Optional[List[str]]) -> List[str]:
    """Union two lists with case-insensitive deduplication."""
    res = list(a or [])
    res_norm = {str(item).strip().lower() for item in res if item is not None}
    for item in (b or []):
        if item is not None:
            norm = str(item).strip().lower()
            if norm not in res_norm:
                res.append(item)
                res_norm.add(norm)
    return res

def merge_graphs(a: Optional[Any], b: Optional[Any]) -> Optional[Any]:
    """
    Merge two NetworkX graphs (for parallel specialist execution).
    When specialists run in parallel, both expand the graph independently.
    This ensures both sets of updates are preserved.
    """
    if a is None: return b
    if b is None: return a
    
    # Import here to avoid circular deps
    import networkx as nx
    
    # Deserialized graphs from dicts if necessary
    graph_a = nx.node_link_graph(a) if isinstance(a, dict) else a
    graph_b = nx.node_link_graph(b) if isinstance(b, dict) else b
    
    # Merge nodes
    combined = nx.MultiDiGraph(graph_a)
    existing_nodes_norm = {str(n).strip().lower(): n for n in combined.nodes()}
    for node, data in graph_b.nodes(data=True):
        norm_node = str(node).strip().lower()
        if norm_node in existing_nodes_norm:
            actual_node = existing_nodes_norm[norm_node]
            # Node exists - deep merge attributes
            existing = combined.nodes[actual_node]
            for key, val in data.items():
                if key not in existing:
                    existing[key] = val
                elif isinstance(val, dict) and isinstance(existing[key], dict):
                    existing[key].update(val)
                elif isinstance(val, list) and isinstance(existing[key], list):
                    res = list(existing[key])
                    res_set = {str(i).strip().lower() for i in res if i is not None}
                    for item in val:
                        if item is not None and str(item).strip().lower() not in res_set:
                            res.append(item)
                            res_set.add(str(item).strip().lower())
                    existing[key] = res
                else:
                    existing[key] = val
        else:
            # New node - add it
            combined.add_node(node, **data)
            existing_nodes_norm[norm_node] = node
    
    # Merge edges
    for u, v, data in graph_b.edges(data=True):
        rel = data.get("relationship")
        edge_matched = False
        if combined.has_edge(u, v):
            for edge_key, edge_data in combined[u][v].items():
                if edge_data.get("relationship") == rel:
                    edge_data.update(data)
                    edge_matched = True
                    break
        if not edge_matched:
            combined.add_edge(u, v, **data)
    
    # Return as dict for state persistence
    return nx.node_link_data(combined)

def _is_entity_list(lst: List[Any]) -> bool:
    """
    Heuristic: detects a rich_intel-style relationship entity list, i.e. a list of
    dicts shaped like push_to_rich_intel's output (backend/utils/agent_utils.py):
    {"id": ..., "type": ..., "source_id": ..., "attributes": {...}}.
    We only require "id" and "source_id" to be present, since that's the pair
    push_to_rich_intel dedupes on.
    """
    return any(
        isinstance(item, dict) and "id" in item and "source_id" in item
        for item in lst
    )

def _merge_entity_lists(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Concatenate two rich_intel relationship entity lists, deduping on the exact
    same key push_to_rich_intel uses: (id, source_id), both normalized via
    str(...).strip().lower(). Keeps the first-seen entity for any duplicate key
    (mirrors push_to_rich_intel's "skip if exists" semantics), so merging is
    idempotent and never creates duplicate entities.
    """
    def dedup_key(item: Dict[str, Any]):
        return (
            str(item.get("id")).strip().lower(),
            str(item.get("source_id")).strip().lower(),
        )

    result: List[Dict[str, Any]] = []
    seen = set()
    for item in list(a) + list(b):
        if isinstance(item, dict) and "id" in item and "source_id" in item:
            key = dedup_key(item)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        else:
            # Defensive: not an entity dict (shouldn't happen for rich_intel
            # relationship lists) - keep it if not already present.
            if item not in result:
                result.append(item)
    return result

def _merge_generic_lists(a: List[Any], b: List[Any]) -> List[Any]:
    """
    Fallback list merge for non-entity lists: concatenate + dedupe by value
    equality, preserving order (a's items first, then new items from b).
    """
    result = list(a)
    for item in b:
        if item not in result:
            result.append(item)
    return result

def _deep_merge_value(a: Any, b: Any) -> Any:
    """
    Generic recursive merge used by merge_metadata:
      - dict + dict: merge key-by-key, recursing into shared keys.
      - list + list: if either list looks like a rich_intel entity list
        (push_to_rich_intel shape), dedupe on (id, source_id); otherwise
        concatenate + dedupe by value equality.
      - anything else (scalars, mismatched types, None on one side): b wins
        if present, else a is kept. This preserves last-write-wins semantics
        for single-writer scalar fields (e.g. risk_level, gti_score).
    """
    if a is None:
        return b
    if b is None:
        return a
    if isinstance(a, dict) and isinstance(b, dict):
        merged = dict(a)
        for key, b_val in b.items():
            if key not in merged:
                merged[key] = b_val
            else:
                merged[key] = _deep_merge_value(merged[key], b_val)
        return merged
    if isinstance(a, list) and isinstance(b, list):
        if _is_entity_list(a) or _is_entity_list(b):
            return _merge_entity_lists(a, b)
        return _merge_generic_lists(a, b)
    # Scalars or mismatched types: last-write-wins (b wins)
    return b

def merge_metadata(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deep-merge reducer for the `metadata` state field.

    Replaces the old shallow merge_dicts (`{**a, **b}`), which discarded one
    parallel specialist's entire `rich_intel` sub-tree whenever malware_node
    and infrastructure_node (genuine parallel LangGraph branches fanned out
    from `gate`) both returned updated `metadata`. Both branches write into
    state["metadata"]["rich_intel"]["relationships"] under different rel_name
    keys ("communicates_with"/"dropped" for malware, "related_infrastructure"
    for infrastructure) via push_to_rich_intel, but since both start from the
    same pre-fan-out metadata snapshot, a shallow top-level merge would let
    whichever branch's update was folded in second silently replace the
    other's `rich_intel` dict wholesale.

    This mirrors merge_graphs' "never lose data" philosophy for parallel
    specialist updates, generalized to arbitrary nested dict/list shapes
    instead of being hardcoded to one schema:
      - Keys present on only one side are kept as-is.
      - Keys present on both sides with dict values are merged recursively
        (so rich_intel's other sub-keys - triage_analysis, triage_summary,
        signal_filter_carryover - are preserved even though both parallel
        branches carry identical copies of them from before the fan-out).
      - Keys present on both sides with list values are concatenated and
        deduped - using the (id, source_id) key push_to_rich_intel uses for
        rich_intel.relationships entity lists, or plain value-equality dedup
        for any other list-shaped metadata.
      - Otherwise (scalars, e.g. risk_level/gti_score which triage sets
        single-threaded before the fan-out): b wins, i.e. last-write-wins,
        same as the previous shallow-merge behavior for those keys.
    """
    if a is None:
        return b if b is not None else {}
    if b is None:
        return a
    if not isinstance(a, dict) or not isinstance(b, dict):
        # Defensive: metadata should always be a dict; if not, fall back to
        # last-write-wins rather than raising.
        return b
    return _deep_merge_value(a, b)

class AgentState(TypedDict):
    """
    State schema for the Harimau Investigation Graph.
    Passed between all nodes in the workflow.
    """
    job_id: Annotated[str, last_value]
    ioc: Annotated[str, last_value]
    ioc_type: Annotated[Optional[str], last_value]
    
    # Chat History: Stores the chain of thought and tool outputs
    messages: Annotated[List[BaseMessage], operator.add]
    
    # Subtasks: Tasks generated by Triage for Specialists
    # Example: [{"agent": "malware", "task": "Analyze behavior of hash..."}]
    subtasks: Annotated[List[Dict[str, Any]], last_value]
    
    # Outputs: Final results from specialists
    # Example: {"malware": {"verdict": "malicious", "details": "..."}}
    specialist_results: Annotated[Dict[str, Any], merge_dicts]
    
    # Final Report: The generated markdown report
    # Reverting to last_value since Lead Hunter now assembles report manually
    final_report: Annotated[Optional[str], last_value]
    
    # Metadata: Timing, errors, etc.
    # CRITICAL: Uses merge_metadata (deep merge) instead of shallow merge_dicts,
    # since malware_node and infrastructure_node run as parallel branches and
    # both write into metadata["rich_intel"]["relationships"]; a shallow merge
    # would let one branch's entire rich_intel sub-tree silently clobber the
    # other's. See merge_metadata's docstring above for details.
    metadata: Annotated[Dict[str, Any], merge_metadata]
    
    # Investigation Graph: NetworkX cache for full entity storage
    # Stores complete GTI attributes for all entities and relationships
    # CRITICAL: Uses merge_graphs to preserve updates from parallel specialists
    investigation_graph: Annotated[Optional[Any], merge_graphs]  # nx.MultiDiGraph (using Any to avoid import)
    
    # Iteration Control
    iteration: Annotated[int, last_value]  # Explicit iteration phase (0, 1, 2)

    # Investigation depth: controls cost vs. depth trade-off
    # Set from POST /api/investigate, persists unchanged through entire loop
    max_iterations: Annotated[int, last_value]
    
    lead_hunter_report: Annotated[Optional[str], last_value]  # Full synthesis report

    # Entities that have been assigned as subtasks across all iterations (for convergence detection)
    tasked_entities: Annotated[List[str], union_lists]