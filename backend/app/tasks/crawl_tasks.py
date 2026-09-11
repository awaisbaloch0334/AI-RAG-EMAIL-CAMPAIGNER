from collections import Counter
from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawler.crawler import WebCrawler
from app.extraction.extractor import ContentExtractor
from app.db.database import SessionLocal
from app.db.models.bot import Bot
from app.db.models.branding import BrandSettings
from app.db.models.crawl import CrawlJob, Page
from app.knowledge.indexing import run_knowledge_indexing_pipeline
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def detect_live_cta_color(url: str, timeout: float = 6.0) -> Optional[str]:
    """
    Headless fallback: evaluates the live rendered computed style of CTA buttons/links/headings
    using Chromium 1-pixel canvas normalization to handle oklch, hsl, rgb, and hex formats.
    Filters out third-party social widgets (WhatsApp, Facebook, Twitter, Phone/Call).
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page.set_default_timeout(int(timeout * 1000))
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=2500)
            except Exception:
                pass
            page.wait_for_timeout(800)

            color = page.evaluate("""() => {
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
                        if (max - min < 20) return null; // saturation check, filter out grays/white/black
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
                        const bgHex = toHex(style.backgroundColor);
                        if (bgHex && !socialGreens.includes(bgHex)) {
                            return bgHex;
                        }
                        const colHex = toHex(style.color);
                        if (colHex && !socialGreens.includes(colHex)) {
                            return colHex;
                        }
                    }
                }
                return null;
            }""")
            browser.close()
            return color
    except Exception as e:
        logger.debug(f"Live CTA color detection skipped for {url}: {e}")
        return None


def extract_dominant_color_from_image(image_url: str) -> Optional[str]:
    """
    Extract dominant vibrant brand color directly from a logo image using Pillow.
    Excludes transparent pixels, neutral/gray pixels, and third-party WhatsApp greens.
    """
    try:
        import httpx
        from PIL import Image
        from io import BytesIO
        from collections import Counter

        with httpx.Client(timeout=4.0) as client:
            resp = client.get(image_url)
            if resp.status_code != 200:
                return None
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            colors = []
            pixels = list(img.getdata()) if hasattr(img, "getdata") else []
            for p in pixels:
                r, g, b, a = p
                if a > 80:
                    mx, mn = max(r, g, b), min(r, g, b)
                    # Saturated pixels only (exclude neutral grays/white/black)
                    if mx - mn >= 30 and mx >= 40 and mn <= 220:
                        hex_col = f"#{r:02X}{g:02X}{b:02X}"
                        if hex_col not in ("#25D366", "#61CE70", "#128C7E"):
                            colors.append((r, g, b))

            if not colors:
                return None

            # Cluster by 16-step quantization
            bucketed = Counter((r // 16 * 16, g // 16 * 16, b // 16 * 16) for r, g, b in colors)
            (br, bg, bb), _ = bucketed.most_common(1)[0]
            in_bucket = [c for c in colors if (c[0] // 16 * 16, c[1] // 16 * 16, c[2] // 16 * 16) == (br, bg, bb)]
            avg_r = sum(c[0] for c in in_bucket) // len(in_bucket)
            avg_g = sum(c[1] for c in in_bucket) // len(in_bucket)
            avg_b = sum(c[2] for c in in_bucket) // len(in_bucket)
            return f"#{avg_r:02X}{avg_g:02X}{avg_b:02X}"
    except Exception as err:
        logger.debug(f"Dominant color extraction from {image_url} skipped: {err}")
        return None


def auto_enrich_bot_branding(db: Session, bot: Bot, pages_data: list) -> None:
    """
    Automatically detect and enrich real website branding (company name, logo, primary color, favicon)
    from crawled pages if brand settings are unconfigured, default, or holding placeholder data.
    """
    try:
        brand = db.get(BrandSettings, bot.id)
        if not brand:
            return

        dummy_markers = ["data:image", "base64", "no-image", "no_image", "noimage", "placeholder", "dummy", "blank.gif", "spacer.gif", "default-image"]
        bad_logo_keywords = ["google", "trustpilot", "clutch", "rating", "stripe", "visa", "wordpress", "no-image", "no_image", "noimage", "placeholder", "dummy", "blank.gif", "spacer.gif", "default-image"]

        curr_comp = (brand.company_name or "").strip()
        initial_bot_name = re.sub(r"(?i)\s+(chatbot|bot|ai assistant|assistant)$", "", bot.name).strip()
        needs_company = (
            not curr_comp
            or curr_comp == bot.name
            or curr_comp.lower() == initial_bot_name.lower()
            or bool(re.search(r"(?i)\b(chatbot|bot|ai assistant|assistant)\b", curr_comp))
        )

        curr_logo = (brand.logo_url or "").strip()
        needs_logo = not curr_logo or any(m in curr_logo.lower() for m in dummy_markers)

        curr_color = (brand.primary_color or "").strip().upper()
        needs_color = (
            not curr_color
            or curr_color in (
                "#2563EB", "#000000", "#FFFFFF",
                "#61CE70", "#25D366", "#128C7E", "#79D45E", "#78D25F"  # reject WhatsApp greens
            )
        )

        # Fallback: If pages_data lacks rich HTML/images, fetch the homepage HTML directly to inspect live tags
        if (needs_logo or needs_company or needs_color) and bot.website_url:
            has_rich_images = any(bool(getattr(p, "images", None)) for p in pages_data)
            if not pages_data or not has_rich_images:
                try:
                    import httpx
                    with httpx.Client(timeout=6.0, follow_redirects=True) as client:
                        resp = client.get(
                            bot.website_url,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
                        )
                        if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", "").lower():
                            homepage_data = ContentExtractor.extract(resp.text, str(resp.url))
                            pages_data = [homepage_data] + (pages_data or [])
                except Exception as direct_err:
                    logger.debug(f"Direct homepage branding fetch skipped for {bot.website_url}: {direct_err}")

        # 1. Company Name Detection
        if needs_company and pages_data:
            detected_company = None
            # Check og:site_name on homepage or other pages
            for p in pages_data:
                sn = getattr(p, "site_name", None)
                if sn and len(sn.strip()) > 1:
                    detected_company = sn.strip()
                    break

            # Fallback to page titles
            if not detected_company:
                suffixes = []
                for p in pages_data:
                    title = (getattr(p, "title", None) or "").strip()
                    if " - " in title:
                        suffixes.append(title.split(" - ")[-1].strip())
                    elif " | " in title:
                        suffixes.append(title.split(" | ")[-1].strip())
                    elif ":" in title:
                        suffixes.append(title.split(":")[0].strip())
                if suffixes:
                    common_suffix, count = Counter(suffixes).most_common(1)[0]
                    if count >= 2 or len(suffixes) == 1:
                        clean_suffix = re.sub(r"(?i)\s+(home|official|welcome|main)$", "", common_suffix).strip()
                        if clean_suffix and len(clean_suffix) > 2:
                            detected_company = clean_suffix

            if detected_company:
                clean_company = re.sub(r"(?i)\s+(chatbot|bot|ai assistant|assistant)$", "", detected_company).strip()
                if clean_company and len(clean_company) > 1:
                    brand.company_name = clean_company
                    logger.info(f"Auto-enriched company name '{brand.company_name}' for bot '{bot.id}'")

        # 2. Logo & Favicon Detection
        if needs_logo and pages_data:
            # Priority 1: Check image tags explicitly classified as logo
            for p in pages_data:
                for img in getattr(p, "images", []):
                    src = (img.get("url") or img.get("src") or "").strip()
                    if not src or any(m in src.lower() for m in dummy_markers):
                        continue
                    if any(bad in src.lower() for bad in bad_logo_keywords):
                        continue
                    if img.get("is_logo"):
                        brand.logo_url = src
                        logger.info(f"Auto-enriched logo (is_logo) '{src}' for bot '{bot.id}'")
                        break
                if brand.logo_url and not any(m in brand.logo_url.lower() for m in dummy_markers):
                    break

            # Priority 2: Fallback to keyword matching in attributes
            if not brand.logo_url or any(m in brand.logo_url.lower() for m in dummy_markers):
                for p in pages_data:
                    for img in getattr(p, "images", []):
                        src = (img.get("url") or img.get("src") or "").strip()
                        if not src or any(m in src.lower() for m in dummy_markers):
                            continue
                        if any(bad in src.lower() for bad in bad_logo_keywords):
                            continue
                        alt = (img.get("alt") or "").lower()
                        cls_name = (img.get("class") or "").lower()
                        img_id = (img.get("id") or "").lower()
                        if any("logo" in x for x in [src.lower(), alt, cls_name, img_id]):
                            brand.logo_url = src
                            logger.info(f"Auto-enriched logo '{src}' for bot '{bot.id}'")
                            break
                    if brand.logo_url and not any(m in brand.logo_url.lower() for m in dummy_markers):
                        break

            # Priority 3: Fallback to favicon_url if no explicit logo
            if not brand.logo_url or any(m in brand.logo_url.lower() for m in dummy_markers):
                for p in pages_data:
                    fav = getattr(p, "favicon_url", None)
                    if fav and not any(m in fav.lower() for m in dummy_markers):
                        brand.logo_url = fav
                        logger.info(f"Auto-enriched logo from favicon '{fav}' for bot '{bot.id}'")
                        break

        # Enrich favicon_url if not set or invalid
        curr_fav = (brand.favicon_url or "").strip()
        if (not curr_fav or any(m in curr_fav.lower() for m in dummy_markers)) and pages_data:
            for p in pages_data:
                fav = getattr(p, "favicon_url", None)
                if fav and not any(m in fav.lower() for m in dummy_markers):
                    brand.favicon_url = fav
                    break
            if not brand.favicon_url and brand.logo_url and not any(m in brand.logo_url.lower() for m in dummy_markers):
                brand.favicon_url = brand.logo_url

        # 3. Primary Color Detection
        if needs_color:
            detected_color = None

            # Priority A: Check if page has authentic theme_color (excluding social greens & grays)
            if pages_data:
                for p in pages_data:
                    c = getattr(p, "theme_color", None)
                    if c and c.upper() not in (
                        "#2563EB", "#000000", "#FFFFFF", "#F9FAFB", "#F3F4F6", "#E5E7EB",
                        "#61CE70", "#25D366", "#128C7E", "#79D45E", "#78D25F"
                    ):
                        detected_color = c.upper()
                        break

            # Priority B: Extract dominant brand color directly from authentic Logo image
            if not detected_color and brand.logo_url and not any(m in brand.logo_url.lower() for m in dummy_markers):
                detected_color = extract_dominant_color_from_image(brand.logo_url)
                if detected_color:
                    logger.info(f"Extracted authentic brand color '{detected_color}' from logo '{brand.logo_url}'")

            # Priority C: Fast headless browser evaluation of live CTAs / header elements
            if not detected_color and bot.website_url:
                detected_color = detect_live_cta_color(bot.website_url)

            if detected_color:
                brand.primary_color = detected_color
                logger.info(f"Auto-enriched primary color '{detected_color}' for bot '{bot.id}'")

        db.commit()
    except Exception as e:
        logger.warning(f"Failed auto-enriching brand settings for bot '{bot.id}': {e}")


def run_crawl_pipeline(
    bot_id: str,
    job_id: Optional[str] = None,
    max_pages: int = 60,
) -> Dict[str, Any]:
    """
    Core crawl pipeline execution.
    Enforces the bot_id multi-tenant invariant throughout the ingestion process.
    """
    db: Session = SessionLocal()
    crawl_job: Optional[CrawlJob] = None
    bot: Optional[Bot] = None

    try:
        bot = db.get(Bot, bot_id)
        if not bot:
            logger.error(f"Bot '{bot_id}' not found for crawl pipeline")
            return {"status": "error", "message": "Bot not found"}

        # Find or create CrawlJob
        if job_id:
            crawl_job = db.get(CrawlJob, job_id)

        if not crawl_job:
            crawl_job = CrawlJob(
                bot_id=bot.id,
                status="RUNNING",
                started_at=datetime.now(timezone.utc),
            )
            db.add(crawl_job)
            db.commit()
            db.refresh(crawl_job)
        else:
            crawl_job.status = "RUNNING"
            if not crawl_job.started_at:
                crawl_job.started_at = datetime.now(timezone.utc)

        bot.status = "CRAWLING"
        db.commit()

        # Run crawler with real-time incremental persistence
        crawler = WebCrawler(max_pages=max_pages, max_depth=3)

        def on_page_crawled(p_data, current_count):
            try:
                existing_page = db.scalar(
                    select(Page).where(Page.bot_id == bot.id, Page.url == p_data.url)
                )
                if existing_page:
                    existing_page.title = p_data.title
                    existing_page.content = p_data.clean_text
                    existing_page.content_hash = p_data.content_hash
                    existing_page.crawl_status = "SUCCESS"
                else:
                    new_page = Page(
                        bot_id=bot.id,
                        url=p_data.url,
                        title=p_data.title,
                        content=p_data.clean_text,
                        content_hash=p_data.content_hash,
                        crawl_status="SUCCESS",
                    )
                    db.add(new_page)
                crawl_job.total_pages = current_count
                crawl_job.processed_pages = current_count
                db.commit()
            except Exception as ex:
                logger.error(f"Failed incremental storage for {p_data.url}: {ex}")

        pages_data = crawler.crawl_site(bot.website_url, on_page_crawled=on_page_crawled)

        # Ensure all pages returned from crawl_site are persisted (even if on_page_crawled was bypassed by a mock)
        for p_data in pages_data:
            existing_page = db.scalar(
                select(Page).where(Page.bot_id == bot.id, Page.url == p_data.url)
            )
            if not existing_page:
                new_page = Page(
                    bot_id=bot.id,
                    url=p_data.url,
                    title=p_data.title,
                    content=p_data.clean_text,
                    content_hash=p_data.content_hash,
                    crawl_status="SUCCESS",
                )
                db.add(new_page)

        crawl_job.total_pages = len(pages_data)
        crawl_job.processed_pages = len(pages_data)
        crawl_job.status = "COMPLETED"
        crawl_job.completed_at = datetime.now(timezone.utc)
        db.commit()

        # Auto-enrich company name and brand metadata from crawled pages
        auto_enrich_bot_branding(db=db, bot=bot, pages_data=pages_data)

        # Transition bot status to PROCESSING and automatically chain knowledge indexing
        bot.status = "PROCESSING"
        db.commit()

        # Run canonical markdown, semantic chunking, embeddings, and vector indexing
        indexing_result = run_knowledge_indexing_pipeline(bot_id=bot.id, db=db)
        logger.info(f"Knowledge indexing for bot '{bot.id}' completed: {indexing_result.get('message')}")

        return {
            "status": "success",
            "bot_id": bot.id,
            "job_id": crawl_job.id,
            "total_pages": len(pages_data),
            "processed_pages": len(pages_data),
            "failed_pages": 0,
            "indexing": indexing_result,
        }

    except Exception as e:
        logger.error(f"Crawl pipeline failed for bot {bot_id}: {str(e)}")
        if crawl_job:
            crawl_job.status = "FAILED"
            crawl_job.completed_at = datetime.now(timezone.utc)
        if bot:
            bot.status = "FAILED"
        db.commit()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


@celery_app.task(name="app.tasks.crawl_tasks.start_crawl_task", bind=True)
def start_crawl_task(self, bot_id: str, job_id: Optional[str] = None, max_pages: int = 60):
    """
    Celery worker task that executes website crawling in the background.
    Retains bot_id throughout the execution.
    """
    return run_crawl_pipeline(bot_id=bot_id, job_id=job_id, max_pages=max_pages)

