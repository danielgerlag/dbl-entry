"""LLM access via Microsoft Foundry (Azure OpenAI) using Azure CLI credentials.

Configuration comes from environment variables, loaded from `evals/.env` (gitignored; see `.env.example`).
"""
import os
import random
import time
from pathlib import Path

from azure.identity import AzureCliCredential, get_bearer_token_provider
from openai import AzureOpenAI, BadRequestError, RateLimitError


def _load_env(path=Path(__file__).parent / ".env"):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


_load_env()


def _require(name):
    if name not in os.environ:
        raise RuntimeError(f"{name} is not set; copy evals/.env.example to evals/.env and fill it in")
    return os.environ[name]


ENDPOINT = _require("EVAL_ENDPOINT")
SUBSCRIPTION = _require("EVAL_SUBSCRIPTION")
AGENT_MODEL = _require("EVAL_AGENT_MODEL")
REFLECTION_MODEL = _require("EVAL_REFLECTION_MODEL")
API_VERSION = os.environ.get("EVAL_API_VERSION", "2025-01-01-preview")

_client = None


def client() -> AzureOpenAI:
    global _client
    if _client is None:
        provider = get_bearer_token_provider(
            AzureCliCredential(subscription=SUBSCRIPTION), "https://cognitiveservices.azure.com/.default"
        )
        _client = AzureOpenAI(azure_endpoint=ENDPOINT, azure_ad_token_provider=provider,
                              api_version=API_VERSION, max_retries=2)
    return _client


_NO_TEMPERATURE = set()


def complete(model, messages, **kw):
    # Token-per-minute quotas on some deployments need longer waits than the SDK's default backoff.
    for attempt in range(12):
        if model in _NO_TEMPERATURE:
            kw.pop("temperature", None)
        try:
            return client().chat.completions.create(model=model, messages=messages, **kw)
        except BadRequestError as e:
            if "temperature" not in str(e) or "temperature" not in kw:
                raise
            _NO_TEMPERATURE.add(model)
        except RateLimitError:
            if attempt == 11:
                raise
            time.sleep(min(15 * (attempt + 1), 60) + random.random() * 5)
