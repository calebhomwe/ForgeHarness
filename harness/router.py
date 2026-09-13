"""Model ladder + escalation + one small LLM client.

Ladder (config `models:`): local -> cheap -> standard -> heavy.
  - local  = LM Studio / Ollama on your machine ($0; classification, summaries, routing)
  - contract may pin a tier (complexity: local|cheap|standard|heavy)
  - each retry escalates one tier, so free/cheap models get first crack and
    Opus-class only runs when they've demonstrably failed (doc-46 ladder, automated)

Model entries may be a plain string (uses the default `llm_base_url`/`llm_key_env`) or a
dict pinning its own endpoint: {name: "qwen2.5-coder-14b", base_url: "http://localhost:1234/v1"}.
That's how LM Studio (:1234), Ollama (:11434), OpenRouter, or a LiteLLM proxy coexist.
Localhost endpoints don't require an API key.
"""
import json
import os
import time
import urllib.error
import urllib.request

LADDER = ["local", "cheap", "standard", "heavy"]


def pick_model(cfg, complexity: str, attempt_n: int):
    ladder = [t for t in LADDER if t in cfg["models"]]  # skip tiers you haven't configured
    start = complexity if complexity in ladder else ("standard" if "standard" in ladder else ladder[0])
    base = ladder.index(start)
    tier = ladder[min(base + max(0, attempt_n - 1), len(ladder) - 1)]
    return cfg["models"][tier]


def model_name(spec) -> str:
    return spec["name"] if isinstance(spec, dict) else str(spec)


def llm_chat(cfg, model, messages: list, max_tokens: int = 4000) -> dict:
    """model: str or {name, base_url?, key_env?}. Returns {'text', 'cost_usd'}."""
    if isinstance(model, dict):
        name = model["name"]
        base = model.get("base_url", cfg.get("llm_base_url", "https://openrouter.ai/api/v1"))
        key_env = model.get("key_env", cfg.get("llm_key_env", "OPENROUTER_API_KEY"))
    else:
        name = str(model)
        base = cfg.get("llm_base_url", "https://openrouter.ai/api/v1")
        key_env = cfg.get("llm_key_env", "OPENROUTER_API_KEY")
    base = base.rstrip("/")
    is_local = "localhost" in base or "127.0.0.1" in base
    key = os.getenv(key_env, "")
    if not key and not is_local:
        raise RuntimeError(f"Set {key_env} in environment/.env for endpoint {base}")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps({"model": name, "messages": messages,
                         "max_tokens": max_tokens, "usage": {"include": True}}).encode(),
        headers=headers)
    timeout = float(cfg.get("llm_timeout_s", 600))
    retries = max(0, int(cfg.get("llm_retry_attempts", 1)))
    backoff = max(0.0, float(cfg.get("llm_retry_backoff_s", 0.25)))
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as exc:
            # Do not retry auth, permission, or request-shape failures. Retry only
            # statuses that conventionally indicate transient provider pressure.
            retryable = exc.code in {408, 425, 429, 500, 502, 503, 504}
            if not retryable or attempt >= retries:
                raise
            if backoff:
                time.sleep(backoff * (2 ** attempt))
        except (urllib.error.URLError, TimeoutError):
            if attempt >= retries:
                raise
            if backoff:
                time.sleep(backoff * (2 ** attempt))
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {}) or {}
    cost = 0.0 if is_local else float(usage.get("cost", 0.0) or data.get("response_cost", 0.0) or 0.0)
    return {"text": text, "cost_usd": cost}
