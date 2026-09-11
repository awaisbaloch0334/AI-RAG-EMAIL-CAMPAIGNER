import logging
from typing import List, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    _fastembed_model = None

    @classmethod
    def _get_fastembed_model(cls):
        """Lazy singleton loader for local fastembed ONNX model."""
        if cls._fastembed_model is None:
            from fastembed import TextEmbedding
            logger.info(f"Loading FastEmbed model '{settings.embedding_model}'...")
            cls._fastembed_model = TextEmbedding(model_name=settings.embedding_model)
        return cls._fastembed_model

    @classmethod
    def embed_texts(
        cls,
        texts: List[str],
        provider: Optional[str] = None,
    ) -> List[List[float]]:
        """
        Generate embedding vectors for a list of texts using the configured provider.
        Supports: 'fastembed' (default), 'mock', 'openai', 'gemini'.
        """
        if not texts:
            return []

        active_provider = (provider or settings.embedding_provider).lower()

        if active_provider == "fastembed":
            model = cls._get_fastembed_model()
            embeddings = list(model.embed(texts))
            return [e.tolist() for e in embeddings]

        elif active_provider == "mock":
            # Deterministic normalized vectors for tests
            results: List[List[float]] = []
            for idx, text in enumerate(texts):
                base_val = (hash(text) % 100) / 100.0
                vec = [base_val + (i * 0.001) for i in range(384)]
                results.append(vec)
            return results

        elif active_provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is not configured in settings.")
            url = "https://api.openai.com/v1/embeddings"
            headers = {
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "input": texts,
                "model": settings.embedding_model or "text-embedding-3-small",
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return [item["embedding"] for item in data["data"]]

        elif active_provider == "gemini":
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not configured in settings.")
            # Google Gemini embedding endpoint
            results = []
            with httpx.Client(timeout=30.0) as client:
                for text in texts:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={settings.gemini_api_key}"
                    payload = {
                        "model": "models/text-embedding-004",
                        "content": {"parts": [{"text": text}]},
                    }
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    results.append(data["embedding"]["values"])
            return results

        else:
            raise ValueError(f"Unknown embedding provider '{active_provider}'")

    @classmethod
    def embed_query(cls, query: str, provider: Optional[str] = None) -> List[float]:
        """Embed a single query text string."""
        results = cls.embed_texts([query], provider=provider)
        return results[0]

