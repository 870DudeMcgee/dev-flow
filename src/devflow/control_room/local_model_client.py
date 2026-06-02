import json
import os
import urllib.request
import urllib.error

class LocalModelClientError(Exception):
    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

class LocalModelClient:
    def __init__(
        self,
        base_url: str | None = None,
        model_id: str | None = None,
        timeout_seconds: float | None = None,
        temperature: float | None = None,
    ):
        self.base_url = base_url or os.environ.get("LOCAL_MODEL_BASE_URL", "http://127.0.0.1:8080/v1")
        self.model_id = model_id or os.environ.get("LOCAL_MODEL_ID")
        
        # Parse timeout
        timeout_env = os.environ.get("LOCAL_MODEL_TIMEOUT_SECONDS", "120")
        if timeout_seconds is not None:
            self.timeout = float(timeout_seconds)
        else:
            try:
                self.timeout = float(timeout_env)
            except ValueError:
                self.timeout = 120.0
                
        # Parse temperature
        temp_env = os.environ.get("LOCAL_MODEL_TEMPERATURE", "0")
        if temperature is not None:
            self.temperature = float(temperature)
        else:
            try:
                self.temperature = float(temp_env)
            except ValueError:
                self.temperature = 0.0

    def get_completions_url(self) -> str:
        base = self.base_url.rstrip("/")
        if not base.endswith("/v1"):
            return f"{base}/v1/chat/completions"
        return f"{base}/chat/completions"

    def chat_completion(self, system_prompt: str, user_prompt: str) -> dict:
        if not self.model_id:
            raise LocalModelClientError("LOCAL_MODEL_ID is missing. Please set the environment variable or pass --model.")

        # Hard cap prompt lengths to protect the endpoint and memory
        MAX_PROMPT_CHARS = 20000
        if len(system_prompt) > MAX_PROMPT_CHARS:
            system_prompt = system_prompt[:MAX_PROMPT_CHARS]
        if len(user_prompt) > MAX_PROMPT_CHARS:
            user_prompt = user_prompt[:MAX_PROMPT_CHARS]

        url = self.get_completions_url()
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
        }
        
        headers = {
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                MAX_RESPONSE_BYTES = 2000000
                res_data = response.read(MAX_RESPONSE_BYTES).decode("utf-8")
                response_json = json.loads(res_data)
                return {
                    "url": url,
                    "payload": payload,
                    "response": response_json,
                    "status_code": response.status,
                }
        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                err_body = ""
            raise LocalModelClientError(
                f"HTTP Error {exc.code}: {exc.reason}",
                status_code=exc.code,
                response_body=err_body,
            ) from exc
        except urllib.error.URLError as exc:
            raise LocalModelClientError(
                f"Local model server at {url} is unreachable: {exc.reason}"
            ) from exc
        except Exception as exc:
            raise LocalModelClientError(f"Request failed: {exc}") from exc
