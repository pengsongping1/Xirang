"""Recipe cache — the self-evolution engine.

A "recipe" is a successful action sequence cached from a prior turn. On new
input, we hash the user's intent into a fingerprint and look it up. Hits skip
the full planning phase and hint the agent directly at known-good steps.

Storage: line-delimited JSON at ~/.xirang/recipes.jsonl (grep-friendly, no DB).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Recipe:
    fingerprint: str
    intent_sample: str                  # the original user message (truncated)
    steps: list[dict] = field(default_factory=list)  # [{tool, args_template}]
    hit_count: int = 0
    success_rate: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)


# ---- fingerprinting ----
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "i", "me", "my", "you",
    "your", "please", "can", "could", "would", "to", "of", "for", "in", "on",
    "and", "or", "but", "with", "at", "by", "from", "this", "that",
    "能", "请", "帮", "我", "一下", "的", "了", "是", "在", "把", "给",
}


def fingerprint(text: str) -> str:
    """Cheap semantic hash: lowercase keywords, stripped and sorted."""
    text = text.lower()
    tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text)
    tokens = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
    if not tokens:
        return ""
    # Keep token order stable but dedupe
    seen: set[str] = set()
    uniq: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return " ".join(uniq[:12])


# ---- store ----

def _load_all(path: Path) -> list[Recipe]:
    if not path.exists():
        return []
    out: list[Recipe] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Recipe(**json.loads(line)))
        except Exception:
            continue
    return out


def _save_all(path: Path, recipes: list[Recipe]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(asdict(r), ensure_ascii=False) for r in recipes) + "\n",
        encoding="utf-8",
    )


def lookup(path: Path, user_text: str) -> Recipe | None:
    """Find a recipe whose fingerprint overlaps with the query."""
    fp = fingerprint(user_text)
    if not fp:
        return None
    query_tokens = set(fp.split())
    best: tuple[float, Recipe] | None = None
    for r in _load_all(path):
        rec_tokens = set(r.fingerprint.split())
        if not rec_tokens:
            continue
        overlap = len(query_tokens & rec_tokens) / max(len(query_tokens | rec_tokens), 1)
        if overlap >= 0.5:  # 50% Jaccard threshold
            if best is None or overlap > best[0]:
                best = (overlap, r)
    return best[1] if best else None


def record(path: Path, user_text: str, steps: list[dict]) -> None:
    """Save (or bump) a recipe. Dedupes by fingerprint."""
    fp = fingerprint(user_text)
    if not fp or not steps:
        return
    recipes = _load_all(path)
    for r in recipes:
        if r.fingerprint == fp:
            r.hit_count += 1
            r.last_used_at = time.time()
            # Prefer shorter successful trace
            if len(steps) < len(r.steps):
                r.steps = steps
            _save_all(path, recipes)
            return
    recipes.append(
        Recipe(
            fingerprint=fp,
            intent_sample=user_text[:200],
            steps=steps,
        )
    )
    _save_all(path, recipes)


def render_hint(recipe: Recipe) -> str:
    """Format a recipe as a system-prompt hint."""
    tool_names = [s.get("tool", "?") for s in recipe.steps]
    return (
        f"\n# Recipe cache hit (used {recipe.hit_count + 1} times)\n"
        f"Similar past task: \"{recipe.intent_sample}\"\n"
        f"Successful tool sequence was: {' → '.join(tool_names)}\n"
        f"You MAY follow this sequence if the task truly matches. Skip it if not.\n"
    )


def list_all(path: Path) -> list[Recipe]:
    return sorted(_load_all(path), key=lambda r: -r.hit_count)
