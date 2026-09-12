"""Target-level specialist completion checks.

Dispatching a target to a specialist is not evidence that the specialist
actually investigated it.  This module keeps that distinction deterministic:
a target succeeds only when the specialist's final structured response names
that target and supplies at least one target-specific evidence field.
"""

import json
import re
from typing import Any, Dict, Iterable, List, Optional
from backend.utils.entity_identity import normalise_target_id as _normalise_target_id


def normalise_target_id(value: Any) -> Optional[str]:
    """Return the typed canonical target id used by graph/lifecycle state."""
    return _normalise_target_id(value)


def canonical_agent(agent: Any) -> Optional[str]:
    """Collapse public and internal specialist aliases to one lifecycle key."""
    value = str(agent or "").strip().lower()
    if value in {"malware", "malware_specialist"}:
        return "malware"
    if value in {"infrastructure", "infrastructure_specialist"}:
        return "infrastructure"
    return None


def _dedupe_limited(candidates: Iterable[Any], limit: int) -> List[str]:
    selected = []
    for candidate in candidates:
        target_id = normalise_target_id(candidate)
        if target_id and target_id not in selected:
            selected.append(target_id)
        if len(selected) >= limit:
            break
    return selected


def _is_infrastructure_target(value: Any) -> bool:
    """Match the IOC forms accepted by the infrastructure specialist."""
    target = normalise_target_id(value)
    return bool(
        target
        and (
            re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", target)
            or target.startswith("http")
            or "." in target
        )
    )


def select_malware_target_ids(ioc: Any, subtasks: Iterable[Dict[str, Any]],
                              investigated_ids: Iterable[Any]) -> List[str]:
    """Pure, canonical version of the malware specialist's five-target cap."""
    investigated = {normalise_target_id(value) for value in investigated_ids or []}
    retry_candidates, normal_candidates = [], []
    root = normalise_target_id(ioc)
    if root and re.fullmatch(r"[a-f0-9]{32,64}", root) and root not in investigated:
        normal_candidates.append(root)
    for task in subtasks or []:
        if canonical_agent(task.get("agent")) != "malware":
            continue
        target = normalise_target_id(task.get("entity_id"))
        if target and re.fullmatch(r"[a-f0-9]{32,64}", target) and target not in investigated:
            (retry_candidates if task.get("priority") == "retry" else normal_candidates).append(target)
    return _dedupe_limited([*retry_candidates, *normal_candidates], 5)


def select_infrastructure_target_ids(ioc: Any, subtasks: Iterable[Dict[str, Any]],
                                     investigated_ids: Iterable[Any], triage_summary: str = "",
                                     key_findings: Iterable[Any] = ()) -> List[str]:
    """Pure, canonical version of the infrastructure specialist's ten-target cap."""
    investigated = {normalise_target_id(value) for value in investigated_ids or []}
    root = normalise_target_id(ioc)
    retry_candidates, normal_candidates = [], []
    if root and _is_infrastructure_target(root) and root not in investigated:
        normal_candidates.append(root)
    for task in subtasks or []:
        if canonical_agent(task.get("agent")) != "infrastructure":
            continue
        destination = retry_candidates if task.get("priority") == "retry" else normal_candidates
        if _is_infrastructure_target(task.get("entity_id")):
            destination.append(task["entity_id"])
        text = str(task.get("task") or "")
        destination.extend(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text))
        destination.extend(re.findall(r"https?://[^\s]+", text))
        for domain in re.findall(r"\b([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b", text):
            parts = domain.split(".")
            if len(parts) >= 2 and parts[-1].lower() not in {"exe", "dll", "pdf", "txt", "json", "docx", "png", "jpg", "zip", "rar"} and domain.lower() not in {"e.g", "i.e", "vs."}:
                destination.append(domain)
    if len(retry_candidates) + len(normal_candidates) < 5:
        context = f"{triage_summary or ''} {' '.join(str(value) for value in (key_findings or []))}"
        normal_candidates.extend(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", context))
        for domain in re.findall(r"\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,})\b", context):
            if normalise_target_id(domain) not in {root, "google.com", "virustotal.com", "example.com"}:
                normal_candidates.append(domain)
    return [
        target for target in _dedupe_limited([*retry_candidates, *normal_candidates], 10)
        if target not in investigated and _is_infrastructure_target(target)
    ]


def _tool_error_seen(messages: Iterable[Any]) -> bool:
    """Detect the uniform ``{\"error\": ...}`` envelopes returned by tools."""
    for message in messages or []:
        content = getattr(message, "content", message)
        if isinstance(content, list):
            content = " ".join(str(part) for part in content)
        if not isinstance(content, str):
            continue
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict) and parsed.get("error"):
            return True
    return False


def _successful_tool_targets(messages: Iterable[Any]) -> set[str]:
    """Return targets with a matched successful ToolNode result in this attempt."""
    calls: Dict[str, set[str]] = {}
    completed: set[str] = set()
    for message in messages or []:
        tool_calls = getattr(message, "tool_calls", None) or (message.get("tool_calls") if isinstance(message, dict) else None) or []
        for call in tool_calls:
            call_id = call.get("id")
            args = call.get("args") or call.get("arguments") or {}
            if call_id:
                values = args.values() if isinstance(args, dict) else []
                calls[call_id] = {normalise_target_id(value) for value in values if normalise_target_id(value)}
        tool_call_id = getattr(message, "tool_call_id", None) or (message.get("tool_call_id") if isinstance(message, dict) else None)
        if tool_call_id and tool_call_id in calls:
            content = getattr(message, "content", message.get("content") if isinstance(message, dict) else "")
            try:
                failed = isinstance(json.loads(content), dict) and bool(json.loads(content).get("error"))
            except (TypeError, json.JSONDecodeError):
                failed = False
            if not failed:
                completed.update(calls[tool_call_id])
    return completed


def _substantive(value: Any) -> bool:
    if not isinstance(value, str):
        return value not in (None, "", [], {})
    cleaned = value.strip().lower()
    return bool(cleaned) and cleaned not in {"unknown", "n/a", "na", "none", "null", "error", "no data", "not available", "no summary provided."} and not cleaned.startswith("error")


def assess_target_outcomes(
    target_ids: Iterable[Any],
    final_result: Optional[Dict[str, Any]],
    agent: str,
    *,
    messages: Optional[Iterable[Any]] = None,
    failure_reason: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Build the latest, minimal per-target result records for one specialist.

    A tool error conservatively fails the whole selected batch. The current
    ToolNode does not retain a reliable target-to-tool-call mapping, and it is
    safer to retry a target than to certify it from a partial tool run.
    """
    selected = []
    for target_id in target_ids or []:
        normalised = normalise_target_id(target_id)
        if normalised and normalised not in selected:
            selected.append(normalised)

    if failure_reason:
        batch_reason = failure_reason
    elif not isinstance(final_result, dict) or not final_result:
        batch_reason = "no_final_output"
    elif _tool_error_seen(messages or []):
        batch_reason = "tool_error"
    else:
        batch_reason = None

    analyzed = final_result.get("analyzed_targets") if isinstance(final_result, dict) else []
    by_indicator: Dict[str, Dict[str, Any]] = {}
    for item in analyzed or []:
        if not isinstance(item, dict):
            continue
        indicator = normalise_target_id(item.get("indicator") or item.get("value"))
        if indicator:
            by_indicator[indicator] = item

    successful_tools = _successful_tool_targets(messages or [])
    outcomes: Dict[str, Dict[str, Any]] = {}
    for target_id in selected:
        key = f"{agent}:{target_id}"
        evidence = by_indicator.get(target_id)
        if batch_reason:
            status, reason, evidence_payload = "failed", batch_reason, {}
        elif evidence is None:
            status, reason, evidence_payload = "failed", "not_addressed_by_model", {}
        else:
            evidence_payload = {
                field: evidence.get(field)
                for field in ("indicator", "verdict", "behavior", "notes")
                if _substantive(evidence.get(field))
            }
            if target_id not in successful_tools:
                status, reason = "failed", "missing_successful_tool_provenance"
            elif any(field in evidence_payload for field in ("verdict", "behavior", "notes")):
                status, reason = "succeeded", None
            else:
                status, reason = "failed", "missing_target_evidence"

        outcomes[key] = {
            "agent": agent,
            "target_id": target_id,
            "status": status,
            "evidence": evidence_payload,
            "reason": reason,
        }
    return outcomes


def successful_target_ids(outcomes: Dict[str, Dict[str, Any]]) -> List[str]:
    """Return only targets whose latest outcome is evidence-backed success."""
    return [
        outcome["target_id"]
        for outcome in (outcomes or {}).values()
        if outcome.get("status") == "succeeded" and outcome.get("target_id")
    ]
