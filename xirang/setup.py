"""First-run setup helpers for ordinary users."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xirang import bundle
from xirang import catalog
from xirang import skilllet
from xirang.config import Config, provider_presets


@dataclass(frozen=True)
class ProviderGuide:
    name: str
    title: str
    signup_url: str
    key_env: str
    model_env: str
    recommended_model: str
    note: str


GUIDES = {
    "openrouter": ProviderGuide(
        name="openrouter",
        title="OpenRouter",
        signup_url="https://openrouter.ai/keys",
        key_env="OPENROUTER_API_KEY",
        model_env="XIRANG_OPENROUTER_MODEL",
        recommended_model="qwen/qwen3-coder:free",
        note="Best default for one-key setup: OpenAI-compatible, many free models, daily free quota.",
    ),
    "groq": ProviderGuide(
        name="groq",
        title="Groq",
        signup_url="https://console.groq.com/keys",
        key_env="GROQ_API_KEY",
        model_env="XIRANG_GROQ_MODEL",
        recommended_model="llama-3.1-8b-instant",
        note="Fast free-tier provider with simple OpenAI-compatible chat endpoints.",
    ),
    "together": ProviderGuide(
        name="together",
        title="Together AI",
        signup_url="https://api.together.xyz/settings/api-keys",
        key_env="TOGETHER_API_KEY",
        model_env="XIRANG_TOGETHER_MODEL",
        recommended_model="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        note="Good fallback if OpenRouter/Groq quota is unavailable.",
    ),
    "ollama": ProviderGuide(
        name="ollama",
        title="Ollama",
        signup_url="https://ollama.com/download",
        key_env="",
        model_env="XIRANG_OLLAMA_MODEL",
        recommended_model="qwen2.5-coder:7b",
        note="Local-only path. No API key, but the user must run Ollama separately.",
    ),
}


def setup_path(home: Path) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    return home / ".env"


def primary_key_env(provider: str) -> str:
    preset = provider_presets()[provider]
    return tuple(preset["api_env"])[0]


def recommended_model(provider: str) -> str:
    guide = GUIDES.get(provider)
    if guide:
        return guide.recommended_model
    return str(provider_presets()[provider]["default_model"])


def provider_env_values(
    provider: str,
    *,
    api_key: str = "",
    model: str = "",
    profile: str = "balanced",
) -> dict[str, str]:
    provider = provider.lower()
    presets = provider_presets()
    if provider not in presets:
        raise ValueError(f"Unknown provider: {provider}")

    preset = presets[provider]
    values = {
        "XIRANG_PROVIDER": provider,
        "XIRANG_PROFILE": profile,
        str(preset["model_env"]): model or recommended_model(provider),
    }
    base_url = preset.get("default_base_url")
    if base_url:
        values[str(preset["base_url_env"])] = str(base_url)
    if preset["requires_api_key"]:
        key_env = primary_key_env(provider)
        if not api_key:
            raise ValueError(f"{provider} requires an API key for {key_env}")
        values[key_env] = api_key.strip()
    return values


def update_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    lines: list[str] = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            lines.append(f"{key}={remaining.pop(key)}")
        else:
            lines.append(line)
    if lines and remaining:
        lines.append("")
    for key, value in remaining.items():
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def local_project_env_path(cwd: Path | None = None) -> Path | None:
    root = (cwd or Path.cwd()).expanduser()
    if not (root / ".env.example").exists():
        return None
    if not (root / "xirang").is_dir():
        return None
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    if 'name = "xirang"' not in text:
        return None
    return root / ".env"


def configure_provider(
    home: Path,
    provider: str,
    *,
    api_key: str = "",
    model: str = "",
    profile: str = "balanced",
) -> Path:
    values = provider_env_values(
        provider,
        api_key=api_key,
        model=model,
        profile=profile,
    )
    path = setup_path(home)
    update_env_file(path, values)
    return path


def sync_local_project_env(
    provider: str,
    *,
    api_key: str = "",
    model: str = "",
    profile: str = "balanced",
    cwd: Path | None = None,
) -> Path | None:
    path = local_project_env_path(cwd)
    if path is None:
        return None
    values = provider_env_values(
        provider,
        api_key=api_key,
        model=model,
        profile=profile,
    )
    update_env_file(path, values)
    return path


def doctor_rows(cfg: Config) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    rows.append(("ok", "home", str(cfg.home)))
    rows.append(("ok", "provider", cfg.provider))
    rows.append(("ok", "model", cfg.model))
    if cfg.provider_requires_api_key:
        status = "ok" if cfg.api_key else "fail"
        detail = f"{primary_key_env(cfg.provider)} is set" if cfg.api_key else "API key is missing"
        rows.append((status, "api key", detail))
    else:
        rows.append(("ok", "api key", "not required"))
    rows.append(("ok" if cfg.base_url else "warn", "base url", cfg.base_url or "provider default"))

    api_count = len(catalog.load_entries(cfg.catalogs_dir, "api"))
    llm_count = len(catalog.load_entries(cfg.catalogs_dir, "llm"))
    rows.append(("ok" if api_count else "warn", "api catalog", f"{api_count} entries"))
    rows.append(("ok" if llm_count else "warn", "llm catalog", f"{llm_count} entries"))

    genes = skilllet.list_all(cfg.skilllets_dir)
    mature = [
        item for item in genes
        if bundle.gene_maturity(item)["level"] in {"stable", "proven"}
    ]
    high_risk = [
        item for item in genes
        if bundle.gene_maturity(item)["risk"] == "high"
    ]
    rows.append(
        (
            "ok" if genes else "warn",
            "local genome",
            f"{len(genes)} genes, {len(mature)} stable/proven",
        )
    )
    rows.append(
        (
            "warn" if high_risk else "ok",
            "genome risk",
            f"{len(high_risk)} high-risk genes need manual review before proposal",
        )
    )
    return rows


def format_doctor(rows: list[tuple[str, str, str]]) -> str:
    icon = {"ok": "✓", "warn": "!", "fail": "✗"}
    return "\n".join(f"{icon.get(status, '?')} {name}: {detail}" for status, name, detail in rows)


def guide_text(provider: str = "openrouter") -> str:
    guide = GUIDES[provider]
    if guide.key_env:
        key_line = f"2) Paste the API key when Xirang asks for `{guide.key_env}`."
    else:
        key_line = "2) Start the local provider first; no API key is needed."
    return (
        f"{guide.title} setup\n"
        f"1) Open: {guide.signup_url}\n"
        f"{key_line}\n"
        f"3) Run: xirang -p \"你好\"\n"
        f"Default model: {guide.recommended_model}\n"
        f"Why: {guide.note}"
    )
