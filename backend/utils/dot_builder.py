"""
Deterministic Graphviz DOT skeleton builder + validator (S4-T3).

Problem this closes: the Lead Hunter's attack-flow diagram used to be authored
entirely freehand by the LLM (see ``### 5. Attack Flow Diagram`` in
``backend/agents/lead_hunter_synthesis.py``), grounded only by a list of
label-only DOT edge lines that nothing validated. Two concrete failure modes
resulted:
  - Malformed DOT reaches the frontend's async `d3-graphviz` renderer, whose
    surrounding try/catch never fires (renderDot() is worker-based), so a bad
    diagram silently renders a blank panel.
  - Edges were keyed on *display labels* (``meaningful_name`` / ``host_name`` /
    ``last_final_url``), so two distinct entities could collapse into a single
    DOT node — and it also contradicted the prompt's own "show the full IOC,
    do not truncate" instruction.

Fix: the backend builds a complete, deterministic DOT skeleton keyed on the
graph's real (already-normalised, lowercase) entity ids. The LLM is asked to
*annotate* that skeleton (styling, clustering, edge-label wording) rather than
invent one. Whatever the LLM returns is parsed and validated against the
skeleton's own node/edge set; if it doesn't match, the skeleton itself is
substituted in as a deterministic fallback so the diagram is never blank or
inconsistent with the graph.

Pure Python + stdlib ``re`` — no new dependencies, and deliberately no import
from ``backend.agents.lead_hunter_synthesis`` (this module takes plain
dicts/lists so there is no risk of a circular import).
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Mirrors backend.agents.lead_hunter_synthesis.HIGH_SIGNAL_THREAT_SCORE.
# Redefined locally (not imported) to avoid a circular import between this
# module and lead_hunter_synthesis.py.
HIGH_SIGNAL_THREAT_SCORE = 60

MAX_VALIDATION_REASONS = 10

# Matches the first ```dot fenced block. Tolerates trailing horizontal
# whitespace on the info line and CRLF line endings — both occur in real LLM
# output, and a miss here is not benign: the frontend's markdown parser
# normalises them and would render the block anyway, so the backend would be
# validating nothing while unvalidated DOT reached d3-graphviz.
#
# The language tag stays lowercase-exact to match the frontend's own check
# (`match[1] === 'dot'` in app/src/app/investigate/[id]/page.tsx). A ```DOT or
# ```graphviz block is invisible to both, so falling back to appending a real
# ```dot block is the correct repair rather than something to paper over here.
_DOT_FENCE_RE = re.compile(r"```dot[ \t]*\r?\n(.*?)```", re.DOTALL)

# Extra ```dot blocks are retagged with this language instead of being deleted
# (see demote_extra_dot_blocks). NOT an empty info string: the frontend treats a
# fence with no language as *inline* code (`isInline = !match && !className`),
# so a whole diagram would render as one run-on span; a named language keeps it
# in the <pre> branch.
_DEMOTED_FENCE_LANG = "text"

# ---------------------------------------------------------------------------
# Skeleton construction
# ---------------------------------------------------------------------------

_SHAPE_BY_TYPE = {
    "file": "box",
    "domain": "ellipse",
    "ip_address": "box3d",
    "url": "note",
}

_FILLCOLOR_MALICIOUS = "lightcoral"
_FILLCOLOR_SUSPICIOUS = "orange"
_FILLCOLOR_BENIGN = "palegreen"
_FILLCOLOR_DEFAULT = "lightgray"


def _escape(value: Any) -> str:
    """Escape backslashes and double-quotes so the result is always safe to
    place inside a DOT double-quoted string. Backslash MUST be escaped first,
    otherwise the backslash introduced by quote-escaping would itself get
    re-escaped."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _collapse_label_whitespace(value: Any) -> str:
    """Flatten line/field breaks out of a display label.

    Display labels are attacker-chosen (``meaningful_name`` / ``last_final_url``
    / ``host_name``), and _escape only handles backslashes and quotes — a raw
    newline in a filename would therefore survive into the skeleton's
    ``label="..."`` and break the one-statement-per-line shape of the very block
    the LLM is asked to echo back verbatim, inviting a mangled re-emission that
    then fails validation.

    Mirrors ``_sanitise_label`` in lead_hunter_synthesis.py, reimplemented here
    rather than imported: this module deliberately depends on nothing in
    backend.agents (see the module docstring)."""
    text = str(value)
    for ch in ("\r\n", "\r", "\n", "\t"):
        text = text.replace(ch, " ")
    return text.strip()


def _unescape(value: str) -> str:
    """Inverse of _escape — used when parsing DOT text back into raw ids."""
    return value.replace('\\"', '"').replace("\\\\", "\\")


def _shape_for_type(entity_type: Optional[str]) -> str:
    return _SHAPE_BY_TYPE.get((entity_type or "").lower(), "box")


def _fillcolor_for(node: Dict[str, Any]) -> str:
    verdict = (node.get("verdict") or "").lower()
    score = node.get("score") or 0
    if verdict == "malicious" or score >= 80:
        return _FILLCOLOR_MALICIOUS
    if verdict == "suspicious" or score > HIGH_SIGNAL_THREAT_SCORE:
        return _FILLCOLOR_SUSPICIOUS
    if verdict == "benign":
        return _FILLCOLOR_BENIGN
    return _FILLCOLOR_DEFAULT


def build_dot_skeleton(
    node_details: Dict[str, Dict[str, Any]],
    diagram_edges: List[Dict[str, Any]],
    root_ioc: Optional[str],
) -> str:
    """
    Build a complete, deterministic ``digraph AttackChain { ... }`` from the
    investigation graph's already-scored node/edge data.

    Node declarations cover exactly the set of nodes referenced by
    ``diagram_edges``, plus ``root_ioc`` (if present in ``node_details``) even
    when it has no edges of its own. DOT node ids are always the entity's real
    graph id (``node_details[nid]["id"]``) — never a display label — so two
    distinct entities can never collapse into one DOT node.

    Deterministic: node declarations are sorted by id, so two calls over the
    same input produce byte-identical output.
    """
    node_ids: Set[str] = set()
    for edge in diagram_edges:
        node_ids.add(edge["source"])
        node_ids.add(edge["target"])
    if root_ioc and root_ioc in node_details:
        node_ids.add(root_ioc)

    lines = [
        "digraph AttackChain {",
        "  rankdir=TB;",
        "  center=true;",
        "  concentrate=true;",
        '  bgcolor="ghostwhite";',
        '  node [shape=box, style=filled, fillcolor=lightgray, fontname="Arial", fontsize=10];',
        '  edge [fontname="Arial", fontsize=9];',
        "",
    ]

    for nid in sorted(node_ids):
        node = node_details.get(nid, {})
        real_id = node.get("id", nid)
        entity_type = node.get("type", "unknown")
        display_label = node.get("label")

        label_lines = [
            _collapse_label_whitespace(entity_type).upper() or "UNKNOWN",
            _collapse_label_whitespace(real_id),
        ]
        display_label = _collapse_label_whitespace(display_label) if display_label else ""
        if display_label and display_label != label_lines[1]:
            label_lines.append(f"({display_label})")
        label_text = "\\n".join(_escape(part) for part in label_lines)

        attrs = [
            f"shape={_shape_for_type(entity_type)}",
            f"fillcolor={_fillcolor_for(node)}",
            f'label="{label_text}"',
        ]
        if root_ioc and nid == root_ioc:
            attrs.append("penwidth=3")

        lines.append(f'  "{_escape(nid)}" [{", ".join(attrs)}];')

    lines.append("")
    for edge in diagram_edges:
        src = _escape(edge["source"])
        tgt = _escape(edge["target"])
        rel = _escape(edge.get("relationship") or "related_to")
        lines.append(f'  "{src}" -> "{tgt}" [label="{rel}"];')

    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown fence helpers — must match the frontend's contract exactly
# (app/src/app/investigate/[id]/page.tsx matches on the ```dot language tag).
# ---------------------------------------------------------------------------


def extract_dot_block(markdown: str) -> Optional[str]:
    """Return the contents of the first ```dot fenced block, or None."""
    if not markdown:
        return None
    match = _DOT_FENCE_RE.search(markdown)
    if not match:
        return None
    # Strip \r as well as \n: with CRLF input the closing fence leaves a
    # trailing \r that would otherwise ride along into the validator.
    return match.group(1).rstrip("\r\n")


def replace_dot_block(markdown: str, dot: str) -> str:
    """
    Replace the first ```dot block's contents with ``dot``. If there is no
    such block, append a new "### 5. Attack Flow Diagram" section at the end
    so the diagram is never simply lost.
    """
    new_block = f"```dot\n{dot}\n```"
    if _DOT_FENCE_RE.search(markdown or ""):
        # Use a callable replacement (not a plain string) so re.sub never
        # interprets backslashes in `dot` (e.g. "\n" line breaks, "\"" escapes)
        # as backreference syntax — callable return values are inserted verbatim.
        return _DOT_FENCE_RE.sub(lambda _m: new_block, markdown, count=1)
    return f"{markdown}\n\n### 5. Attack Flow Diagram\n\n```dot\n{dot}\n```\n"


def demote_extra_dot_blocks(markdown: str) -> Tuple[str, int]:
    """
    Retag every ```dot block *after the first* as ```text, returning the
    rewritten markdown and the number of blocks demoted.

    extract_dot_block / validate_dot / replace_dot_block all act on the first
    fence only, but the frontend keys off the language tag, not the position
    (`match[1] === 'dot'`), and so hands EVERY dot block to d3-graphviz. A
    second block would therefore reach the renderer having been validated
    against nothing — precisely the failure this module exists to prevent — and
    a malformed one renders as a silent blank panel.

    Demoting rather than deleting keeps the report readable: the extra block is
    usually a partial or restated diagram that still carries prose value, and
    dropping content the model wrote is a bigger surprise than showing it as a
    code listing. Only the opening fence's language tag is rewritten; the body
    is carried through verbatim so backslashes in the DOT are untouched.
    """
    if not markdown:
        return markdown, 0

    seen = 0
    demoted = 0

    def _retag(match: re.Match) -> str:
        nonlocal seen, demoted
        seen += 1
        if seen == 1:
            return match.group(0)
        demoted += 1
        return f"```{_DEMOTED_FENCE_LANG}{match.group(0)[len('```dot'):]}"

    return _DOT_FENCE_RE.sub(_retag, markdown), demoted


# ---------------------------------------------------------------------------
# DOT structure parsing + validation
# ---------------------------------------------------------------------------

# HTML-like attribute values: label=<<B>x</B>>. Must be stripped before the
# generic key=value pass, whose value alternation doesn't cover angle brackets.
_HTML_VALUE_RE = re.compile(r"=\s*<(?:[^<>]|<[^>]*>)*>")
_BRACKET_ATTRS_RE = re.compile(r"\[[^\]]*\]", re.DOTALL)
_SUBGRAPH_NAME_RE = re.compile(
    r'\bsubgraph\b(?:\s+("(?:[^"\\]|\\.)*"|[A-Za-z_]\w*))?', re.IGNORECASE
)
_GRAPH_HEADER_RE = re.compile(
    r'\b(?:strict\s+)?(?:di)?graph\b(?:\s+("(?:[^"\\]|\\.)*"|[A-Za-z_]\w*))?',
    re.IGNORECASE,
)
# A DOT identifier: a quoted string, a bare alphanumeric/underscore name, or a
# numeral. Bare ids matter — a SHA-256 hash is a valid unquoted DOT id, so a
# parser that only sees quoted tokens can be bypassed entirely.
# Alternation order matters: the alnum-leading branch must come before the
# negative-numeral branch so a bare hex id ("44d88612fea8...") tokenises as one
# unit instead of splitting into "44" + the remainder. The trailing class
# deliberately excludes "-" so it can't swallow the "-" of an "->" edge op.
_ID = r'(?:"(?:[^"\\]|\\.)*"|[A-Za-z_0-9][\w.]*|-\.?\d[\d.]*)'
# Generic attribute assignment, e.g. rankdir=TB; bgcolor="ghostwhite";
# fontcolor="red". Deliberately NOT an allowlist of known attribute names: any
# unrecognised graph-level attribute whose value happened to be a quoted string
# used to leave a stray token behind that was then misread as a node id, which
# failed validation and silently discarded the LLM's whole annotation.
_ATTR_ASSIGNMENT_RE = re.compile(rf"{_ID}\s*=\s*{_ID}")
_EDGE_OP = r"(?:->|--)"
# An endpoint may carry a port and an optional compass point ("a":n -> "b":f:se).
# Without this the port tokenises as an identifier of its own, reads as an
# unknown node, and validate_dot silently discards the LLM's whole annotation.
# The suffix is matched only OUTSIDE the head token, so the colons inside a
# quoted URL id ("http://evil.example/p") are still part of the id. Whitespace
# around ":" is horizontal-only: allowing newlines would let a colon at the
# start of a line glue two unrelated statements into one bogus token.
_PORT = rf"(?:[ \t]*:[ \t]*{_ID}){{0,2}}"
_ID_PORT = rf"{_ID}{_PORT}"
_EDGE_CHAIN_RE = re.compile(rf"{_ID_PORT}(?:\s*{_EDGE_OP}\s*{_ID_PORT})+")
_ID_RE = re.compile(_ID)
_ID_PORT_RE = re.compile(_ID_PORT)
# Bare words that are DOT keywords, never node references. `node`/`edge`/`graph`
# survive as bare tokens once their `[...]` attribute list has been stripped.
_RESERVED_WORDS = {"node", "edge", "graph", "digraph", "subgraph", "strict"}


def _strip_comments(text: str) -> str:
    """
    Remove DOT comments (``/* */``, ``//``, ``#``) that are NOT inside a quoted
    string.

    This cannot be a regex. A URL entity id contains ``//``
    ("http://evil.example/p"), so a naive `//.*$` sweep eats the rest of the
    line, destroys the quote balance, and leaves fragments like `http` and
    ` -> ` that then read as invented node ids. The effect was that a skeleton
    containing any URL node failed to validate against *itself*, so every
    report with a URL in the diagram silently discarded the LLM's annotation
    and fell back to the bare skeleton. `contacted_urls` / `embedded_urls` /
    `urls` are all in triage's PRIORITY_RELATIONSHIPS, so that was most hunts.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            # Copy the quoted string verbatim, honouring backslash escapes.
            out.append(ch)
            i += 1
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    out.append(text[i:i + 2])
                    i += 2
                    continue
                out.append(text[i])
                i += 1
                if text[i - 1] == '"':
                    break
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
            continue
        if text.startswith("//", i) or ch == "#":
            end = text.find("\n", i)
            i = n if end == -1 else end
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _head_id(token: str) -> str:
    """Drop a ``:port[:compass]`` suffix, keeping the node id itself.

    Re-matching _ID against the head is what makes this quote-aware: a quoted id
    is consumed whole (colons inside it belong to the id), so only a colon that
    follows a *complete* token is treated as a port separator."""
    stripped = token.strip()
    match = _ID_RE.match(stripped)
    return match.group(0) if match else stripped


def _clean_id(raw: str) -> Optional[str]:
    """Normalise one parsed DOT identifier token, or None if it isn't a node ref."""
    token = raw.strip()
    if not token:
        return None
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        return _unescape(token[1:-1])
    if token.lower() in _RESERVED_WORDS:
        return None
    return token


def parse_dot_structure(dot: str) -> Tuple[Set[str], Set[Tuple[str, str]]]:
    """
    Extract the (node_ids, edges) referenced by a DOT document.

    Deliberately NOT a full DOT grammar parser, but it must be sound in BOTH
    directions, because each kind of mistake has a cost:
      - Missing a reference (false accept) lets the LLM smuggle an invented
        node or edge past validate_dot, defeating the point of grounding the
        diagram in the graph. Unquoted ids are the trap here: `evil_c2` and a
        bare hex hash are both legal unquoted DOT ids.
      - Inventing a reference (false reject) makes validate_dot fail on a
        perfectly good annotated diagram, so every report silently falls back
        to the bare skeleton and the annotation step is wasted.

    Strategy — strip everything that can legally contain arbitrary text, then
    read what's left as statements:
      1. Strip comments (``/* */``, ``//``, ``#``).
      2. Strip HTML-like values (``label=<<B>x</B>>``).
      3. Strip every ``[...]`` attribute list (labels live here).
      4. Strip ``digraph``/``subgraph`` header names so cluster names aren't
         read as nodes.
      5. Strip ``key=value`` attribute statements *generically* — no allowlist.
      6. In what remains, edge chains (``a -> b -> c``, including ``--``)
         contribute both their pairwise edges and their endpoints; any other
         surviving identifier is a standalone node declaration. Endpoints keep
         only their head id — a ``:port[:compass]`` suffix is not a node.
    """
    text = _strip_comments(dot or "")
    text = _HTML_VALUE_RE.sub(" ", text)
    text = _BRACKET_ATTRS_RE.sub(" ", text)
    text = _SUBGRAPH_NAME_RE.sub(" ", text)
    text = _GRAPH_HEADER_RE.sub(" ", text)
    text = _ATTR_ASSIGNMENT_RE.sub(" ", text)

    node_ids: Set[str] = set()
    edges: Set[Tuple[str, str]] = set()

    # Edge chains first, then blank them out so their endpoints aren't
    # re-counted by the standalone-declaration pass below.
    def _consume_chain(match: re.Match) -> str:
        chain = [_clean_id(_head_id(tok)) for tok in _ID_PORT_RE.findall(match.group(0))]
        chain = [c for c in chain if c is not None]
        for src, tgt in zip(chain, chain[1:]):
            edges.add((src, tgt))
        node_ids.update(chain)
        return " "

    text = _EDGE_CHAIN_RE.sub(_consume_chain, text)

    for token in _ID_PORT_RE.findall(text):
        cleaned = _clean_id(_head_id(token))
        if cleaned is not None:
            node_ids.add(cleaned)

    return node_ids, edges


def validate_dot(
    dot: str,
    allowed_nodes: Set[str],
    allowed_edges: Set[Tuple[str, str]],
    required_edges: Optional[Set[Tuple[str, str]]] = None,
) -> Tuple[bool, List[str]]:
    """
    Validate that ``dot`` references nothing outside the allowed sets, and — when
    ``required_edges`` is given — that it still contains everything it should.

    Fails if: there's no ``digraph`` header, braces are unbalanced, any
    referenced node id is not in ``allowed_nodes``, any referenced edge is not
    in ``allowed_edges``, or any edge in ``required_edges`` is absent.

    The completeness half matters as much as the soundness half. Without it,
    `digraph AttackChain { }` validates perfectly — it invents nothing — and the
    user gets a blank diagram, which is exactly the outcome the deterministic
    skeleton exists to prevent. Dropping the graph is as wrong as fabricating
    it, and the prompt already instructs the model to reproduce every node and
    edge, so requiring coverage doesn't forbid anything it was allowed to do.
    Falling back to the skeleton on a partial answer is the safe direction: the
    reader still gets a complete, correct diagram, just without the annotation.

    Comparisons are case-insensitive (graph entity ids are normalised
    lowercase, but the LLM may re-case them when echoing them back).
    ``reasons`` is capped at MAX_VALIDATION_REASONS entries.
    """
    reasons: List[str] = []

    if not dot or not re.search(r"\bdigraph\b", dot, re.IGNORECASE):
        reasons.append("missing 'digraph' header")

    open_braces = dot.count("{") if dot else 0
    close_braces = dot.count("}") if dot else 0
    if open_braces != close_braces or open_braces == 0:
        reasons.append(
            f"unbalanced braces: {open_braces} '{{' vs {close_braces} '}}'"
        )

    try:
        node_ids, edges = parse_dot_structure(dot)
    except Exception as e:  # pragma: no cover - defensive, regexes shouldn't raise
        reasons.append(f"failed to parse dot structure: {e}")
        node_ids, edges = set(), set()

    allowed_nodes_lower = {str(n).lower() for n in allowed_nodes}
    allowed_edges_lower = {(str(s).lower(), str(t).lower()) for s, t in allowed_edges}

    for nid in sorted(node_ids):
        if len(reasons) >= MAX_VALIDATION_REASONS:
            break
        if nid.lower() not in allowed_nodes_lower:
            reasons.append(f"unknown node referenced: {nid}")

    for src, tgt in sorted(edges):
        if len(reasons) >= MAX_VALIDATION_REASONS:
            break
        if (src.lower(), tgt.lower()) not in allowed_edges_lower:
            reasons.append(f"unknown edge referenced: {src} -> {tgt}")

    if required_edges:
        present = {(s.lower(), t.lower()) for s, t in edges}
        missing = sorted(
            (s, t) for s, t in required_edges
            if (str(s).lower(), str(t).lower()) not in present
        )
        if missing:
            reasons.append(
                f"dropped {len(missing)} of {len(required_edges)} required edges"
            )
            for src, tgt in missing:
                if len(reasons) >= MAX_VALIDATION_REASONS:
                    break
                reasons.append(f"missing required edge: {src} -> {tgt}")

    return (len(reasons) == 0), reasons[:MAX_VALIDATION_REASONS]
