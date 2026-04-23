"""Skilllets — tiny local skills distilled from successful tool traces.

Recipes are fast hints. Skilllets are the next layer: a grep-friendly markdown
memory of how Xirang solved a task class before. They stay local, load as a
small index, and avoid depending on an external skills directory.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from xirang import persona as per
from xirang import recipe


MAX_SKILLLETS_IN_PROMPT = 8
MATCH_THRESHOLD = 0.38


@dataclass
class Skilllet:
    name: str
    slug: str
    fingerprint: str
    summary: str
    version: int = 3
    steps: list[dict] = field(default_factory=list)
    input_schema: dict = field(default_factory=dict)
    source_samples: list[str] = field(default_factory=list)
    hit_count: int = 0
    success_count: int = 1
    failure_count: int = 0
    chain_stats: dict[str, int] = field(default_factory=dict)
    owner_slug: str = ""
    inherited_from: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def tool_chain(self) -> str:
        return " → ".join(s.get("tool", "?") for s in self.steps) or "(no tools)"

    def to_markdown(self) -> str:
        meta = {
            "name": self.name,
            "slug": self.slug,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "hit_count": self.hit_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "chain_stats_json": json.dumps(self.chain_stats, ensure_ascii=False),
            "owner_slug": self.owner_slug,
            "inherited_from": self.inherited_from,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps_json": json.dumps(self.steps, ensure_ascii=False),
            "input_schema_json": json.dumps(self.input_schema, ensure_ascii=False),
            "source_samples_json": json.dumps(self.source_samples[-5:], ensure_ascii=False),
        }
        frontmatter = "\n".join(f"{k}: {v}" for k, v in meta.items())
        step_lines = [
            f"- `{s.get('tool', '?')}` with args: {', '.join(s.get('args_keys', [])) or '(none)'}"
            for s in self.steps
        ]
        sample_lines = [f"- {s}" for s in self.source_samples[-5:]]
        return (
            f"---\n{frontmatter}\n---\n\n"
            f"# {self.name}\n\n"
            f"{self.summary}\n\n"
            "## Tool Path\n"
            + ("\n".join(step_lines) if step_lines else "- (none)")
            + "\n\n## Input Schema\n"
            f"```json\n{json.dumps(self.input_schema, ensure_ascii=False, indent=2)}\n```\n"
            + "\n## Reliability\n"
            f"- success_count: {self.success_count}\n"
            f"- failure_count: {self.failure_count}\n"
            f"- hit_count: {self.hit_count}\n"
            f"- best_tool_chain: {self.tool_chain}\n"
            + "\n\n## Use When\n"
            f"- The user intent overlaps with: `{self.fingerprint}`\n"
            "- Prefer this path only when the current task truly matches.\n"
            "- Keep arguments fresh; do not blindly reuse old file paths or URLs.\n\n"
            "## Source Samples\n"
            + ("\n".join(sample_lines) if sample_lines else "- (none)")
            + "\n"
        )


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff-]+", "-", text).strip("-").lower()
    return slug[:60] or "skilllet"


def _skilllets_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path_for(skilllets_dir: Path, slug: str) -> Path:
    return _skilllets_dir(skilllets_dir) / f"{slug}.md"


def _scoped_slug(base_slug: str, owner_slug: str = "") -> str:
    if not owner_slug:
        return base_slug
    return _slugify(f"{owner_slug}-{base_slug}")


def _parse_frontmatter(text: str) -> dict:
    match = re.match(r"^---\n([\s\S]*?)\n---", text)
    if not match:
        return {}
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def load(path: Path) -> Skilllet | None:
    try:
        text = path.read_text(encoding="utf-8")
        meta = _parse_frontmatter(text)
        if not meta:
            return None
        steps = json.loads(meta.get("steps_json", "[]"))
        input_schema = json.loads(meta.get("input_schema_json", "{}"))
        samples = json.loads(meta.get("source_samples_json", "[]"))
        chain_stats = json.loads(meta.get("chain_stats_json", "{}"))
        name = meta.get("name", path.stem)
        summary_match = re.search(rf"^# {re.escape(name)}\n\n([\s\S]*?)(?:\n\n##|\Z)", text)
        summary = summary_match.group(1).strip() if summary_match else ""
        return Skilllet(
            name=name,
            slug=meta.get("slug", path.stem),
            fingerprint=meta.get("fingerprint", ""),
            summary=summary,
            version=int(meta.get("version", 1)),
            steps=steps if isinstance(steps, list) else [],
            input_schema=input_schema if isinstance(input_schema, dict) else {},
            source_samples=samples if isinstance(samples, list) else [],
            hit_count=int(meta.get("hit_count", 0)),
            success_count=int(meta.get("success_count", 1)),
            failure_count=int(meta.get("failure_count", 0)),
            chain_stats=chain_stats if isinstance(chain_stats, dict) else {},
            owner_slug=meta.get("owner_slug", ""),
            inherited_from=meta.get("inherited_from", ""),
            created_at=float(meta.get("created_at", time.time())),
            updated_at=float(meta.get("updated_at", time.time())),
        )
    except Exception:
        return None


def list_all(skilllets_dir: Path) -> list[Skilllet]:
    out: list[Skilllet] = []
    for fp in _skilllets_dir(skilllets_dir).glob("*.md"):
        item = load(fp)
        if item:
            out.append(item)
    return sorted(out, key=lambda s: (-s.hit_count, -s.updated_at))


def lookup(
    skilllets_dir: Path,
    user_text: str,
    owner_slug: str = "",
    personas_dir: Path | None = None,
) -> Skilllet | None:
    query_fp = recipe.fingerprint(user_text)
    if not query_fp:
        return None
    query_tokens = set(query_fp.split())
    best: tuple[float, Skilllet] | None = None
    for item in _eligible_items(skilllets_dir, owner_slug=owner_slug, personas_dir=personas_dir):
        score = _match_score(item, query_tokens)
        score += _owner_bonus(item, owner_slug, personas_dir)
        if score >= MATCH_THRESHOLD and (best is None or score > best[0]):
            best = (score, item)
    if not best:
        return None
    item = best[1]
    if owner_slug and item.owner_slug and item.owner_slug != owner_slug:
        return replace(item, inherited_from=item.owner_slug)
    return item


def upsert_from_trace(
    skilllets_dir: Path,
    user_text: str,
    steps: list[dict],
    owner_slug: str = "",
) -> Skilllet | None:
    fp = recipe.fingerprint(user_text)
    if not fp or not steps:
        return None
    existing = _find_existing(skilllets_dir, fp, owner_slug=owner_slug)
    chain_key = _chain_key(steps)

    if existing:
        existing.hit_count += 1
        existing.success_count += 1
        existing.updated_at = time.time()
        existing.fingerprint = _merge_fingerprint(existing.fingerprint, fp)
        existing.chain_stats = _merge_chain_stats(existing.chain_stats, chain_key)
        existing.input_schema = _merge_input_schema(existing.input_schema, _infer_input_schema(steps))
        sample = user_text[:200]
        if sample not in existing.source_samples:
            existing.source_samples.append(sample)
        existing.source_samples = existing.source_samples[-8:]
        existing.steps = _select_best_steps(existing, steps)
        existing.summary = _build_summary(existing, user_text)
        _path_for(skilllets_dir, existing.slug).write_text(existing.to_markdown(), encoding="utf-8")
        return existing

    tokens = fp.split()[:5]
    name = "Skilllet: " + (" ".join(tokens) if tokens else "workflow")
    slug = _scoped_slug(_slugify(" ".join(tokens) or user_text[:40]), owner_slug=owner_slug)
    item = Skilllet(
        name=name,
        slug=slug,
        fingerprint=fp,
        summary="",
        steps=steps,
        input_schema=_infer_input_schema(steps),
        source_samples=[user_text[:200]],
        chain_stats={chain_key: 1},
        owner_slug=owner_slug,
    )
    item.summary = _build_summary(item, user_text)
    _path_for(skilllets_dir, item.slug).write_text(item.to_markdown(), encoding="utf-8")
    return item


def _infer_input_schema(steps: list[dict]) -> dict:
    properties: dict[str, dict] = {}
    required: list[str] = []
    for index, step in enumerate(steps, 1):
        tool_name = step.get("tool", f"step_{index}")
        for arg_key in step.get("args_keys", []):
            field_name = f"{tool_name}.{arg_key}"
            properties[field_name] = {
                "type": "string",
                "description": f"Fresh value for `{arg_key}` when calling `{tool_name}`.",
            }
            required.append(field_name)
    return {
        "type": "object",
        "properties": properties,
        "required": required[:20],
        "note": "Generated from observed tool argument keys. Refresh values per task.",
    }


def _match_score(item: Skilllet, query_tokens: set[str]) -> float:
    item_tokens = set(item.fingerprint.split())
    if not item_tokens:
        return 0.0
    overlap = len(query_tokens & item_tokens) / max(len(query_tokens | item_tokens), 1)
    reliability = item.success_count / max(item.success_count + item.failure_count, 1)
    usage_bonus = min(item.hit_count / 10.0, 0.4)
    recency_bonus = 1.0 / (1.0 + max(time.time() - item.updated_at, 0.0) / 86400.0 / 21.0)
    return overlap + (0.18 * reliability) + (0.08 * usage_bonus) + (0.06 * recency_bonus)


def _owner_bonus(item: Skilllet, owner_slug: str, personas_dir: Path | None) -> float:
    if not owner_slug:
        return 0.0 if not item.owner_slug else -0.12
    if item.owner_slug == owner_slug:
        return 0.22
    if not item.owner_slug:
        return 0.03
    if not personas_dir:
        return -0.08
    owner = per.load(personas_dir, owner_slug)
    if not owner:
        return -0.08
    chain = _inherited_owner_slugs(personas_dir, owner)
    if item.owner_slug in chain:
        distance = chain.index(item.owner_slug) + 1
        return max(0.16 - (distance * 0.03), 0.04)
    return -0.08


def _eligible_items(skilllets_dir: Path, owner_slug: str, personas_dir: Path | None) -> list[Skilllet]:
    items = list_all(skilllets_dir)
    if not owner_slug:
        return [item for item in items if not item.owner_slug]
    allowed = {owner_slug, ""}
    if personas_dir:
        owner = per.load(personas_dir, owner_slug)
        if owner:
            allowed.update(_inherited_owner_slugs(personas_dir, owner))
    return [item for item in items if item.owner_slug in allowed]


def _inherited_owner_slugs(personas_dir: Path, owner: per.Persona) -> list[str]:
    out: list[str] = []
    seen: set[str] = {owner.slug}

    def visit(parent_slug: str | None) -> None:
        if not parent_slug or parent_slug in seen:
            return
        parent = per.load(personas_dir, parent_slug)
        if not parent:
            return
        seen.add(parent.slug)
        out.append(parent.slug)
        visit(parent.parent_slug)
        visit(parent.other_parent_slug)

    visit(owner.parent_slug)
    visit(owner.other_parent_slug)
    return out


def _find_existing(skilllets_dir: Path, fingerprint: str, owner_slug: str = "") -> Skilllet | None:
    exact = None
    fp_tokens = set(fingerprint.split())
    best_similar: tuple[float, Skilllet] | None = None
    for item in list_all(skilllets_dir):
        if item.owner_slug != owner_slug:
            continue
        if item.fingerprint == fingerprint:
            exact = item
            break
        score = _match_score(item, fp_tokens)
        if score >= 0.60 and (best_similar is None or score > best_similar[0]):
            best_similar = (score, item)
    return exact or (best_similar[1] if best_similar else None)


def _merge_fingerprint(existing: str, new: str, limit: int = 16) -> str:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in (existing.split() + new.split()):
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
        if len(tokens) >= limit:
            break
    return " ".join(tokens)


def _merge_chain_stats(existing: dict[str, int], chain_key: str) -> dict[str, int]:
    merged = {str(key): int(value) for key, value in existing.items()}
    merged[chain_key] = merged.get(chain_key, 0) + 1
    return dict(sorted(merged.items(), key=lambda item: (-item[1], item[0]))[:8])


def _merge_input_schema(existing: dict, new: dict) -> dict:
    merged = {
        "type": "object",
        "properties": dict(existing.get("properties", {})),
        "required": list(existing.get("required", [])),
        "note": new.get("note") or existing.get("note") or "",
    }
    for key, value in new.get("properties", {}).items():
        merged["properties"][key] = value
    for key in new.get("required", []):
        if key not in merged["required"]:
            merged["required"].append(key)
    merged["required"] = merged["required"][:20]
    return merged


def _chain_key(steps: list[dict]) -> str:
    return " → ".join(step.get("tool", "?") for step in steps) or "(no tools)"


def _select_best_steps(item: Skilllet, new_steps: list[dict]) -> list[dict]:
    if not item.steps:
        return new_steps
    current_key = _chain_key(item.steps)
    new_key = _chain_key(new_steps)
    current_count = item.chain_stats.get(current_key, 0)
    new_count = item.chain_stats.get(new_key, 0)
    if new_count > current_count:
        return new_steps
    if new_count == current_count and len(new_steps) < len(item.steps):
        return new_steps
    return item.steps


def _build_summary(item: Skilllet, user_text: str) -> str:
    examples = max(len(item.source_samples), 1)
    return (
        f"A local workflow for tasks like: {user_text[:160]}. "
        f"Best-known path: {item.tool_chain}. "
        f"Learned from {examples} example(s) with {item.success_count} successful reuse(s)."
    )


def delete(skilllets_dir: Path, slug_or_name: str) -> bool:
    target_slug = _slugify(slug_or_name)
    candidates = [target_slug, slug_or_name]
    for item in list_all(skilllets_dir):
        if item.slug in candidates or item.name == slug_or_name:
            fp = _path_for(skilllets_dir, item.slug)
            if fp.exists():
                fp.unlink()
                return True
    return False


def render_index(skilllets_dir: Path) -> str:
    items = list_all(skilllets_dir)[:MAX_SKILLLETS_IN_PROMPT]
    if not items:
        return ""
    lines = ["\n# Local skilllets (self-grown workflows; use only when relevant)"]
    for item in items:
        lines.append(
            f"- `{item.slug}` v{item.version} "
            f"(hits={item.hit_count}, ok={item.success_count}, fail={item.failure_count}): "
            f"{item.fingerprint} :: {item.tool_chain}"
        )
    return "\n".join(lines) + "\n"


def render_family_index(skilllets_dir: Path, personas_dir: Path, owner_slug: str) -> str:
    items = _eligible_items(skilllets_dir, owner_slug=owner_slug, personas_dir=personas_dir)[:MAX_SKILLLETS_IN_PROMPT]
    if not items:
        return ""
    lines = ["\n# Family skill genes (own + inherited workflows)"]
    for item in items:
        owner = item.owner_slug or "shared"
        relation = "self" if item.owner_slug == owner_slug else ("shared" if not item.owner_slug else f"inherited from {owner}")
        lines.append(
            f"- `{item.slug}` [{relation}] "
            f"(hits={item.hit_count}, ok={item.success_count}, fail={item.failure_count}): "
            f"{item.fingerprint} :: {item.tool_chain}"
        )
    return "\n".join(lines) + "\n"


def render_hint(item: Skilllet) -> str:
    return (
        "\n# Skilllet match\n"
        f"Name: {item.name}\n"
        f"Intent fingerprint: {item.fingerprint}\n"
        f"Known-good tool path: {item.tool_chain}\n"
        "Reuse the workflow shape if it fits, but refresh all arguments for the current task.\n"
    )
