import json
import shodan

from ..server import server, get_shodan_client


@server.tool()
def dns_lookup(hostnames: str) -> str:
    """
    Resolve one or more hostnames to IP addresses using Shodan DNS.
    Accepts a single hostname or a comma-separated list (e.g. 'example.com,evil.io').
    Returns a mapping of hostname -> IP address.
    """
    api = get_shodan_client()
    try:
        hostname_list = [h.strip() for h in hostnames.split(",") if h.strip()]
        result = api.dns.resolve(hostname_list)
        return json.dumps(result, indent=2)
    except shodan.APIError as e:
        return json.dumps({"error": str(e)})


@server.tool()
def reverse_dns_lookup(ips: str) -> str:
    """
    Perform reverse DNS lookup for one or more IP addresses using Shodan.
    Accepts a single IP or a comma-separated list (e.g. '1.1.1.1,8.8.8.8').
    Returns a mapping of IP -> list of hostnames.
    """
    api = get_shodan_client()
    try:
        ip_list = [ip.strip() for ip in ips.split(",") if ip.strip()]
        result = api.dns.reverse(ip_list)
        return json.dumps(result, indent=2)
    except shodan.APIError as e:
        return json.dumps({"error": str(e)})
