import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.bot import Bot
from app.db.models.branding import BrandSettings
from app.db.models.chat import Conversation, Message
from app.llm.client import get_llm_client
from app.rag.prompt import RAGPromptBuilder
from app.rag.retriever import VectorRetriever
from app.rag.schemas import SourceCitation

logger = logging.getLogger(__name__)


class ChatService:
    """
    Orchestrates grounded RAG chat interactions:
    1. Loads or initializes multi-turn conversation sessions.
    2. Performs bot-scoped vector similarity retrieval.
    3. Builds anti-prompt-injection grounded prompts.
    4. Generates responses using pluggable LLM backends (Gemini, Claude, OpenAI, Mock).
    5. Persists message transcripts.
    6. Supports standard JSON responses and SSE streaming.
    """

    @classmethod
    def get_or_create_conversation(
        cls,
        db: Session,
        bot_id: str,
        session_id: Optional[str] = None,
    ) -> Conversation:
        """Find existing conversation by session_id or initialize a new one."""
        if session_id:
            conv = db.scalar(
                select(Conversation).where(
                    Conversation.bot_id == bot_id,
                    Conversation.session_id == session_id,
                )
            )
            if conv:
                return conv

        new_session_id = session_id or str(uuid.uuid4())
        conv = Conversation(bot_id=bot_id, session_id=new_session_id)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv

    @classmethod
    def _prepare_retrieval_query_and_company(
        cls,
        bot: Bot,
        query: str,
        db: Session,
    ) -> Tuple[str, str]:
        """
        Extract clean company name from BrandSettings and contextualize short/ambiguous
        queries so vector search retrieves company-wide overview chunks rather than niche sub-pages.
        """
        brand = db.get(BrandSettings, bot.id)
        raw_company = (brand.company_name if brand and brand.company_name else bot.name).strip()
        clean_company = re.sub(r"(?i)\s+(chatbot|bot|assistant|ai)$", "", raw_company).strip() or raw_company

        retrieval_query = query.strip()
        words = retrieval_query.split()
        is_generic = (
            len(words) <= 5
            or any(
                re.search(rf"\b{w}\b", retrieval_query, re.I)
                for w in ("it", "this", "you", "they", "company", "what is", "tell me about", "services", "products")
            )
        )
        if is_generic and clean_company.lower() not in retrieval_query.lower():
            retrieval_query = f"{clean_company} {retrieval_query}"

        return retrieval_query, clean_company

    @classmethod
    def process_message(
        cls,
        db: Session,
        bot: Bot,
        query: str,
        session_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Tuple[str, List[SourceCitation], Conversation]:
        """
        Synchronous / standard end-to-end RAG question answering.
        """
        conv = cls.get_or_create_conversation(db, bot.id, session_id)

        # 1. Store user message turn
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=query.strip(),
        )
        db.add(user_msg)
        db.commit()

        # 2. Load prior conversation history (excluding the current turn)
        prior_messages = (
            db.scalars(
                select(Message)
                .where(Message.conversation_id == conv.id, Message.id != user_msg.id)
                .order_by(Message.created_at.asc())
            )
            .all()
        )
        history: List[Dict[str, str]] = [
            {"role": m.role, "content": m.content} for m in prior_messages
        ]

        # 3. Contextualize generic queries & resolve company name
        retrieval_query, clean_company = cls._prepare_retrieval_query_and_company(bot, query, db)

        # 4. Retrieve relevant chunks strictly scoped to bot.id
        chunks = VectorRetriever.retrieve(
            bot_id=bot.id,
            query=retrieval_query,
            db=db,
            top_k=5,
            provider=provider,
        )

        # 5. Extract unique source citations
        seen_urls = set()
        citations: List[SourceCitation] = []
        for c in chunks:
            if c.source_url and c.source_url not in seen_urls:
                seen_urls.add(c.source_url)
                citations.append(
                    SourceCitation(
                        url=c.source_url,
                        title=c.page_title,
                        section=c.section,
                        chunk_index=c.chunk_index,
                    )
                )

        # 6. Build prompt with untrusted reference data isolation
        system_prompt = RAGPromptBuilder.build_system_prompt(bot, company_name=clean_company)
        user_prompt = RAGPromptBuilder.build_user_prompt(
            query=query,
            chunks=chunks,
            conversation_history=history,
        )

        # 6. LLM Inference
        llm = get_llm_client(provider)
        try:
            answer = llm.generate_response(user_prompt, system_prompt=system_prompt)
        except Exception as ex:
            logger.error(f"LLM inference error: {str(ex)}")
            answer = (
                f"I'm sorry, I encountered an issue accessing my knowledge base. "
                f"Please try again or visit {bot.website_url} directly."
            )

        # 7. Store assistant response turn
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=answer,
        )
        db.add(assistant_msg)
        db.commit()

        return answer, citations, conv

    @classmethod
    async def stream_message(
        cls,
        db: Session,
        bot: Bot,
        query: str,
        session_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronous Server-Sent Events (SSE) generator for streaming chatbot responses.
        Yields JSON payloads conforming to standard event-stream protocol.
        """
        conv = cls.get_or_create_conversation(db, bot.id, session_id)

        # 1. Record user turn
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=query.strip(),
        )
        db.add(user_msg)
        db.commit()

        # 2. Prior history
        prior_messages = (
            db.scalars(
                select(Message)
                .where(Message.conversation_id == conv.id, Message.id != user_msg.id)
                .order_by(Message.created_at.asc())
            )
            .all()
        )
        history: List[Dict[str, str]] = [
            {"role": m.role, "content": m.content} for m in prior_messages
        ]

        # 3. Contextualize generic queries & resolve company name
        retrieval_query, clean_company = cls._prepare_retrieval_query_and_company(bot, query, db)

        # 4. Retrieve chunks
        chunks = VectorRetriever.retrieve(
            bot_id=bot.id,
            query=retrieval_query,
            db=db,
            top_k=5,
            provider=provider,
        )

        # 5. Citations
        seen_urls = set()
        citations: List[Dict[str, Any]] = []
        for c in chunks:
            if c.source_url and c.source_url not in seen_urls:
                seen_urls.add(c.source_url)
                citations.append({
                    "url": c.source_url,
                    "title": c.page_title,
                    "section": c.section,
                    "chunk_index": c.chunk_index,
                })

        # Send start event with metadata & citations
        start_payload = {
            "type": "start",
            "conversation_id": conv.id,
            "session_id": conv.session_id,
            "sources": citations,
        }
        yield f"data: {json.dumps(start_payload)}\n\n"

        # 6. Build prompt & invoke LLM
        system_prompt = RAGPromptBuilder.build_system_prompt(bot, company_name=clean_company)
        user_prompt = RAGPromptBuilder.build_user_prompt(
            query=query,
            chunks=chunks,
            conversation_history=history,
        )

        llm = get_llm_client(provider)
        try:
            full_answer = llm.generate_response(user_prompt, system_prompt=system_prompt)
        except Exception as ex:
            logger.error(f"LLM streaming inference error: {str(ex)}")
            full_answer = (
                f"I'm sorry, I encountered an issue accessing my knowledge base. "
                f"Please check {bot.website_url}."
            )

        # 6. Stream tokens/words smoothly to client
        words = full_answer.split(" ")
        for i, word in enumerate(words):
            token = word + (" " if i < len(words) - 1 else "")
            token_payload = {"type": "token", "token": token}
            yield f"data: {json.dumps(token_payload)}\n\n"
            await asyncio.sleep(0.015)  # Natural typing rhythm

        # 7. Persist assistant turn in DB
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=full_answer,
        )
        db.add(assistant_msg)
        db.commit()

        # Final end event
        end_payload = {
            "type": "end",
            "conversation_id": conv.id,
            "session_id": conv.session_id,
            "full_answer": full_answer,
        }
        yield f"data: {json.dumps(end_payload)}\n\n"
