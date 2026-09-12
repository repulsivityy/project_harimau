"""Canonical, type-aware identities for investigation entities.

Graph keys, specialist lifecycle state and GTI tool calls must name the same
IOC.  Generic lowercasing is correct for hashes, IPs and domains, but corrupts
the path/query portion of a URL.  URL graph keys are therefore canonical URLs
(lowercase scheme and host only), never GTI's opaque base64 URL object id.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit


URL_ENTITY_TYPE = "url"
_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_BASE64_URL_ID_RE = re.compile(r"^[A-Za-z0-9_+/-]+$")


def is_http_url(value: Any) -> bool:
    """Return whether *value* is an HTTP(S) URL, without modifying it."""
    return isinstance(value, str) and bool(_HTTP_URL_RE.match(value.strip()))


def normalise_url(value: Any) -> Optional[str]:
    """Canonicalise only the case-insensitive URL components.

    URL paths, queries, fragments and user-info are deliberately retained
    byte-for-byte.  Changing their case can refer to another resource and
    would make a hunt target the wrong IOC.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or not is_http_url(raw):
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    if not parts.hostname:
        return raw

    # ``netloc`` may contain case-sensitive user-info and an IPv6 literal.
    # Lowercase only the host part, retaining user-info and an explicit port.
    userinfo, separator, hostport = parts.netloc.rpartition("@")
    prefix = f"{userinfo}@" if separator else ""
    if hostport.startswith("["):
        closing = hostport.find("]")
        host = hostport[: closing + 1].lower() if closing >= 0 else hostport.lower()
        suffix = hostport[closing + 1 :] if closing >= 0 else ""
    else:
        host, colon, port = hostport.rpartition(":")
        if not colon or ":" in host:  # no port, or an unbracketed IPv6 literal
            host, suffix = hostport.lower(), ""
        else:
            host, suffix = host.lower(), f":{port}"
    return urlunsplit((parts.scheme.lower(), f"{prefix}{host}{suffix}", parts.path, parts.query, parts.fragment))


def gti_url_id(url: Any) -> Optional[str]:
    """Return GTI's unpadded base64url object id for a canonical raw URL."""
    canonical = normalise_url(url)
    if not canonical:
        return None
    return base64.urlsafe_b64encode(canonical.encode("utf-8")).decode("ascii").rstrip("=")


def raw_url_from_gti_id(value: Any) -> Optional[str]:
    """Decode a GTI URL id only when it unambiguously represents an HTTP URL."""
    if value is None:
        return None
    encoded = str(value).strip()
    if not encoded or not _BASE64_URL_ID_RE.fullmatch(encoded):
        return None
    try:
        padding = "=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(encoded.replace("+", "-").replace("/", "_") + padding).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None
    return normalise_url(decoded)


def normalise_entity_id(value: Any, entity_type: Optional[str] = None) -> Optional[str]:
    """Return the graph/lifecycle identity for a file, IP, domain or URL.

    A GTI URL object id is decoded only if it round-trips to an HTTP(S) URL;
    opaque URL ids that cannot be decoded stay explicitly namespaced so they
    cannot collide with a raw IOC or be case-folded accidentally.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    is_url_type = str(entity_type or "").strip().lower() == URL_ENTITY_TYPE
    if is_url_type or is_http_url(raw):
        if is_url_type and raw.startswith("gti-url:"):
            return raw
        canonical = normalise_url(raw)
        if canonical:
            return canonical
        decoded = raw_url_from_gti_id(raw) if is_url_type else None
        return decoded or (f"gti-url:{raw}" if is_url_type else raw.lower())
    return raw.lower()


def normalise_target_id(value: Any) -> Optional[str]:
    """Target identity with punctuation trimming only for non-URL prose IOCs."""
    if value is None:
        return None
    raw = str(value).strip()
    # A final ``.``, ``,`` or ``;`` can be a legitimate URL path/query value.
    # Do not make a different resource look like a prose-punctuation variant.
    if is_http_url(raw):
        return normalise_entity_id(raw)
    raw = raw.strip(".,;:")
    return normalise_entity_id(raw)
