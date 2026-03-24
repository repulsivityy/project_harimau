import json
import requests

from ..server import server

CVEDB_BASE = "https://cvedb.shodan.io"


@server.tool()
def cve_lookup(cve_id: str) -> str:
    """
    Fetch detailed vulnerability information for a CVE ID from Shodan CVEDB.
    Returns CVSS scores, EPSS score, affected products/CPEs, references, and summary.
    Example: cve_id='CVE-2021-44228'
    """
    try:
        resp = requests.get(f"{CVEDB_BASE}/cve/{cve_id}", timeout=10)
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except requests.RequestException as e:
        return json.dumps({"error": str(e)})


@server.tool()
def cves_by_product(cpe23: str, skip: int = 0, limit: int = 10) -> str:
    """
    Find CVEs affecting a specific product identified by its CPE 2.3 string.
    Example: cpe23='cpe:2.3:a:apache:log4j:2.14.1:*:*:*:*:*:*:*'
    Returns a list of CVEs with severity scores sorted by EPSS score.
    """
    try:
        resp = requests.get(
            f"{CVEDB_BASE}/cves",
            params={"cpe23": cpe23, "skip": skip, "count": limit},
            timeout=10,
        )
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except requests.RequestException as e:
        return json.dumps({"error": str(e)})


@server.tool()
def cpe_lookup(product: str, skip: int = 0, limit: int = 10) -> str:
    """
    Search for Common Platform Enumeration (CPE) entries by product name.
    Useful for finding the correct CPE string to use with cves_by_product.
    Example: product='log4j'
    """
    try:
        resp = requests.get(
            f"{CVEDB_BASE}/cpes",
            params={"product": product, "skip": skip, "count": limit},
            timeout=10,
        )
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except requests.RequestException as e:
        return json.dumps({"error": str(e)})
