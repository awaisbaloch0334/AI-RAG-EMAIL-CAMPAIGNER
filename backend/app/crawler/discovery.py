from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse
from typing import List, Set
from bs4 import BeautifulSoup


IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".css", ".js", ".mjs",
    ".pdf", ".doc", ".docx", ".zip", ".tar", ".gz", ".rar",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".xml", ".json", ".txt",
}

STRIPPED_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "source",
}


def normalize_domain(netloc: str) -> str:
    """Normalize domain by lowercasing and stripping default port and www prefix."""
    domain = netloc.lower().split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs belong to the same website domain."""
    d1 = normalize_domain(urlparse(url1).netloc)
    d2 = normalize_domain(urlparse(url2).netloc)
    return d1 == d2 and bool(d1)


def normalize_url(url: str) -> str:
    """
    Normalize URL:
    - Strips fragment identifiers.
    - Lowers scheme and netloc.
    - Removes common tracking query parameters.
    - Standardizes trailing slashes.
    """
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Remove trailing slash unless it's just the root
        path = parsed.path
        if path.endswith("/") and len(path) > 1:
            path = path[:-1]
        elif not path:
            path = "/"

        # Filter query params
        qs = parse_qs(parsed.query, keep_blank_values=False)
        cleaned_qs = {k: v for k, v in qs.items() if k.lower() not in STRIPPED_PARAMS}
        query = urlencode(cleaned_qs, doseq=True)

        return urlunparse((scheme, netloc, path, parsed.params, query, ""))
    except Exception:
        return url


def is_crawlable_page(url: str, base_url: str) -> bool:
    """Determine if a URL is a legitimate same-domain content page."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False

    if not is_same_domain(url, base_url):
        return False

    path_lower = parsed.path.lower()
    for ext in IGNORED_EXTENSIONS:
        if path_lower.endswith(ext):
            return False

    return True


def extract_links(html: str, base_url: str) -> Set[str]:
    """
    Extract and normalize all same-domain navigation links from HTML content.
    """
    discovered: Set[str] = set()
    soup = BeautifulSoup(html, "html.parser")

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        resolved = urljoin(base_url, href)
        normalized = normalize_url(resolved)

        if is_crawlable_page(normalized, base_url):
            discovered.add(normalized)

    return discovered

