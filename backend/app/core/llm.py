"""Client LLM pentru Featherless.ai (API compatibil OpenAI). Proprietar: Om1.

Regula de aur: orice apel LLM poate eșua. Funcțiile întorc None la eșec,
iar agentul care le cheamă trebuie să aibă un fallback determinist.
"""
import json
import logging
import re
from typing import Any

from app import config

log = logging.getLogger("lexops.llm")
_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=config.FEATHERLESS_API_KEY,
                         base_url=config.FEATHERLESS_BASE_URL,
                         timeout=config.LLM_TIMEOUT_S)
    return _client


def _extract_json(text: str) -> Any | None:
    """Modelele open-weights pun uneori JSON-ul în ```json ... ``` sau adaugă text în jur."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    start = min([i for i in (candidate.find("{"), candidate.find("[")) if i != -1], default=-1)
    if start == -1:
        return None
    end = max(candidate.rfind("}"), candidate.rfind("]"))
    try:
        return json.loads(candidate[start:end + 1])
    except json.JSONDecodeError:
        return None


def chat_json(system: str, user: str, temperature: float = 0.0,
              max_tokens: int = 1500) -> dict | list | None:
    """Trimite un prompt și întoarce JSON parsat, sau None dacă LLM-ul e oprit / a eșuat."""
    if not config.llm_enabled():
        return None
    try:
        resp = _get_client().chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "system", "content": system + "\nRăspunde DOAR cu JSON valid."},
                      {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _extract_json(resp.choices[0].message.content or "")
    except Exception as exc:  # rețea, rate limit, model indisponibil
        log.warning("LLM call failed: %s", exc)
        return None


def chat_text(system: str, user: str, temperature: float = 0.2, max_tokens: int = 800) -> str | None:
    if not config.llm_enabled():
        return None
    try:
        resp = _get_client().chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        log.warning("LLM call failed: %s", exc)
        return None
