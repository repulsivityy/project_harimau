import json
import shodan

from ..server import server, get_shodan_client


def _extract_service(svc: dict) -> dict:
    """Extract selected fields from a single service entry."""
    entry = {
        "port": svc.get("port"),
        "transport": svc.get("transport"),
        "product": svc.get("product"),
        "version": svc.get("version"),
        "cpe23": svc.get("cpe23", []),
        "banner": svc.get("data", "")[:300],
        "os": svc.get("os"),
        "vulns": list(svc.get("opts", {}).get("vulns", [])) or None,
    }

    # SSL/TLS
    ssl = svc.get("ssl")
    if ssl:
        cert = ssl.get("cert", {})
        entry["ssl"] = {
            "subject_cn": cert.get("subject", {}).get("CN"),
            "issuer_cn": cert.get("issuer", {}).get("CN"),
            "fingerprint_sha256": cert.get("fingerprint", {}).get("sha256"),
            "jarm": ssl.get("jarm"),
            "ja3s": ssl.get("ja3s"),
        }

    # HTTP
    http = svc.get("http")
    if http:
        entry["http"] = {
            "status": http.get("status"),
            "title": http.get("title"),
            "server": http.get("server"),
            "components": list(http.get("components", {}).keys()) or None,
            "redirects": [r.get("location") for r in http.get("redirects", []) if r.get("location")] or None,
            "favicon_hash": http.get("favicon", {}).get("hash") if http.get("favicon") else None,
        }

    # SSH
    ssh = svc.get("ssh")
    if ssh:
        entry["ssh"] = {
            "fingerprint": ssh.get("fingerprint"),
            "hassh": ssh.get("hassh"),
        }

    # FTP
    ftp = svc.get("ftp")
    if ftp:
        entry["ftp"] = {
            "anonymous": ftp.get("anonymous"),
            "supported_commands": list(ftp.get("features", {}).keys()) or None,
        }

    # DNS
    dns = svc.get("dns")
    if dns:
        entry["dns"] = {
            "recursive": dns.get("recursive"),
            "resolver_id": dns.get("resolver_id"),
        }

    return entry


@server.tool()
def ip_lookup(ip: str) -> str:
    """
    Look up a host by IP address using Shodan.
    Returns org, hostnames, open ports, tags, and per-service details including
    SSL/TLS certificates, HTTP metadata, SSH fingerprints, FTP config, DNS info,
    and known vulnerabilities.
    """
    api = get_shodan_client()
    try:
        host = api.host(ip)
        result = {
            "ip": host.get("ip_str"),
            "org": host.get("org"),
            "hostnames": host.get("hostnames", []),
            "domains": host.get("domains", []),
            "ports": host.get("ports", []),
            "tags": host.get("tags", []),
            "last_update": host.get("last_update"),
            "os": host.get("os"),
            "services": [_extract_service(svc) for svc in host.get("data", [])],
        }
        return json.dumps(result, indent=2)
    except shodan.APIError as e:
        return json.dumps({"error": str(e)})


@server.tool()
def shodan_search(query: str, limit: int = 10) -> str:
    """
    Search Shodan for internet-connected devices matching the query.
    Supports Shodan search filters (e.g. 'apache port:443 country:MY').
    Returns matched hosts with IP, ports, services, org, and banners.
    """
    api = get_shodan_client()
    try:
        results = api.search(query, limit=limit)
        output = {
            "total": results.get("total", 0),
            "returned": len(results.get("matches", [])),
            "matches": [
                {
                    "ip": match.get("ip_str"),
                    "port": match.get("port"),
                    "transport": match.get("transport"),
                    "org": match.get("org"),
                    "isp": match.get("isp"),
                    "asn": match.get("asn"),
                    "country": match.get("location", {}).get("country_name"),
                    "city": match.get("location", {}).get("city"),
                    "hostnames": match.get("hostnames", []),
                    "domains": match.get("domains", []),
                    "product": match.get("product"),
                    "version": match.get("version"),
                    "cpe": match.get("cpe", []),
                    "banner": match.get("data", "")[:300],
                }
                for match in results.get("matches", [])
            ],
        }
        return json.dumps(output, indent=2)
    except shodan.APIError as e:
        return json.dumps({"error": str(e)})
