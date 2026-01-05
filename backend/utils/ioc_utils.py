"""
IOC Utility Functions
"""

import re
from urllib.parse import urlparse


def classify_ioc_type(ioc: str) -> str:
    """
    Determine IOC type from string pattern.
    
    Args:
        ioc: The IOC string
    
    Returns:
        IOC type: "file", "ip", "domain", or "url"
    """
    
    # File hash patterns
    if re.match(r'^[a-fA-F0-9]{32}$', ioc):  # MD5
        return "file"
    if re.match(r'^[a-fA-F0-9]{40}$', ioc):  # SHA1
        return "file"
    if re.match(r'^[a-fA-F0-9]{64}$', ioc):  # SHA256
        return "file"
    
    # IP address pattern
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ioc):
        return "ip"
    
    # URL pattern
    if ioc.startswith(("http://", "https://")):
        return "url"
    
    # Default to domain
    return "domain"


def extract_domain_from_url(url: str) -> str:
    """
    Extract domain from URL.
    
    Args:
        url: URL string
    
    Returns:
        Domain or empty string if extraction fails
    """
    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except:
        return ""


def is_valid_hash(hash_value: str, hash_type: str = "sha256") -> bool:
    """
    Validate hash format.
    
    Args:
        hash_value: Hash string
        hash_type: Hash type ("md5", "sha1", "sha256")
    
    Returns:
        True if valid format, False otherwise
    """
    patterns = {
        "md5": r'^[a-fA-F0-9]{32}$',
        "sha1": r'^[a-fA-F0-9]{40}$',
        "sha256": r'^[a-fA-F0-9]{64}$'
    }
    
    pattern = patterns.get(hash_type.lower())
    if not pattern:
        return False
    
    return bool(re.match(pattern, hash_value))


def is_valid_ip(ip: str) -> bool:
    """
    Validate IPv4 address format.
    
    Args:
        ip: IP address string
    
    Returns:
        True if valid IPv4, False otherwise
    """
    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
        return False
    
    # Check octets are 0-255
    octets = ip.split('.')
    return all(0 <= int(octet) <= 255 for octet in octets)


def truncate_ioc(ioc: str, max_length: int = 50) -> str:
    """
    Truncate IOC for display purposes.
    
    Args:
        ioc: IOC string
        max_length: Maximum length
    
    Returns:
        Truncated IOC with ellipsis if needed
    """
    if len(ioc) <= max_length:
        return ioc
    
    return ioc[:max_length-3] + "..."
