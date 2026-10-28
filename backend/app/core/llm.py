"""Client LLM pentru AWS Bedrock (cu cache pe disc, telemetrie și fallback determinist). Proprietar: Om1.

Regula de aur: orice apel LLM poate eșua. Funcțiile întorc None la eșec,
iar agentul care le cheamă trebuie să aibă un fallback determinist.
"""
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from app import config

log = logging.getLogger("lexops.llm")
_bedrock_client = None
_CACHE_DIR = Path(__file__).resolve().parent / "__pycache__" / "llm_cache"

_FALLBACK_BEDROCK_MODELS = [
    "us.amazon.nova-pro-v1:0",
    "us.amazon.nova-lite-v1:0",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "anthropic.claude-3-haiku-20240307-v1:0",
]

_LAST_METRICS: dict[str, Any] = {
    "provider": "aws-bedrock",
    "model": config.LLM_MODEL,
    "latency_ms": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cached": False,
}


def last_call_metrics() -> dict[str, Any]:
    """Returnează metricile ultimului apel LLM (latență, tokeni, cache hit) pentru evenimentele din UI."""
    return dict(_LAST_METRICS)


def _get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        import boto3
        from botocore.config import Config as BotoConfig

        kwargs: dict[str, Any] = {
            "service_name": "bedrock-runtime",
            "region_name": config.AWS_DEFAULT_REGION,
            "config": BotoConfig(read_timeout=config.LLM_TIMEOUT_S, retries={"max_attempts": 2}),
        }
        if config.AWS_ACCESS_KEY_ID:
            kwargs["aws_access_key_id"] = config.AWS_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = config.AWS_SECRET_ACCESS_KEY
        if config.AWS_SESSION_TOKEN:
            kwargs["aws_session_token"] = config.AWS_SESSION_TOKEN
        _bedrock_client = boto3.client(**kwargs)
    return _bedrock_client


def _cache_key(system: str, user: str, temperature: float) -> Path:
    digest = hashlib.sha256(f"{system}\n---\n{user}\n---\n{temperature:.2f}".encode("utf-8")).hexdigest()
    return _CACHE_DIR / f"{digest}.json"


def _read_cache(key_path: Path) -> str | None:
    try:
        if key_path.exists():
            payload = json.loads(key_path.read_text(encoding="utf-8"))
            _LAST_METRICS.update({
                "model": payload.get("model", config.LLM_MODEL),
                "latency_ms": 1,
                "input_tokens": payload.get("input_tokens", 0),
                "output_tokens": payload.get("output_tokens", 0),
                "cached": True,
            })
            return payload.get("text")
    except Exception:
        return None
    return None


def _write_cache(key_path: Path, text: str, model_id: str, in_tok: int, out_tok: int) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key_path.write_text(
            json.dumps({
                "model": model_id,
                "text": text,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _extract_json(text: str) -> Any | None:
    """Modelele pun uneori JSON-ul în ```json ... ``` sau adaugă text în jur."""
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


def _call_bedrock(system: str, user: str, temperature: float, max_tokens: int) -> str | None:
    """Apelează AWS Bedrock Converse API cu cache pe disc, retry cu backoff și fallback pe modele."""
    key_path = _cache_key(system, user, temperature)
    cached_text = _read_cache(key_path)
    if cached_text is not None:
        return cached_text

    client = _get_bedrock_client()
    candidates = [config.LLM_MODEL] + [m for m in _FALLBACK_BEDROCK_MODELS if m != config.LLM_MODEL]
    last_exc: Exception | None = None

    for model_id in candidates:
        for attempt in range(2):
            t0 = time.perf_counter()
            try:
                resp = client.converse(
                    modelId=model_id,
                    system=[{"text": system}],
                    messages=[{"role": "user", "content": [{"text": user}]}],
                    inferenceConfig={"temperature": temperature, "maxTokens": max_tokens},
                )
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                blocks = resp.get("output", {}).get("message", {}).get("content", [])
                text = "".join(b.get("text", "") for b in blocks if "text" in b).strip()
                usage = resp.get("usage", {})
                in_tok = int(usage.get("inputTokens", 0))
                out_tok = int(usage.get("outputTokens", 0))
                if text:
                    _LAST_METRICS.update({
                        "model": model_id,
                        "latency_ms": elapsed_ms,
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "cached": False,
                    })
                    _write_cache(key_path, text, model_id, in_tok, out_tok)
                    return text
                break
            except Exception as exc:
                last_exc = exc
                err_msg = str(exc)
                if "ThrottlingException" in err_msg and attempt == 0:
                    time.sleep(0.6)
                    continue
                if "ExpiredToken" in err_msg or "UnrecognizedClientException" in err_msg:
                    log.warning("AWS Bedrock credentials expired or invalid: %s", exc)
                    return None
                break

    if last_exc:
        log.warning("AWS Bedrock call failed: %s", last_exc)
    return None


def chat_json(system: str, user: str, temperature: float = 0.0,
              max_tokens: int = 1500) -> dict | list | None:
    """Trimite un prompt și întoarce JSON parsat, sau None dacă LLM-ul e oprit / a eșuat."""
    if not config.llm_enabled():
        return None
    text = _call_bedrock(
        system=system + "\nRăspunde DOAR cu JSON valid, fără explicații în afara JSON-ului.",
        user=user,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _extract_json(text or "")


def chat_text(system: str, user: str, temperature: float = 0.2, max_tokens: int = 800) -> str | None:
    if not config.llm_enabled():
        return None
    return _call_bedrock(system=system, user=user, temperature=temperature, max_tokens=max_tokens)
