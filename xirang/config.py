"""Config: env vars, home dir, model selection."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, find_dotenv


PROFILE_DEFAULTS = {
    "fast": {"max_output_tokens": 1600, "max_tool_iters": 6},
    "balanced": {"max_output_tokens": 3200, "max_tool_iters": 12},
    "deep": {"max_output_tokens": 6400, "max_tool_iters": 18},
}


PROVIDER_PRESETS = {
    "anthropic": {
        "client": "anthropic",
        "api_env": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
        "model_env": "XIRANG_ANTHROPIC_MODEL",
        "default_model": "claude-opus-4-7",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "default_base_url": None,
        "requires_api_key": True,
    },
    "openai": {
        "client": "openai",
        "api_env": ("OPENAI_API_KEY",),
        "model_env": "XIRANG_OPENAI_MODEL",
        "default_model": "gpt-4o",
        "base_url_env": "XIRANG_OPENAI_BASE_URL",
        "default_base_url": None,
        "requires_api_key": True,
    },
    "deepseek": {
        "client": "openai",
        "api_env": ("DEEPSEEK_API_KEY",),
        "model_env": "XIRANG_DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
        "base_url_env": "XIRANG_DEEPSEEK_BASE_URL",
        "default_base_url": "https://api.deepseek.com/v1",
        "requires_api_key": True,
    },
    "ollama": {
        "client": "openai",
        "api_env": ("OLLAMA_API_KEY",),
        "model_env": "XIRANG_OLLAMA_MODEL",
        "default_model": "qwen2.5-coder:7b",
        "base_url_env": "XIRANG_OLLAMA_BASE_URL",
        "default_base_url": "http://127.0.0.1:11434/v1",
        "requires_api_key": False,
    },
    "lmstudio": {
        "client": "openai",
        "api_env": ("LMSTUDIO_API_KEY",),
        "model_env": "XIRANG_LMSTUDIO_MODEL",
        "default_model": "local-model",
        "base_url_env": "XIRANG_LMSTUDIO_BASE_URL",
        "default_base_url": "http://127.0.0.1:1234/v1",
        "requires_api_key": False,
    },
    "openrouter": {
        "client": "openai",
        "api_env": ("OPENROUTER_API_KEY",),
        "model_env": "XIRANG_OPENROUTER_MODEL",
        "default_model": "qwen/qwen3-coder:free",
        "base_url_env": "XIRANG_OPENROUTER_BASE_URL",
        "default_base_url": "https://openrouter.ai/api/v1",
        "requires_api_key": True,
    },
    "groq": {
        "client": "openai",
        "api_env": ("GROQ_API_KEY",),
        "model_env": "XIRANG_GROQ_MODEL",
        "default_model": "llama-3.1-8b-instant",
        "base_url_env": "XIRANG_GROQ_BASE_URL",
        "default_base_url": "https://api.groq.com/openai/v1",
        "requires_api_key": True,
    },
    "together": {
        "client": "openai",
        "api_env": ("TOGETHER_API_KEY",),
        "model_env": "XIRANG_TOGETHER_MODEL",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        "base_url_env": "XIRANG_TOGETHER_BASE_URL",
        "default_base_url": "https://api.together.xyz/v1",
        "requires_api_key": True,
    },
    "fireworks": {
        "client": "openai",
        "api_env": ("FIREWORKS_API_KEY",),
        "model_env": "XIRANG_FIREWORKS_MODEL",
        "default_model": "accounts/fireworks/models/llama4-maverick-instruct-basic",
        "base_url_env": "XIRANG_FIREWORKS_BASE_URL",
        "default_base_url": "https://api.fireworks.ai/inference/v1",
        "requires_api_key": True,
    },
    "openai_compat": {
        "client": "openai",
        "api_env": ("OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"),
        "model_env": "XIRANG_OPENAI_COMPAT_MODEL",
        "default_model": "gpt-4o-mini",
        "base_url_env": "XIRANG_OPENAI_COMPAT_BASE_URL",
        "default_base_url": "http://127.0.0.1:8000/v1",
        "requires_api_key": False,
    },
}


@dataclass
class Config:
    brand: str
    provider: str
    provider_client: str
    model: str
    api_key: str
    base_url: str | None
    provider_requires_api_key: bool
    mode: str
    response_profile: str
    max_output_tokens: int
    max_tool_iters: int
    autosave_on_turn: bool
    memory_context_budget_bytes: int
    home: Path
    audit_path: Path
    recipes_path: Path
    memory_dir: Path
    personas_dir: Path
    skilllets_dir: Path
    catalogs_dir: Path

    @property
    def is_anthropic(self) -> bool:
        return self.provider_client == "anthropic"


def _resolve_home(raw: str | None = None, *, migrate_legacy: bool = True) -> Path:
    raw = raw or os.getenv("XIRANG_HOME") or os.getenv("MORROW_HOME")
    home = Path(raw).expanduser() if raw else Path.home() / ".xirang"
    if migrate_legacy:
        _maybe_migrate_legacy_home(home)
    (home / "memory").mkdir(parents=True, exist_ok=True)
    (home / "personas").mkdir(parents=True, exist_ok=True)
    (home / "skilllets").mkdir(parents=True, exist_ok=True)
    (home / "audit").mkdir(parents=True, exist_ok=True)
    (home / "catalogs").mkdir(parents=True, exist_ok=True)
    return home


def _legacy_key(name: str) -> str:
    if name.startswith("XIRANG_"):
        return "MORROW_" + name[len("XIRANG_"):]
    return name


def _env_value(env: dict[str, str], name: str, default: str | None = None) -> str | None:
    if name in env and env[name] != "":
        return env[name]
    legacy = _legacy_key(name)
    if legacy in env and env[legacy] != "":
        return env[legacy]
    return default


def _maybe_rewrite_legacy_env(fp: Path) -> None:
    if not fp.exists():
        return
    text = fp.read_text(encoding="utf-8")
    updated = text.replace("MORROW_", "XIRANG_").replace("~/.morrow", "~/.xirang").replace(".morrow", ".xirang")
    if updated != text:
        fp.write_text(updated, encoding="utf-8")


def _maybe_migrate_legacy_home(home: Path) -> None:
    if home.name == ".morrow":
        return
    if home.exists() and any(home.iterdir()):
        return
    legacy_raw = os.getenv("MORROW_HOME")
    legacy_home = Path(legacy_raw).expanduser() if legacy_raw else (Path.home() / ".morrow")
    if not legacy_home.exists() or legacy_home == home:
        return
    shutil.copytree(legacy_home, home, dirs_exist_ok=True)
    _maybe_rewrite_legacy_env(home / ".env")


def _cwd_env() -> dict[str, str]:
    env_path = find_dotenv(usecwd=True)
    if not env_path:
        return {}
    return {k: str(v) for k, v in dotenv_values(env_path).items() if v is not None}


def _home_env(home: Path) -> dict[str, str]:
    fp = home / ".env"
    if not fp.exists():
        return {}
    return {k: str(v) for k, v in dotenv_values(fp).items() if v is not None}


def _merged_env(home: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    env.update(_cwd_env())
    env.update(_home_env(home))
    env.update(os.environ)
    return env


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _profile_settings(profile: str) -> dict[str, int]:
    return PROFILE_DEFAULTS.get(profile, PROFILE_DEFAULTS["balanced"]).copy()


def provider_presets() -> dict[str, dict]:
    return {name: dict(preset) for name, preset in PROVIDER_PRESETS.items()}


def resolve_provider_preset(provider: str) -> dict:
    key = (provider or "anthropic").lower()
    preset = PROVIDER_PRESETS.get(key)
    if not preset:
        raise ValueError(f"Unknown provider: {provider}")
    return dict(preset)


def _env_first(env: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = env.get(name, "")
        if value:
            return value
    return ""


def load_config(provider_override: str | None = None) -> Config:
    cwd_env = _cwd_env()
    explicit_home = os.environ.get("XIRANG_HOME") or cwd_env.get("XIRANG_HOME")
    legacy_home = os.environ.get("MORROW_HOME") or cwd_env.get("MORROW_HOME")
    home = _resolve_home(explicit_home or legacy_home, migrate_legacy=not explicit_home)
    env = _merged_env(home)

    provider = (provider_override or _env_value(env, "XIRANG_PROVIDER", "anthropic")).lower()
    preset = resolve_provider_preset(provider)
    brand = _env_value(env, "XIRANG_BRAND", "Xirang · 息壤")
    mode = _env_value(env, "XIRANG_MODE", "default").lower()
    response_profile = _env_value(env, "XIRANG_PROFILE", "balanced").lower()
    if response_profile not in PROFILE_DEFAULTS:
        response_profile = "balanced"
    profile_settings = _profile_settings(response_profile)
    max_output_tokens = int(
        _env_value(env, "XIRANG_MAX_OUTPUT_TOKENS", str(profile_settings["max_output_tokens"]))
    )
    max_tool_iters = int(
        _env_value(env, "XIRANG_MAX_TOOL_ITERS", str(profile_settings["max_tool_iters"]))
    )
    autosave_on_turn = _parse_bool(_env_value(env, "XIRANG_AUTOSAVE_ON_TURN"), default=True)
    memory_context_budget_bytes = int(
        _env_value(env, "XIRANG_MEMORY_CONTEXT_BYTES", str(2 * 1024 * 1024))
    )

    api_key = _env_first(env, tuple(preset["api_env"]))
    if not api_key and not preset["requires_api_key"]:
        api_key = "not-needed"
    model = _env_value(env, str(preset["model_env"]), str(preset["default_model"]))
    base_url = _env_value(env, str(preset["base_url_env"]), str(preset["default_base_url"] or "")) or None

    if preset["requires_api_key"] and not api_key:
        raise RuntimeError(
            f"Missing API key for provider '{provider}'. "
            f"Set the appropriate env var (see .env.example)."
        )

    return Config(
        brand=brand,
        provider=provider,
        provider_client=preset["client"],
        model=model,
        api_key=api_key,
        base_url=base_url,
        provider_requires_api_key=bool(preset["requires_api_key"]),
        mode=mode,
        response_profile=response_profile,
        max_output_tokens=max_output_tokens,
        max_tool_iters=max_tool_iters,
        autosave_on_turn=autosave_on_turn,
        memory_context_budget_bytes=memory_context_budget_bytes,
        home=home,
        audit_path=home / "audit" / "events.jsonl",
        recipes_path=home / "recipes.jsonl",
        memory_dir=home / "memory",
        personas_dir=home / "personas",
        skilllets_dir=home / "skilllets",
        catalogs_dir=home / "catalogs",
    )
