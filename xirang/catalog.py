"""Catalogs for model providers and public APIs.

Xirang keeps a small built-in catalog for one-minute onboarding, and can import
larger local markdown catalogs such as:
- public-apis/public-apis README.md
- cheahjs/free-llm-api-resources README.md
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CatalogEntry:
    kind: str
    name: str
    description: str
    url: str = ""
    category: str = ""
    auth: str = ""
    https: str = ""
    cors: str = ""
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    source: str = "builtin"

    def searchable_text(self) -> str:
        return " ".join(
            [
                self.kind,
                self.name,
                self.description,
                self.category,
                self.auth,
                self.provider,
                self.model,
                self.url,
            ]
        ).lower()


BUILTIN_LLM_ENTRIES = [
    CatalogEntry(
        kind="llm",
        name="Ollama local",
        description="Local OpenAI-compatible endpoint. No cloud API key required; run ollama locally.",
        provider="ollama",
        model="qwen2.5-coder:7b",
        base_url="http://127.0.0.1:11434/v1",
        api_key_env="not required",
        url="https://ollama.com",
    ),
    CatalogEntry(
        kind="llm",
        name="LM Studio local",
        description="Local OpenAI-compatible endpoint served by LM Studio.",
        provider="lmstudio",
        model="local-model",
        base_url="http://127.0.0.1:1234/v1",
        api_key_env="not required",
        url="https://lmstudio.ai",
    ),
    CatalogEntry(
        kind="llm",
        name="OpenRouter free models",
        description="OpenAI-compatible router with multiple free model IDs and daily quotas.",
        provider="openrouter",
        model="qwen/qwen3-coder:free",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        url="https://openrouter.ai/models?max_price=0",
    ),
    CatalogEntry(
        kind="llm",
        name="Groq free tier",
        description="Fast OpenAI-compatible inference with free-tier limits.",
        provider="groq",
        model="llama-3.1-8b-instant",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        url="https://console.groq.com",
    ),
    CatalogEntry(
        kind="llm",
        name="Together AI free/open models",
        description="OpenAI-compatible hosted open models; free model availability depends on account limits.",
        provider="together",
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        url="https://api.together.xyz",
    ),
]


BUILTIN_API_ENTRIES = [
    CatalogEntry(kind="api", name="Dog CEO", description="Random dog images and breed data.", category="Animals", auth="No", https="Yes", cors="Yes", url="https://dog.ceo/dog-api/"),
    CatalogEntry(kind="api", name="Cat Facts", description="Daily cat facts.", category="Animals", auth="No", https="Yes", cors="No", url="https://alexwohlbruck.github.io/cat-facts/"),
    CatalogEntry(kind="api", name="Jikan", description="Unofficial MyAnimeList API.", category="Anime", auth="No", https="Yes", cors="Yes", url="https://jikan.moe"),
    CatalogEntry(kind="api", name="Open Library", description="Books, authors, and bibliographic data.", category="Books", auth="No", https="Yes", cors="Yes", url="https://openlibrary.org/developers/api"),
    CatalogEntry(kind="api", name="CoinGecko", description="Cryptocurrency prices and market data.", category="Cryptocurrency", auth="No", https="Yes", cors="Yes", url="https://www.coingecko.com/en/api"),
    CatalogEntry(kind="api", name="ExchangeRate.host", description="Foreign exchange and crypto rates.", category="Currency Exchange", auth="No", https="Yes", cors="Yes", url="https://exchangerate.host"),
    CatalogEntry(kind="api", name="Open-Meteo", description="Weather forecasts without API keys.", category="Weather", auth="No", https="Yes", cors="Yes", url="https://open-meteo.com"),
    CatalogEntry(kind="api", name="Nominatim", description="OpenStreetMap geocoding search API.", category="Geocoding", auth="No", https="Yes", cors="Yes", url="https://nominatim.org/release-docs/latest/api/Overview/"),
    CatalogEntry(kind="api", name="GitHub REST API", description="Repositories, users, issues, and pull requests.", category="Development", auth="OAuth", https="Yes", cors="Yes", url="https://docs.github.com/en/rest"),
    CatalogEntry(kind="api", name="Hacker News Firebase", description="Hacker News stories, users, and comments.", category="News", auth="No", https="Yes", cors="Yes", url="https://github.com/HackerNews/API"),
]


def _catalog_file(catalogs_dir: Path, kind: str) -> Path:
    catalogs_dir.mkdir(parents=True, exist_ok=True)
    return catalogs_dir / f"{kind}.jsonl"


def builtin_entries(kind: str = "all") -> list[CatalogEntry]:
    entries = [*BUILTIN_LLM_ENTRIES, *BUILTIN_API_ENTRIES]
    if kind == "all":
        return entries
    return [entry for entry in entries if entry.kind == kind]


def load_entries(catalogs_dir: Path, kind: str = "all") -> list[CatalogEntry]:
    entries = builtin_entries(kind)
    kinds = ["llm", "api"] if kind == "all" else [kind]
    for catalog_kind in kinds:
        fp = _catalog_file(catalogs_dir, catalog_kind)
        if not fp.exists():
            continue
        for line in fp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = CatalogEntry(**json.loads(line))
            except Exception:
                continue
            if kind == "all" or entry.kind == kind:
                entries.append(entry)
    return _dedupe(entries)


def save_entries(catalogs_dir: Path, kind: str, entries: list[CatalogEntry]) -> Path:
    fp = _catalog_file(catalogs_dir, kind)
    existing = [entry for entry in load_entries(catalogs_dir, kind) if entry.source != "builtin"]
    merged = _dedupe([*existing, *entries])
    fp.write_text(
        "\n".join(json.dumps(asdict(entry), ensure_ascii=False) for entry in merged) + "\n",
        encoding="utf-8",
    )
    return fp


def search(catalogs_dir: Path, query: str, kind: str = "all", limit: int = 12) -> list[CatalogEntry]:
    query = (query or "").strip().lower()
    entries = load_entries(catalogs_dir, kind)
    if not query:
        return entries[:limit]
    tokens = [token for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", query) if len(token) > 1]
    scored: list[tuple[int, CatalogEntry]] = []
    for entry in entries:
        haystack = entry.searchable_text()
        score = sum(1 for token in tokens if token in haystack)
        if query in haystack:
            score += 3
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1].kind, item[1].name.lower()))
    return [entry for _, entry in scored[:limit]]


def import_public_apis_readme(path: Path) -> list[CatalogEntry]:
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: list[CatalogEntry] = []
    category = ""
    row_re = re.compile(
        r"^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|?"
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^###\s+(.+)$", line)
        if heading:
            category = heading.group(1).strip()
            continue
        match = row_re.match(line)
        if not match:
            continue
        name, url, description, auth, https, cors = [part.strip() for part in match.groups()]
        if name.lower() == "api" or set(description) <= {"-", ":"}:
            continue
        entries.append(
            CatalogEntry(
                kind="api",
                name=_strip_markup(name),
                description=_strip_markup(description),
                url=url,
                category=category,
                auth=_strip_markup(auth),
                https=_strip_markup(https),
                cors=_strip_markup(cors),
                source=str(path),
            )
        )
    return _dedupe(entries)


def import_free_llm_readme(path: Path) -> list[CatalogEntry]:
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: list[CatalogEntry] = []
    provider_name = ""
    provider_url = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^###\s+\[([^\]]+)\]\(([^)]+)\)", line)
        if heading:
            provider_name, provider_url = heading.group(1).strip(), heading.group(2).strip()
            entries.append(
                CatalogEntry(
                    kind="llm",
                    name=provider_name,
                    description="Free or trial LLM API provider from free-llm-api-resources.",
                    provider=_provider_slug(provider_name),
                    url=provider_url,
                    source=str(path),
                )
            )
            continue
        model = re.match(r"^-\s+\[?([^\]]+?)\]?(?:\(([^)]+)\))?\s*$", line)
        if provider_name and model:
            label = _strip_markup(model.group(1)).strip()
            url = model.group(2) or provider_url
            if not label or label.lower().startswith(("free providers", "providers with")):
                continue
            entries.append(
                CatalogEntry(
                    kind="llm",
                    name=f"{provider_name}: {label}",
                    description=f"Model or resource listed under {provider_name}.",
                    provider=_provider_slug(provider_name),
                    model=label,
                    url=url,
                    source=str(path),
                )
            )
    return _dedupe(entries)


def import_catalog(catalogs_dir: Path, kind: str, path: Path) -> tuple[Path, int]:
    if kind == "api":
        entries = import_public_apis_readme(path)
    elif kind == "llm":
        entries = import_free_llm_readme(path)
    else:
        raise ValueError("kind must be 'api' or 'llm'")
    fp = save_entries(catalogs_dir, kind, entries)
    return fp, len(entries)


def format_entries(entries: list[CatalogEntry]) -> str:
    if not entries:
        return "No catalog matches."
    lines = ["**Catalog matches:**"]
    for entry in entries:
        parts = [f"`{entry.kind}`", f"**{entry.name}**"]
        if entry.category:
            parts.append(f"category={entry.category}")
        if entry.provider:
            parts.append(f"provider={entry.provider}")
        if entry.model:
            parts.append(f"model={entry.model}")
        if entry.auth:
            parts.append(f"auth={entry.auth}")
        if entry.url:
            parts.append(entry.url)
        lines.append("- " + " · ".join(parts) + f" — {entry.description}")
    return "\n".join(lines)


def _dedupe(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    seen: set[tuple[str, str, str]] = set()
    out: list[CatalogEntry] = []
    for entry in entries:
        key = (entry.kind, entry.name.lower(), entry.url.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def _strip_markup(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _provider_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    aliases = {
        "openrouter": "openrouter",
        "groq": "groq",
        "fireworks": "fireworks",
        "together_ai": "together",
        "nvidia_nim": "nvidia",
        "mistral_la_plateforme": "mistral",
        "github_models": "github_models",
    }
    return aliases.get(slug, slug)
