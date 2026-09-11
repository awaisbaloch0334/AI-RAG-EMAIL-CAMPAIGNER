import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Set, Tuple
import httpx

from app.crawler.discovery import extract_links, is_same_domain, normalize_url
from app.crawler.ssrf import is_safe_url
from app.extraction.extractor import ContentExtractor, ExtractedPageData

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


class WebCrawler:
    def __init__(
        self,
        max_pages: int = 15,
        max_depth: int = 3,
        timeout: float = 12.0,
        enable_browser_fallback: bool = True,
    ):
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.timeout = timeout
        self.enable_browser_fallback = enable_browser_fallback
        self.client = httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    def fetch_static(self, url: str) -> Optional[str]:
        """Fetch page HTML statically via HTTP."""
        safe, reason = is_safe_url(url)
        if not safe:
            logger.warning(f"Skipping unsafe URL {url}: {reason}")
            return None

        try:
            resp = self.client.get(url)
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "").lower()
                if "text/html" in content_type or not content_type:
                    return resp.text
            else:
                logger.warning(f"HTTP {resp.status_code} for {url}")
        except Exception as e:
            logger.warning(f"Failed to fetch {url} statically: {str(e)}")
        return None

    def fetch_dynamic(self, url: str) -> Optional[str]:
        """Fetch JavaScript-rendered HTML using Playwright headless browser."""
        safe, reason = is_safe_url(url)
        if not safe:
            logger.warning(f"Skipping unsafe URL {url}: {reason}")
            return None

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=USER_AGENT)
                page.set_default_timeout(int(self.timeout * 1000))
                page.goto(url, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                page.wait_for_timeout(2000)

                # Dynamically evaluate primary CTA/button brand color if meta theme-color is missing
                try:
                    page.evaluate("""() => {
                        const existing = document.querySelector('meta[name="theme-color"]');
                        if (existing && existing.content) return;

                        const canvas = document.createElement('canvas');
                        canvas.width = 1;
                        canvas.height = 1;
                        const ctx = canvas.getContext('2d', { willReadFrequently: true });

                        function toHex(col) {
                            if (!col || col === 'rgba(0, 0, 0, 0)' || col === 'transparent') return null;
                            try {
                                ctx.clearRect(0, 0, 1, 1);
                                ctx.fillStyle = col;
                                ctx.fillRect(0, 0, 1, 1);
                                const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
                                if (a < 50) return null;
                                const max = Math.max(r, g, b);
                                const min = Math.min(r, g, b);
                                if (max - min < 20) return null; // saturation check
                                return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('').toUpperCase();
                            } catch(e) { return null; }
                        }

                        function isSocialOrThirdParty(el) {
                            const href = (el.getAttribute('href') || '').toLowerCase();
                            const text = (el.innerText || '').toLowerCase();
                            const cls = (el.className || '').toString().toLowerCase();
                            const id = (el.id || '').toLowerCase();
                            const exclude = [
                                'whatsapp', 'wa.me', 'facebook', 'twitter', 'instagram',
                                'linkedin', 'youtube', 'tiktok', 'cookie', 'consent',
                                'tel:', 'mailto:', 'call'
                            ];
                            return exclude.some(pat =>
                                href.includes(pat) || text.includes(pat) || cls.includes(pat) || id.includes(pat)
                            );
                        }

                        const socialGreens = ['#25D366', '#61CE70', '#128C7E', '#79D45E', '#78D25F', '#075E54'];

                        function setThemeColor(hex) {
                            const m = document.createElement('meta');
                            m.setAttribute('name', 'theme-color');
                            m.setAttribute('content', hex);
                            document.head.appendChild(m);
                        }

                        const selectors = [
                            'header h1, h1, header h2, h2, [class*="headline"], [class*="site-title"]',
                            'header [class*="active"], nav [class*="active"], header [class*="brand"], nav [class*="brand"]',
                            '[class*="primary"]:not([class*="social"])',
                            'button[type="submit"]',
                            'a[class*="btn"]:not([class*="social"])',
                            'button:not([disabled])',
                            'header', 'nav'
                        ];
                        for (const sel of selectors) {
                            const els = document.querySelectorAll(sel);
                            for (const el of els) {
                                if (isSocialOrThirdParty(el)) continue;
                                const style = window.getComputedStyle(el);
                                const bg = toHex(style.backgroundColor);
                                if (bg && !socialGreens.includes(bg)) {
                                    setThemeColor(bg);
                                    return;
                                }
                                const col = toHex(style.color);
                                if (col && !socialGreens.includes(col)) {
                                    setThemeColor(col);
                                    return;
                                }
                            }
                        }
                    }""")
                except Exception as eval_err:
                    logger.debug(f"Dynamic color evaluation skipped: {eval_err}")

                html = page.content()
                browser.close()
                return html
        except Exception as e:
            logger.warning(f"Playwright rendering failed for {url}: {str(e)}")
            return None

    def fetch_page_content(self, url: str) -> Tuple[Optional[str], Optional[ExtractedPageData]]:
        """
        Fetch HTML (with dynamic browser fallback if static HTML is empty or a JS placeholder),
        then extract clean page content.
        """
        html = self.fetch_static(url)

        # Check if static HTML needs browser rendering (e.g. client-side SPA with empty body or no links)
        needs_browser = False
        if html:
            data = ContentExtractor.extract(html, url)
            discovered = extract_links(html, url)
            # If static HTML already yielded solid text (>= 150 chars), it is valid!
            if len(data.clean_text) >= 150:
                return html, data

            has_spa_marker = any(
                kw in html.lower()
                for kw in (
                    'id="root"', 'id="__next"', 'id="app"',
                    "modulepreload", "react-router", "vite", "__remix",
                    "_next/static"
                )
            )
            if len(data.clean_text) < 150 and (len(discovered) == 0 or has_spa_marker):
                needs_browser = True
            else:
                return html, data
        else:
            needs_browser = True

        if needs_browser and self.enable_browser_fallback:
            dynamic_html = self.fetch_dynamic(url)
            if dynamic_html:
                return dynamic_html, ContentExtractor.extract(dynamic_html, url)

        if html:
            return html, ContentExtractor.extract(html, url)
        return None, None

    def crawl_site(
        self,
        start_url: str,
        on_page_crawled: Optional[Callable[[ExtractedPageData, int], None]] = None,
    ) -> List[ExtractedPageData]:
        """
        Crawl a website starting from start_url using concurrent BFS traversal.
        Respects max_pages, max_depth, same-domain boundaries, and SSRF rules.
        """
        normalized_start = normalize_url(start_url)
        safe, reason = is_safe_url(normalized_start)
        if not safe:
            raise ValueError(f"Cannot crawl unsafe target: {reason}")

        visited: Set[str] = {normalized_start}
        queue: deque[Tuple[str, int]] = deque([(normalized_start, 0)])
        results: List[ExtractedPageData] = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            while queue and len(results) < self.max_pages:
                batch: List[Tuple[str, int]] = []
                while queue and len(batch) + len(results) < self.max_pages and len(batch) < 5:
                    batch.append(queue.popleft())

                if not batch:
                    break

                future_to_item = {
                    executor.submit(self.fetch_page_content, item[0]): item
                    for item in batch
                }

                for future in as_completed(future_to_item):
                    current_url, depth = future_to_item[future]
                    try:
                        html, extracted_data = future.result()
                    except Exception as err:
                        logger.warning(f"Error fetching {current_url}: {err}")
                        continue

                    if not html or not extracted_data:
                        continue

                    results.append(extracted_data)
                    logger.info(f"Crawled page ({len(results)}/{self.max_pages}): {current_url}")

                    if on_page_crawled:
                        try:
                            on_page_crawled(extracted_data, len(results))
                        except Exception as cb_err:
                            logger.warning(f"Error in on_page_crawled callback: {cb_err}")

                    # Discover internal links for BFS queue if within max_depth
                    if depth < self.max_depth and len(results) < self.max_pages:
                        discovered_links = extract_links(html, current_url)
                        for link in discovered_links:
                            if link not in visited and is_same_domain(link, normalized_start):
                                visited.add(link)
                                queue.append((link, depth + 1))

        return results

