import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.db.models.crawl import Page


@dataclass
class ChunkItem:
    content: str
    page_id: Optional[str]
    source_url: str
    page_title: str
    section: str
    chunk_index: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class SemanticChunker:
    """
    Splits website page content into semantically coherent chunks
    preserving section hierarchy, source URLs, and metadata.
    """

    def __init__(self, target_chunk_size: int = 700, min_chunk_size: int = 80, overlap: int = 80):
        self.target_chunk_size = target_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap = overlap

    def chunk_page(self, page: Page, starting_index: int = 0) -> List[ChunkItem]:
        """
        Split a single crawled Page into structured, metadata-rich chunks.
        """
        if not page.content or not page.content.strip():
            return []

        chunks: List[ChunkItem] = []
        current_section = page.title or "General"
        current_index = starting_index

        # Split text into paragraphs
        paragraphs = [p.strip() for p in page.content.split("\n\n") if p.strip()]

        current_buffer: List[str] = []
        current_buffer_len = 0

        for para in paragraphs:
            # Detect section heading
            heading_match = re.match(r"^(#{1,4})\s+(.+)$", para)
            if heading_match:
                # Flush previous buffer before changing section
                if current_buffer and current_buffer_len >= self.min_chunk_size:
                    chunk_text = " ".join(current_buffer)
                    chunks.append(
                        ChunkItem(
                            content=chunk_text,
                            page_id=page.id,
                            source_url=page.url,
                            page_title=page.title or "",
                            section=current_section,
                            chunk_index=current_index,
                            metadata={
                                "source_url": page.url,
                                "page_title": page.title,
                                "section": current_section,
                                "chunk_index": current_index,
                            },
                        )
                    )
                    current_index += 1
                    current_buffer = []
                    current_buffer_len = 0

                current_section = heading_match.group(2).strip()

            # If a single paragraph is too large, split it with overlap
            if len(para) > self.target_chunk_size:
                # Flush current buffer first
                if current_buffer:
                    chunk_text = " ".join(current_buffer)
                    chunks.append(
                        ChunkItem(
                            content=chunk_text,
                            page_id=page.id,
                            source_url=page.url,
                            page_title=page.title or "",
                            section=current_section,
                            chunk_index=current_index,
                            metadata={
                                "source_url": page.url,
                                "page_title": page.title,
                                "section": current_section,
                                "chunk_index": current_index,
                            },
                        )
                    )
                    current_index += 1
                    current_buffer = []
                    current_buffer_len = 0

                # Split large paragraph by sentences / windows
                sub_chunks = self._split_text_with_overlap(para)
                for sub in sub_chunks:
                    chunks.append(
                        ChunkItem(
                            content=sub,
                            page_id=page.id,
                            source_url=page.url,
                            page_title=page.title or "",
                            section=current_section,
                            chunk_index=current_index,
                            metadata={
                                "source_url": page.url,
                                "page_title": page.title,
                                "section": current_section,
                                "chunk_index": current_index,
                            },
                        )
                    )
                    current_index += 1
                continue

            # Check if adding this paragraph exceeds target size
            if current_buffer_len + len(para) > self.target_chunk_size and current_buffer_len >= self.min_chunk_size:
                chunk_text = " ".join(current_buffer)
                chunks.append(
                    ChunkItem(
                        content=chunk_text,
                        page_id=page.id,
                        source_url=page.url,
                        page_title=page.title or "",
                        section=current_section,
                        chunk_index=current_index,
                        metadata={
                            "source_url": page.url,
                            "page_title": page.title,
                            "section": current_section,
                            "chunk_index": current_index,
                        },
                    )
                )
                current_index += 1
                current_buffer = [para]
                current_buffer_len = len(para)
            else:
                current_buffer.append(para)
                current_buffer_len += len(para)

        # Flush remaining buffer
        if current_buffer:
            chunk_text = " ".join(current_buffer)
            chunks.append(
                ChunkItem(
                    content=chunk_text,
                    page_id=page.id,
                    source_url=page.url,
                    page_title=page.title or "",
                    section=current_section,
                    chunk_index=current_index,
                    metadata={
                        "source_url": page.url,
                        "page_title": page.title,
                        "section": current_section,
                        "chunk_index": current_index,
                    },
                )
            )

        return chunks

    def _split_text_with_overlap(self, text: str) -> List[str]:
        """Split a long text string into overlapping chunks."""
        words = text.split()
        if not words:
            return []

        chunks: List[str] = []
        target_words = max(1, self.target_chunk_size // 6)
        overlap_words = max(1, self.overlap // 6)

        i = 0
        while i < len(words):
            chunk = " ".join(words[i : i + target_words])
            chunks.append(chunk)
            i += target_words - overlap_words

        return chunks

    def chunk_pages(self, pages: List[Page]) -> List[ChunkItem]:
        """Chunk a list of pages in sequence, maintaining a global index."""
        all_chunks: List[ChunkItem] = []
        current_index = 0
        for page in pages:
            page_chunks = self.chunk_page(page, starting_index=current_index)
            all_chunks.extend(page_chunks)
            current_index += len(page_chunks)
        return all_chunks

