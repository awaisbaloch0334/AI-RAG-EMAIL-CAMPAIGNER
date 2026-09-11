import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple, Optional


DISALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "169.254.169.254",
}


def is_safe_ip(ip_str: str) -> bool:
    """
    Check if an IP address is safe to connect to.
    Rejects private, loopback, link-local, multicast, and reserved addresses.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return False


def is_safe_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a URL is safe against SSRF attacks before requesting it.
    Returns (is_safe, error_reason).
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Malformed URL: {str(e)}"

    if parsed.scheme not in ("http", "https"):
        return False, f"Disallowed URL scheme '{parsed.scheme}'. Only http and https are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL missing hostname."

    hostname_lower = hostname.lower()
    if hostname_lower in DISALLOWED_HOSTS:
        return False, f"Requests to '{hostname}' are blocked for security."

    # Resolve hostname to IP to protect against DNS rebinding & local resolution
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for entry in addr_info:
            ip_addr = entry[4][0]
            if not is_safe_ip(ip_addr):
                return False, f"Hostname resolves to blocked IP address '{ip_addr}'."
    except socket.gaierror as e:
        return False, f"Could not resolve hostname '{hostname}': {str(e)}"
    except Exception as e:
        return False, f"DNS resolution failed: {str(e)}"

    return True, None


def validate_url(url: str) -> str:
    """
    Validate URL safety or raise ValueError if unsafe.
    Returns sanitized URL.
    """
    safe, reason = is_safe_url(url)
    if not safe:
        raise ValueError(f"SSRF Protection Error: {reason}")
    return url.strip()

