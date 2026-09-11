from datetime import datetime, timezone
import hashlib
from typing import Any, Callable, List, Optional

from app.db.models.bot import Bot
from app.db.models.crawl import Page


class CanonicalMarkdownGenerator:
    """
    Generates the canonical human-readable Markdown knowledge representation
    from structured crawled pages, as specified in PROJECT_SPEC.md.
    """

    @staticmethod
    def generate(bot: Bot, pages: List[Page]) -> str:
        """
        Assemble all crawled pages for a bot into a standardized, canonical Markdown document.
        Retains source URLs, page titles, and timestamps for source attribution.
        """
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines: List[str] = [
            f"# {bot.name} — Website Knowledge Base",
            "",
            "## Website Information",
            f"- **Website Name**: {bot.name}",
            f"- **Target URL**: {bot.website_url}",
            f"- **Indexed At**: {now_iso}",
            f"- **Total Crawled Pages**: {len(pages)}",
            "",
            "---",
            "",
            "## Knowledge Contents",
            "",
        ]

        if not pages:
            lines.append("*No content has been crawled for this website yet.*")
            return "\n".join(lines)

        for idx, page in enumerate(pages, 1):
            page_title = page.title or f"Page {idx}"
            page_url = page.url
            crawl_time = page.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if page.created_at else now_iso

            lines.extend([
                f"### Page {idx}: {page_title}",
                "```yaml",
                f"source_url: {page_url}",
                f"page_title: {page_title}",
                f"crawl_timestamp: {crawl_time}",
                "```",
                "",
            ])

            if page.content:
                lines.append(page.content.strip())
            else:
                lines.append("*(No text content extracted)*")

            lines.extend(["", "---", ""])

        return "\n".join(lines).strip()

    @staticmethod
    def compute_hash(markdown_content: str) -> str:
        """Compute SHA-256 hash of the canonical Markdown content."""
        return hashlib.sha256(markdown_content.encode("utf-8")).hexdigest()

    @classmethod
    def normalize_with_llm(
        cls,
        markdown_content: str,
        llm_client: Optional[Any] = None,
    ) -> str:
        """
        Optional LLM normalization step (e.g. Gemini, Claude, or OpenAI).
        Cleans repetitive headers, structures FAQ sections, or condenses noise
        while preserving grounding facts.
        Falls back safely to raw markdown if no LLM client is configured.
        """
        if not llm_client:
            return markdown_content

        try:
            # Pluggable LLM invocation hook
            # Expects llm_client to have a generate_content / complete method or callable
            if callable(llm_client):
                return llm_client(markdown_content)
            elif hasattr(llm_client, "generate_content"):
                prompt = (
                    "You are a knowledge-base normalizer. Clean up formatting, preserve all factual details, "
                    "contact info, pricing, product specs, and URLs, and structure the content clearly:\n\n"
                    f"{markdown_content}"
                )
                response = llm_client.generate_content(prompt)
                return getattr(response, "text", markdown_content)
            return markdown_content
        except Exception:
            # Never fail pipeline if optional LLM normalization errors
            return markdown_content

