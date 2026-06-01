# Configuring Provider API Keys Safely

To ensure secure operations, Dev-Flow enforces strict safety boundaries regarding API keys and model provider execution. Under our trusted-local alpha policy:
1. **No literal API keys or secrets may ever be stored in the repository.**
2. **Provider configurations only reference environment variable names** (e.g., `api_key_env: OPENAI_API_KEY`).
3. **Local workers** (e.g., Ollama) are the only automated patch executors and must connect only via local loopback addresses.
4. **Remote/frontier API providers remain disabled or read-only/experimental** in the active control-room runtime.

---

## 1. How to Configure Your Shell

Josh, you should set your API keys locally in your shell environment. This keeps your secrets safely out of the codebase and Git history.

To export these variables in your active shell (e.g., inside `~/.zshrc`, `~/.bashrc`, or just in your active terminal session):

```bash
# Export the environment variables matching the provider configurations
export OPENAI_API_KEY="your-actual-openai-key-here"
export ANTHROPIC_API_KEY="your-actual-anthropic-key-here"
export GEMINI_API_KEY="your-actual-gemini-key-here"
export XAI_API_KEY="your-actual-grok-or-xai-key-here"
export GROK_API_KEY="your-actual-grok-or-xai-key-here"
export OPENAI_COMPATIBLE_API_KEY="your-actual-custom-key-here"
```

Once exported, Dev-Flow will load the keys dynamically from the environment during worker execution when resolving provider config files.

---

## 2. Safe Provider Config Schema

Provider configuration files live under `.devflow/providers/<provider-name>.yaml`. They map the adapter details and reference environment variables dynamically:

### Example: `.devflow/providers/openai.yaml`
```yaml
id: openai
provider: openai
adapter: openai_chat
base_url: https://api.openai.com/v1
api_key_env: OPENAI_API_KEY
default_timeout_seconds: 300
enabled: true
```

*Note: The `api_key_env` value must contain exactly the uppercase name of the environment variable containing the secret. Dev-Flow validators will automatically reject config files that attempt to write literal key structures (e.g. starting with `sk-`).*

---

## 3. Ollama Local Constraints

The Ollama provider is strictly validated to enforce local-only loopback boundaries. This prevents local tools from inadvertently sending local file diff patches or workspace context over unencrypted networks or remote endpoints.

Ollama's `base_url` is restricted to local loopback hosts:
- `http://localhost:<port>`
- `http://127.0.0.1:<port>`
- `http://[::1]:<port>`

Any external hostname or non-loopback IP address will cause the executor to fail closed.
