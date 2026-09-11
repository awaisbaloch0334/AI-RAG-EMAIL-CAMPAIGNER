import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment


BOILERPLATE_TAGS = {
    "script", "style", "noscript", "iframe", "svg",
    "nav", "aside", "footer",
}

BOILERPLATE_SELECTORS = [
    ".cookie", ".cookies", ".cookie-banner", "#cookie-banner",
    ".consent", "#consent", ".popup", "#popup",
    ".advertisement", ".ad", ".social-share",
]


@dataclass
class ExtractedPageData:
    url: str
    title: Optional[str] = None
    site_name: Optional[str] = None
    clean_text: str = ""
    content_hash: str = ""
    headings: List[str] = field(default_factory=list)
    images: List[Dict[str, str]] = field(default_factory=list)
    theme_color: Optional[str] = None
    favicon_url: Optional[str] = None


class ContentExtractor:
    @staticmethod
    def extract(html: str, url: str) -> ExtractedPageData:
        """
        Parse raw HTML and extract clean, structured page knowledge while stripping boilerplate.
        Preserves critical company contact info, physical locations, and footer knowledge.
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. Extract Page Title & Site Name
        title = None
        site_name = None
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            site_name = og_site["content"].strip()

        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.h1:
            title = soup.h1.get_text().strip()

        # 2. Extract Headings before stripping
        headings: List[str] = []
        for h in soup.find_all(["h1", "h2", "h3"]):
            text = h.get_text(strip=True)
            if text and text not in headings:
                headings.append(text)

        # 3. Extract Favicon & Theme Color
        favicon_url = None
        icon_tag = soup.find("link", rel=lambda r: r and any(k in str(r).lower() for k in ["icon", "apple-touch-icon"]))
        if icon_tag and icon_tag.get("href"):
            favicon_url = urljoin(url, icon_tag["href"].strip())

        theme_color = None
        meta_theme = soup.find(
            "meta",
            attrs={"name": re.compile(r"^(theme-color|msapplication-TileColor|msapplication-navbutton-color)$", re.I)}
        )
        if meta_theme and meta_theme.get("content"):
            c = meta_theme["content"].strip()
            if re.match(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", c):
                if len(c) == 4:
                    c = f"#{c[1]*2}{c[2]*2}{c[3]*2}"
                theme_color = c.upper()
            elif "rgb" in c.lower():
                m = re.search(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", c)
                if m:
                    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    if not (r == g == b):
                        theme_color = f"#{r:02x}{g:02x}{b:02x}".upper()

        # 4. Extract Images (with full lazy-loading unpacking and logo classification)
        images: List[Dict[str, Any]] = []
        for img in soup.find_all("img"):
            # Unpack real source from lazy-loading attributes first
            raw_src = (
                img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("data-original")
                or img.get("data-orig-file")
                or img.get("src")
                or ""
            ).strip()

            # If still empty or a base64 data-URI placeholder, check srcset / data-srcset
            if not raw_src or raw_src.startswith("data:image/"):
                srcset = img.get("data-srcset") or img.get("srcset") or ""
                if srcset:
                    candidates = [c.strip().split()[0] for c in srcset.split(",") if c.strip()]
                    for c in candidates:
                        if c and not c.startswith("data:"):
                            raw_src = c
                            break

            # Reject empty, data URI placeholders, and dummy/blank placeholder images
            dummy_markers = ["data:image/", "no-image", "no_image", "noimage", "placeholder", "dummy", "blank.gif", "spacer.gif", "default-image"]
            if not raw_src or any(marker in raw_src.lower() for marker in dummy_markers):
                continue

            abs_url = urljoin(url, raw_src)
            alt = img.get("alt", "").strip()
            cls_name = " ".join(img.get("class", [])) if isinstance(img.get("class"), list) else str(img.get("class", ""))
            img_id = img.get("id", "")

            # If this is a Shopify CDN image with thumbnail sizing (e.g. _80x.png or _80x@2x.png), derive high-res master URL
            high_res_url = re.sub(r"_\d+x(\@2x)?(\.[a-zA-Z0-9]+)", r"\2", abs_url)

            # Classify if image is a brand logo based on attributes and ancestor context
            parent = img.parent
            grandparent = parent.parent if parent else None
            ancestor_context = " ".join(
                filter(None, [
                    cls_name,
                    img_id,
                    alt,
                    abs_url,
                    " ".join(parent.get("class", [])) if parent and isinstance(parent.get("class"), list) else str(parent.get("class", "") if parent else ""),
                    str(parent.get("id", "") if parent else ""),
                    str(grandparent.get("class", "") if grandparent else ""),
                    str(grandparent.get("id", "") if grandparent else ""),
                ])
            ).lower()

            is_logo = any(k in ancestor_context for k in [
                "site-logo", "theme-site-logo", "custom-logo", "header-logo",
                "brand-logo", "navbar-brand", "header__heading-logo", "site-title"
            ])
            if not is_logo and "logo" in ancestor_context:
                # Exclude third-party partner/payment/social logos
                if not any(bad in ancestor_context for bad in [
                    "google", "clutch", "trustpilot", "stripe", "visa", "partner", "client", "customer",
                    "instagram", "tiktok", "facebook", "twitter", "linkedin", "youtube", "social"
                ]):
                    is_logo = True

            # If inside header or nav, inside an anchor linking strictly to homepage
            if not is_logo and parent and parent.name == "a":
                href = (parent.get("href") or "").strip()
                if href in ("/", url, url.rstrip("/") + "/", ""):
                    if any(a.name in ("header", "nav") for a in img.parents):
                        parent_cls = " ".join(parent.get("class", [])).lower()
                        if any(k in parent_cls for k in ["brand", "heading-link", "logo", "site-logo"]):
                            is_logo = True

            final_logo_url = high_res_url if is_logo else abs_url
            images.append({
                "url": final_logo_url,
                "src": final_logo_url,
                "alt": alt,
                "class": cls_name,
                "id": img_id,
                "is_logo": is_logo,
            })

        # 5. Extract Structured Contact & Location Information before boilerplate cleanup
        contact_lines: List[str] = []
        # Extract mailto & tel links
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip()
                item = f"Email: {email}"
                if item not in contact_lines:
                    contact_lines.append(item)
            elif href.startswith("tel:"):
                phone = href.replace("tel:", "").strip()
                item = f"Phone: {phone}"
                if item not in contact_lines:
                    contact_lines.append(item)

        # Extract address & office locations specifically from footer, address tags, and contact sections
        address_regex = re.compile(
            r"\b(street|st\b|ste\b|suite|road|rd\b|avenue|ave\b|blvd|boulevard|lane|ln\b|drive|dr\b|"
            r"floor|building|bldg|villas|tower|headquarters|postal|zip code|"
            r"multan|lahore|karachi|islamabad|punjab|pakistan|london|"
            r"delaware|california|texas|florida|wyoming|new york|united states|usa\b|uk\b)\b",
            re.IGNORECASE,
        )

        contact_containers = []
        for tag in soup.find_all(["footer", "address"]):
            contact_containers.append(tag)
        for tag in soup.find_all(["section", "div"]):
            cls_or_id = (tag.get("id", "") + " " + " ".join(tag.get("class", []))).lower()
            if any(k in cls_or_id for k in ["contact", "footer", "location", "address"]):
                contact_containers.append(tag)

        for container in contact_containers:
            for child in container.find_all(["address", "p", "div", "span", "li"]):
                # Inspect leaf elements with concise text
                if not child.find(["p", "div", "span", "address"]):
                    txt = child.get_text(separator=" ", strip=True)
                    if txt and 5 < len(txt) < 160:
                        if child.name == "address" or address_regex.search(txt):
                            # Skip long marketing slogans or headers that happen to mention a country or word
                            if not any(stop in txt.lower() for stop in ["we deliver", "disorganized", "we analyze", "thousands saved", "turn those roadblocks"]):
                                entry = f"Office Location / Address: {txt}"
                                if entry not in contact_lines:
                                    contact_lines.append(entry)
                        elif re.search(r"(\+\d{1,3}[\s\-]?)?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,5}", txt):
                            entry = f"Phone: {txt}"
                            if entry not in contact_lines:
                                contact_lines.append(entry)

        # 5. Remove HTML Comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # 6. Remove Boilerplate Tags (nav, script, style, etc.)
        for tag_name in BOILERPLATE_TAGS:
            for el in soup.find_all(tag_name):
                el.decompose()

        # 7. Remove Boilerplate Elements by Selector (Cookie banners, popups, ads)
        for selector in BOILERPLATE_SELECTORS:
            for el in soup.select(selector):
                el.decompose()

        # 8. Extract Clean Text Blocks (preserve paragraph and heading linebreaks)
        content_lines: List[str] = []
        for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr", "blockquote", "address"]):
            text = el.get_text(separator=" ", strip=True)
            if text and len(text) > 3:
                content_lines.append(text)

        # Fallback if no block elements matched
        if not content_lines:
            raw_text = soup.get_text(separator="\n", strip=True)
            content_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        # Append structured contact & location section so semantic indexing captures company location
        if contact_lines:
            content_lines.append("## Company Contact & Location Information")
            for item in contact_lines:
                content_lines.append(item)

        clean_text = "\n\n".join(content_lines)
        # Normalize multiple spaces
        clean_text = re.sub(r"[ \t]+", " ", clean_text)
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()

        # 9. Compute Content Hash
        content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()

        return ExtractedPageData(
            url=url,
            title=title,
            site_name=site_name,
            clean_text=clean_text,
            content_hash=content_hash,
            headings=headings,
            images=images,
            theme_color=theme_color,
            favicon_url=favicon_url,
        )
