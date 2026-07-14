"""
Post-synthesis IOC validation.

The Lead Hunter's final report is LLM-generated prose. Even with graph-grounded
edge tuples, nothing verifies that the IOCs it *cites* actually exist in the
investigation. This module extracts every IOC-shaped token from the report and
checks it against the known universe (NetworkX graph + specialist indicator lists).

Design decision: ANNOTATE, don't strip. Silently removing IOCs from a report is
worse than flagging them, and stripping mid-sentence breaks the Markdown.
"""

import re
from typing import Any, Dict, List, Optional

from backend.utils.graph_cache import InvestigationCache, _normalise_id
from backend.utils.logger import get_logger

logger = get_logger("report_validator")

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
# Order matters for reporting only; each is matched independently.
IOC_PATTERNS = {
    "sha256": re.compile(r"\b[a-fA-F0-9]{64}\b"),
    "sha1":   re.compile(r"\b[a-fA-F0-9]{40}\b"),
    "md5":    re.compile(r"\b[a-fA-F0-9]{32}\b"),
    "ipv4":   re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    # Deliberately permissive; heavily post-filtered below.
    "domain": re.compile(r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,24}\b"),
}

# Fenced code blocks and inline code often contain file paths, module names,
# and version strings that look like IOCs. Strip them before matching.
_FENCED_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_GRAPHVIZ_BLOCK = re.compile(r"(?:digraph|graph)\s+\w*\s*\{.*?\}", re.DOTALL)

# Extensions/suffixes that the domain regex will falsely match.
NON_TLD_SUFFIXES = {
    # source files
    "py", "js", "ts", "tsx", "jsx", "go", "rs", "rb", "java", "c", "h", "cpp",
    "sh", "yaml", "yml", "json", "toml", "ini", "cfg", "md", "txt", "csv",
    # windows/pe artefacts that appear constantly in malware reports
    "exe", "dll", "sys", "bat", "cmd", "ps1", "vbs", "scr", "ocx", "cpl",
    "msi", "lnk", "hta", "jar", "bin", "tmp", "dat", "log", "pdb",
    # archives / docs
    "zip", "rar", "7z", "gz", "tar", "iso", "img", "doc", "docx", "xls",
    "xlsx", "ppt", "pptx", "pdf", "rtf",
}

# Cross-agent handoff prefixes: "File:abc123", "IP:1.2.3.4", "Domain:evil.com"
_PREFIXED = re.compile(r"^(?:file|ip|domain|url|hash|md5|sha1|sha256)\s*:\s*", re.IGNORECASE)


def _refang(text: str) -> str:
    """Reports frequently defang IOCs. Normalise before matching."""
    return (
        text.replace("[.]", ".")
        .replace("(.)", ".")
        .replace("[dot]", ".")
        .replace("hxxps", "https")
        .replace("hxxp", "http")
        .replace("[:]", ":")
        .replace("[@]", "@")
    )


def _strip_code(text: str) -> str:
    """Remove fenced blocks and graphviz DOT bodies before IOC extraction."""
    text = _FENCED_BLOCK.sub(" ", text)
    text = _GRAPHVIZ_BLOCK.sub(" ", text)
    return text


def _valid_ipv4(value: str) -> bool:
    """Reject version strings like 10.2.1.300 and 1.2.3.4567."""
    parts = value.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or len(p) > 3:
            return False
        if int(p) > 255:
            return False
    return True


def _plausible_domain(value: str) -> bool:
    """Reject filenames, module paths, and version-ish tokens."""
    suffix = value.rsplit(".", 1)[-1].lower()
    if suffix in NON_TLD_SUFFIXES:
        return False
    if suffix.isdigit():
        return False
    # A bare two-label token whose left side is numeric is almost always a version.
    labels = value.split(".")
    if all(lab.isdigit() for lab in labels[:-1]):
        return False
    return True


def _strip_prefix(indicator: str) -> str:
    """Turn 'File:abc123' into 'abc123'."""
    return _PREFIXED.sub("", indicator.strip())


def build_known_universe(
    cache: InvestigationCache,
    specialist_results: Dict[str, Any],
    root_ioc: str,
) -> set:
    """
    Every identifier the investigation legitimately observed:
      - all NetworkX graph nodes
      - the root IOC
      - specialist network_indicators / related_indicators (prefix-stripped)
      - specialist analyzed_targets
    """
    known = set()

    for node_id in cache.graph.nodes():
        norm = _normalise_id(node_id)
        if norm:
            known.add(norm)

    root = _normalise_id(root_ioc)
    if root:
        known.add(root)

    for res in (specialist_results or {}).values():
        if not isinstance(res, dict):
            continue
        for field in ("network_indicators", "related_indicators"):
            for ind in res.get(field, []) or []:
                if not isinstance(ind, str):
                    continue
                norm = _normalise_id(_strip_prefix(ind))
                if norm:
                    known.add(norm)
        for target in res.get("analyzed_targets", []) or []:
            value = (
                target.get("indicator") or target.get("value")
                if isinstance(target, dict) else target
            )
            norm = _normalise_id(_strip_prefix(str(value))) if value else None
            if norm:
                known.add(norm)

    return known


def validate_report_iocs(
    report_md: str,
    cache: InvestigationCache,
    specialist_results: Dict[str, Any],
    root_ioc: str,
) -> Dict[str, Any]:
    """
    Returns {"unverified": [{"type","value"}], "verified": int, "extracted": int}.
    Pure function — does not mutate the report.
    """
    if not report_md:
        return {"unverified": [], "verified": 0, "extracted": 0}

    known = build_known_universe(cache, specialist_results, root_ioc)
    text = _refang(_strip_code(report_md))

    unverified: List[Dict[str, str]] = []
    seen: set = set()
    verified = 0
    extracted = 0

    for ioc_type, pattern in IOC_PATTERNS.items():
        for match in pattern.findall(text):
            if ioc_type == "ipv4" and not _valid_ipv4(match):
                continue
            if ioc_type == "domain" and not _plausible_domain(match):
                continue

            norm = _normalise_id(match)
            if not norm:
                continue

            extracted += 1
            if norm in known:
                verified += 1
                continue

            # A hash may be cited by a different case, or a domain may be a
            # subdomain of a known node. Substring containment on the graph is
            # too loose, so we only accept exact normalised matches.
            if norm in seen:
                continue
            seen.add(norm)
            unverified.append({"type": ioc_type, "value": match})

    return {"unverified": unverified, "verified": verified, "extracted": extracted}


def annotate_report(report_md: str, validation: Dict[str, Any]) -> str:
    """Append a validation footer if any IOC failed verification."""
    unverified = validation.get("unverified", [])
    if not unverified:
        return report_md

    lines = "\n".join(
        f"- `{item['value']}` ({item['type']})" for item in unverified
    )
    return (
        f"{report_md}\n\n---\n\n### ⚠️ Validation Notice\n\n"
        f"The following indicators appear in this report but were **not observed** "
        f"in the investigation graph or specialist findings. Treat them as "
        f"**unverified** and do not action them without independent confirmation:\n\n"
        f"{lines}\n"
    )


def validate_and_annotate(
    report_md: str,
    cache: InvestigationCache,
    specialist_results: Dict[str, Any],
    root_ioc: str,
    job_id: Optional[str] = None,
) -> str:
    """Convenience wrapper used by lead_hunter.py. Never raises."""
    try:
        validation = validate_report_iocs(report_md, cache, specialist_results, root_ioc)
        if validation["unverified"]:
            logger.warning(
                "report_iocs_unverified",
                job_id=job_id,
                unverified_count=len(validation["unverified"]),
                verified_count=validation["verified"],
                extracted_count=validation["extracted"],
                samples=[i["value"] for i in validation["unverified"][:5]],
            )
        else:
            logger.info(
                "report_iocs_all_verified",
                job_id=job_id,
                verified_count=validation["verified"],
            )
        return annotate_report(report_md, validation)
    except Exception as e:
        logger.error("report_validation_failed", job_id=job_id, error=str(e))
        return report_md  # never block the report on a validator bug

