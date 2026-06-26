"""
Jarvis Mark II — Pre-configured provider profiles.

Every built-in provider Jarvis knows about is declared here as a
``ProviderProfile`` instance.  The ``BUILTIN_PROFILES`` dict is the
single source of truth — the registry merges these with user config
at startup.
"""

from .base import ProviderProfile

# ── Helper ──────────────────────────────────────────────────────────────────


def _profile(
    name: str,
    display_name: str,
    description: str,
    base_url: str,
    env_vars: tuple[str, ...] = (),
    auth_type: str = "api_key",
    supports_vision: bool = False,
    fallback_models: tuple[str, ...] = (),
) -> ProviderProfile:
    """Shorthand to build a ``ProviderProfile`` with less boilerplate."""
    return ProviderProfile(
        name=name,
        display_name=display_name,
        description=description,
        base_url=base_url,
        env_vars=env_vars,
        auth_type=auth_type,
        supports_vision=supports_vision,
        fallback_models=fallback_models,
    )


# ── Profiles ────────────────────────────────────────────────────────────────

BUILTIN_PROFILES: dict[str, ProviderProfile] = {}

# -- OpenAI ------------------------------------------------------------------
BUILTIN_PROFILES["openai"] = _profile(
    name="openai",
    display_name="OpenAI",
    description="GPT-4o, GPT-4, GPT-3.5 via OpenAI API",
    base_url="https://api.openai.com/v1",
    env_vars=("OPENAI_API_KEY", "OPENAI_KEY"),
    auth_type="api_key",
    supports_vision=True,
    fallback_models=(
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    ),
)

# -- Anthropic ---------------------------------------------------------------
# NOTE: Anthropic's native API uses /v1/messages, not the OpenAI /chat/completions
# format.  Jarvis's LLMCore speaks OpenAI-compatible HTTP, so Anthropic support
# requires a translation layer or a proxy.  The profile is included for config
# completeness and future compatibility.
BUILTIN_PROFILES["anthropic"] = _profile(
    name="anthropic",
    display_name="Anthropic",
    description="Claude 3.5 Sonnet, Haiku via Anthropic API",
    base_url="https://api.anthropic.com/v1",
    env_vars=("ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "CLAUDE_API_KEY"),
    auth_type="api_key",
    supports_vision=True,
    fallback_models=(
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
    ),
)

# -- OpenRouter --------------------------------------------------------------
BUILTIN_PROFILES["openrouter"] = _profile(
    name="openrouter",
    display_name="OpenRouter",
    description="Multi-model gateway with unified billing",
    base_url="https://openrouter.ai/api/v1",
    env_vars=("OPENROUTER_API_KEY", "OPENROUTER_KEY"),
    auth_type="api_key",
    supports_vision=True,
    fallback_models=(
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "anthropic/claude-3.5-sonnet",
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.3-70b-instruct",
        "mistral/mistral-large-2411",
        "deepseek/deepseek-chat",
    ),
)

# -- Ollama (local) ----------------------------------------------------------
BUILTIN_PROFILES["ollama"] = _profile(
    name="ollama",
    display_name="Ollama",
    description="Local open-source models via Ollama",
    base_url="http://localhost:11434/v1",
    env_vars=(),
    auth_type="none",
    supports_vision=True,
    fallback_models=(
        "llama3.2:latest",
        "llama3.1:latest",
        "mistral:latest",
        "qwen2.5:latest",
        "phi4:latest",
        "gemma2:latest",
    ),
)

# -- OpenCode Zen ------------------------------------------------------------
BUILTIN_PROFILES["opencode-zen"] = _profile(
    name="opencode-zen",
    display_name="OpenCode Zen",
    description="OpenCode AI Zen API (Hermes/OpenCode models)",
    base_url="https://opencode.ai/zen/v1",
    env_vars=("OPENCODE_ZEN_API_KEY", "OPENCODE_API_KEY", "ZEN_API_KEY"),
    auth_type="api_key",
    supports_vision=True,
    fallback_models=(
        "big-pickle",
        "hermes-3-llama-3.1-405b",
        "hermes-3-llama-3.1-70b",
        "hermes-2-pro-mistral-7b",
        "hermes-2-theta-llama-3-8b",
    ),
)

# -- Grok (xAI) --------------------------------------------------------------
BUILTIN_PROFILES["grok"] = _profile(
    name="grok",
    display_name="xAI Grok",
    description="Grok models via xAI API",
    base_url="https://api.x.ai/v1",
    env_vars=("XAI_API_KEY", "GROK_API_KEY", "XAI_KEY"),
    auth_type="api_key",
    supports_vision=True,
    fallback_models=(
        "grok-2-1212",
        "grok-2-mini",
        "grok-beta",
    ),
)

# -- Gemini (Google) ---------------------------------------------------------
# Google provides an OpenAI-compatible endpoint at:
#   https://generativelanguage.googleapis.com/v1beta/openai
# which is what Jarvis uses here.
BUILTIN_PROFILES["gemini"] = _profile(
    name="gemini",
    display_name="Google Gemini",
    description="Gemini 2.0, 1.5 Pro via Google AI OpenAI-compat endpoint",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    env_vars=("GEMINI_API_KEY", "GOOGLE_API_KEY", "PALM_API_KEY"),
    auth_type="api_key",
    supports_vision=True,
    fallback_models=(
        "gemini-2.0-flash-001",
        "gemini-2.0-flash-lite-preview-02-05",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ),
)

# -- DeepSeek ----------------------------------------------------------------
BUILTIN_PROFILES["deepseek"] = _profile(
    name="deepseek",
    display_name="DeepSeek",
    description="DeepSeek Chat & Reasoner via official API",
    base_url="https://api.deepseek.com/v1",
    env_vars=("DEEPSEEK_API_KEY", "DEEPSEEK_KEY"),
    auth_type="api_key",
    supports_vision=False,
    fallback_models=(
        "deepseek-chat",
        "deepseek-reasoner",
    ),
)

# -- Together AI -------------------------------------------------------------
BUILTIN_PROFILES["together"] = _profile(
    name="together",
    display_name="Together AI",
    description="Open-source model inference via Together API",
    base_url="https://api.together.xyz/v1",
    env_vars=("TOGETHER_API_KEY", "TOGETHER_KEY"),
    auth_type="api_key",
    supports_vision=True,
    fallback_models=(
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "Qwen/Qwen2.5-72B-Instruct-Turbo",
        "deepseek-ai/deepseek-llm-67b-chat",
    ),
)

# -- Custom / Bring-your-own -------------------------------------------------
BUILTIN_PROFILES["custom"] = _profile(
    name="custom",
    display_name="Custom Provider",
    description="Bring your own OpenAI-compatible endpoint",
    base_url="",
    env_vars=("CUSTOM_API_KEY", "CUSTOM_KEY"),
    auth_type="api_key",
    supports_vision=False,
    fallback_models=(),
)


# ── Lookup helper ────────────────────────────────────────────────────────────


def get_builtin_profile(name: str) -> ProviderProfile | None:
    """Return the built-in profile for *name*, or None."""
    return BUILTIN_PROFILES.get(name)
