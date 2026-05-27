import json
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class PromptRequest:
    """Consolidated parameter request for a model invocation prompt."""
    system_instruction: str
    prompt: str
    temperature: float = 0.2
    json_mode: bool = False
    timeout: int = 300

@dataclass
class PromptResponse:
    """Structured response containing invocation result meta and text payload."""
    text: str
    model: str
    success: bool
    error_message: Optional[str] = None

class ModelClient:
    """Base model execution client interface at the gateway seam."""
    def call(self, request: PromptRequest) -> PromptResponse:
        raise NotImplementedError

class MockClient(ModelClient):
    """Networkless mock model execution client for tests and offline runs."""
    def __init__(self, response_text: str, should_fail: bool = False):
        self.response_text = response_text
        self.should_fail = should_fail
        
    def call(self, request: PromptRequest) -> PromptResponse:
        if self.should_fail:
            return PromptResponse(text="", model="mock-fail", success=False, error_message="Mock connection error")
        return PromptResponse(text=self.response_text, model="mock-success", success=True)

class GeminiClient(ModelClient):
    """Polymorphic Google Gemini API wrapper client adapter."""
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model = model
        
    def call(self, request: PromptRequest) -> PromptResponse:
        if not self.api_key:
            return PromptResponse(text="", model=self.model, success=False, error_message="API key missing")

            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": request.prompt}]}],
            "systemInstruction": {"parts": [{"text": request.system_instruction}]}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=request.timeout) as res:
                res_data = json.loads(res.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return PromptResponse(text=parts[0].get("text", ""), model=self.model, success=True)
                return PromptResponse(text="", model=self.model, success=False, error_message="Empty response candidates")
        except Exception as e:
            return PromptResponse(text="", model=self.model, success=False, error_message=str(e))

class ModelGateway:
    """The deep Model Gateway manager handling model routing, failover chains and telemetry."""
    def __init__(self, primary: ModelClient, fallbacks: List[ModelClient] = None):
        self.primary = primary
        self.fallbacks = fallbacks or []
        
    def invoke(self, request: PromptRequest) -> PromptResponse:
        """Invokes a prompt using primary client, failing over to fallback chain on error."""
        clients = [self.primary] + self.fallbacks
        last_error = "No client configured"
        for client in clients:
            res = client.call(request)
            if res.success:
                return res
            last_error = res.error_message or "Unknown model client failure"
        return PromptResponse(text="", model="unknown", success=False, error_message=last_error)
