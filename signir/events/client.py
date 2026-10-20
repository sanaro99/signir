"""Small, bounded clients for explicitly configured self-hosted inference servers."""
import hashlib
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from pydantic import Field, model_validator
from typing import Literal

from .schema import StrictModel


def sha256(value):
    raw = value if isinstance(value, bytes) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f"non-JSON constant: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


class ExtractionError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class ModelConfig(StrictModel):
    backend: Literal["ollama", "vllm"]
    endpoint: str
    model: str = Field(min_length=1)
    model_revision: str | None = None
    api_key_env: str | None = None
    timeout_seconds: int = Field(default=180, ge=1, le=3600)
    context_tokens: int = Field(default=32768, ge=2048, le=1048576)
    max_output_tokens: int = Field(default=8192, ge=256, le=131072)
    max_response_bytes: int = Field(default=2097152, ge=1, le=16777216)
    lexicon: str | None = None

    @model_validator(mode="after")
    def valid_endpoint(self):
        url = urllib.parse.urlsplit(self.endpoint)
        if url.scheme not in ("http", "https") or not url.hostname:
            raise ValueError("endpoint must be an HTTP(S) server base URL")
        if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("endpoint must contain only scheme, host and optional port")
        if self.max_output_tokens >= self.context_tokens:
            raise ValueError("output budget must be smaller than context")
        return self


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.traces = []
        # Never send local corpus requests through ambient HTTP proxy configuration.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def extract(self, messages, schema):
        config = self.config
        if config.backend == "ollama":
            path = "/api/chat"
            body = {"model": config.model, "messages": messages, "stream": False,
                    "format": schema, "options": {"temperature": 0, "seed": 0,
                    "num_ctx": config.context_tokens, "num_predict": config.max_output_tokens}}
        else:
            path = "/v1/chat/completions"
            body = {"model": config.model, "messages": messages, "stream": False,
                    "temperature": 0, "seed": 0, "max_tokens": config.max_output_tokens,
                    "structured_outputs": {"json": schema}}
        trace = {"backend": config.backend, "endpoint": config.endpoint, "request": body,
                 "request_sha256": sha256(body), "configured_model": config.model,
                 "declared_model_revision": config.model_revision,
                 "revision_verified": False}
        self.traces.append(trace)
        start = time.monotonic()
        try:
            # Conservative byte budget, not a tokenizer or proof of server context capacity.
            input_bytes = len(json.dumps([messages, schema], ensure_ascii=False).encode())
            trace["input_utf8_bytes"] = input_bytes
            if input_bytes + config.max_output_tokens > config.context_tokens:
                raise ExtractionError("context_budget_exceeded",
                                      "input exceeds conservative context budget; shorten the row")
            headers = {"Content-Type": "application/json"}
            if config.api_key_env:
                key = os.environ.get(config.api_key_env)
                if not key:
                    raise ExtractionError("missing_credential", "configured API key environment variable is unset")
                headers["Authorization"] = "Bearer " + key
            request = urllib.request.Request(config.endpoint.rstrip("/") + path,
                                             data=json.dumps(body).encode(), headers=headers)
            with self.opener.open(request, timeout=config.timeout_seconds) as response:
                raw = response.read(config.max_response_bytes + 1)
                trace["http_status"] = response.status
            if len(raw) > config.max_response_bytes:
                raise ExtractionError("response_too_large", "server response exceeds byte limit")
            trace["raw_response"] = raw.decode("utf-8")
            trace["response_sha256"] = sha256(raw)
            reply = strict_json(trace["raw_response"])
            if not isinstance(reply, dict):
                raise ExtractionError("invalid_response", "response must be a JSON object")
            if reply.get("error"):
                raise ExtractionError("server_error", "inference server reported an error")
            if reply.get("model") != config.model:
                raise ExtractionError("model_mismatch", "returned model differs from configured model")
            trace["returned_model"] = reply["model"]
            if config.backend == "ollama":
                if reply.get("done") is not True or reply.get("done_reason") != "stop":
                    raise ExtractionError("incomplete_response", "generation did not finish with stop")
                message = reply["message"]
            else:
                choices = reply["choices"]
                if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
                    raise ExtractionError("incomplete_response", "generation did not finish with one stopped choice")
                message = choices[0]["message"]
            if message.get("refusal") or message.get("tool_calls"):
                raise ExtractionError("model_refusal", "model refused extraction or requested a tool")
            content = message["content"]
            if not isinstance(content, str):
                raise ExtractionError("invalid_response", "model content must be JSON text")
            try:
                return strict_json(content)
            except (ValueError, TypeError, RecursionError) as exc:
                raise ExtractionError("invalid_json", "model content is not strict JSON") from exc
        except ExtractionError as exc:
            trace["error"] = exc.code
            raise
        except urllib.error.HTTPError as exc:
            trace["error"] = "http_error"
            trace["http_status"] = exc.code
            exc.close()
            raise ExtractionError("http_error", f"inference HTTP status {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            trace["error"] = "transport_error"
            raise ExtractionError("transport_error", "inference connection failed or timed out") from exc
        except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
            trace["error"] = "invalid_response"
            raise ExtractionError("invalid_response", "malformed inference response") from exc
        finally:
            trace["elapsed_seconds"] = time.monotonic() - start
