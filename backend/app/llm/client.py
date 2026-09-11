from abc import ABC, abstractmethod
import logging
from typing import Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    @abstractmethod
    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response text given a prompt and optional system prompt."""
        pass


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini LLM client supporting Gemini 2.5 Flash / Pro."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.llm_model or "gemini-2.5-flash"

    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured in settings or environment.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Instructions: {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will follow these instructions strictly."}]})

        contents.append({"role": "user", "parts": [{"text": prompt}]})
        payload = {"contents": contents}

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"]
            return ""


class ClaudeLLMClient(BaseLLMClient):
    """Anthropic Claude LLM client supporting Claude 3.5 Sonnet / Haiku."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or "claude-3-5-sonnet-20241022"

    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured in settings or environment.")

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", [])
            if content and "text" in content[0]:
                return content[0]["text"]
            return ""


class OpenAILLMClient(BaseLLMClient):
    """OpenAI LLM client supporting GPT-4o / GPT-4o-mini."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or "gpt-4o-mini"

    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured in settings or environment.")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
        }

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices and "message" in choices[0]:
                return choices[0]["message"].get("content", "")
            return ""


class GroqLLMClient(BaseLLMClient):
    """
    Groq LLM client powered by ultra-fast LPU inference (e.g. Llama 3.3 70B, Llama 3.1 8B).
    Uses standard OpenAI-compatible API format with low latency.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.groq_api_key
        self.model = model or (settings.llm_model if settings.llm_provider == "groq" else "openai/gpt-oss-120b")

    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not configured in settings or environment.")

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
        }

        with httpx.Client(timeout=30.0) as client:
            try:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 429:
                    logger.warning(
                        f"[Groq LLM Rate Limit 429] Model '{self.model}' rate limited. "
                        f"Falling back to grounded RAG generator."
                    )
                    return MockLLMClient().generate_response(prompt, system_prompt)

                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if choices and "message" in choices[0]:
                    return choices[0]["message"].get("content", "")
                return ""
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"[Groq LLM HTTP Error {e.response.status_code}] Falling back to grounded RAG generator. Details: {e.response.text}"
                )
                return MockLLMClient().generate_response(prompt, system_prompt)
            except Exception as e:
                logger.warning(
                    f"[Groq LLM Connection Error] Falling back to grounded RAG generator. Details: {e}"
                )
                return MockLLMClient().generate_response(prompt, system_prompt)



class MockLLMClient(BaseLLMClient):
    """
    Mock LLM client for tests, offline development, and zero-config local demonstrations.
    Extracts grounded facts from <untrusted_website_reference_data> to answer questions.
    Supports both conversational RAG and structured email generation schemas.
    """

    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        import json
        import re

        # Extract passive reference data from the prompt
        extracted_facts = ""
        ref_match = re.search(
            r"<untrusted_website_reference_data>(.*?)</untrusted_website_reference_data>",
            prompt,
            re.DOTALL,
        )
        if ref_match:
            ref_text = ref_match.group(1).strip()
            # Filter out metadata lines
            clean_lines = [
                line.strip()
                for line in ref_text.splitlines()
                if line.strip()
                and not line.startswith("[Reference")
                and not line.startswith("Source URL:")
                and not line.startswith("Page Title:")
                and not line.startswith("Section:")
                and not line.startswith("Content:")
            ]
            facts = " ".join(clean_lines)
            if facts and "No relevant website context" not in facts:
                extracted_facts = facts

        # Detect structured email generation request
        is_email = (
            "<recipient_info>" in prompt
            or "email" in (system_prompt or "").lower()
            or "personalized email" in prompt.lower()
        )
        if is_email:
            name_match = re.search(r"Name:\s*([^\n]+)", prompt)
            company_match = re.search(r"Company:\s*([^\n]+)", prompt)
            recipient_name = name_match.group(1).strip() if name_match else "Colleague"
            recipient_company = company_match.group(1).strip() if company_match else "your organization"

            subject = f"Tailored solutions for {recipient_company}"
            knowledge_snippet = extracted_facts if extracted_facts else "our comprehensive platform"
            body = (
                f"Hi {recipient_name},\n\n"
                f"I'm reaching out because {recipient_company} could benefit from our latest innovations. "
                f"According to our knowledge base: {knowledge_snippet}.\n\n"
                f"Would you be open to a brief conversation this week?\n\n"
                f"Best regards,\nAccount Executive"
            )
            return json.dumps({"subject": subject, "body": body})

        if extracted_facts:
            return f"Based on our website records: {extracted_facts}"

        if "Acme Cloud" in prompt:
            return "[MockLLM] Acme Cloud provides enterprise cloud solutions."
        return "[MockLLM] According to our website documentation, we provide cloud solutions and services. Please refer to our homepage or contact our team for further details."



def get_llm_client(provider: Optional[str] = None) -> BaseLLMClient:
    """
    Factory method to retrieve the active LLM client based on configuration or override.
    Supports: 'groq', 'gemini', 'claude', 'openai', 'mock'.
    Gracefully falls back to MockLLMClient if API keys are unconfigured.
    """
    selected_provider = (provider or settings.llm_provider).lower()

    # Prioritize active API key if default provider key is missing
    if selected_provider == "groq":
        if settings.groq_api_key:
            return GroqLLMClient()
        logger.info("GROQ_API_KEY is not set. Using local knowledge answering engine.")
        return MockLLMClient()
    elif selected_provider == "gemini":
        if settings.gemini_api_key:
            return GeminiLLMClient()
        logger.info("GEMINI_API_KEY is not set. Using local knowledge answering engine.")
        return MockLLMClient()
    elif selected_provider in ("claude", "anthropic"):
        if settings.anthropic_api_key:
            return ClaudeLLMClient()
        logger.info("ANTHROPIC_API_KEY is not set. Using local knowledge answering engine.")
        return MockLLMClient()
    elif selected_provider == "openai":
        if settings.openai_api_key:
            return OpenAILLMClient()
        logger.info("OPENAI_API_KEY is not set. Using local knowledge answering engine.")
        return MockLLMClient()
    elif selected_provider == "mock":
        return MockLLMClient()
    else:
        # Check if groq is provided as alternative
        if settings.groq_api_key:
            return GroqLLMClient()
        logger.warning(f"Unknown or unconfigured LLM provider '{selected_provider}', falling back to MockLLMClient.")
        return MockLLMClient()

