"""Portable family and skill bundles.

Goals:
- Export a persona "child" together with the ancestors and inherited skill genes
- Import that bundle on another machine with no extra tooling
- Export local genome proposals as an opt-in artifact that users can inspect
  and commit/push manually, instead of auto-syncing over the network
"""
from __future__ import annotations

import json
import hashlib
import math
import re
import time
from pathlib import Path

from xirang import persona as per
from xirang import skilllet as skl
from xirang import tools as tl


BUNDLE_VERSION = 1
FAMILY_BUNDLE_TYPE = "xirang_family_bundle"
GENOME_PROPOSAL_BUNDLE_TYPE = "xirang_genome_proposal"
LEGACY_SKILL_CONTRIBUTION_BUNDLE_TYPE = "xirang_skill_contribution"
GENOME_PACK_BUNDLE_TYPE = "xirang_genome_pack"
SAFE_TEXT_RE = re.compile(r"[^0-9A-Za-z_\-\u4e00-\u9fff ]+")
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9._\-]{8,})")
UNIX_PATH_RE = re.compile(r"(?<!https:)(?<!http:)(~?/(?:[^ \n\t]+/?)+)")
WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\[^\s]+")
SAFE_ARG_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_BUNDLE_SKILLLETS = 512
MAX_SKILLLET_STEPS = 12
MAX_COUNTER_VALUE = 1_000_000
OPTIONAL_TOOL_NAMES = {"browser", "desktop"}
HIGH_RISK_TOOLS = {"bash", "write_file", "edit_file", "write_and_run", "desktop"}
MEDIUM_RISK_TOOLS = {"read_file", "browser"}


def _known_tool_names() -> set[str]:
    return {tool.name for tool in tl.all_tools()} | OPTIONAL_TOOL_NAMES


def _sanitize_free_text(text: str, limit: int = 180) -> str:
    text = SECRET_RE.sub("<secret>", text or "")
    text = UNIX_PATH_RE.sub("<path>", text)
    text = WINDOWS_PATH_RE.sub("<path>", text)
    text = " ".join(text.strip().split())
    return text[:limit]


def _safe_slug(text: str, fallback: str = "item", limit: int = 60) -> str:
    raw = str(text or "").strip().replace("\\", "/")
    if "/" in raw:
        parts = [part for part in raw.split("/") if part not in {"", ".", ".."}]
        raw = parts[-1] if parts else ""
    raw = SECRET_RE.sub("secret", raw)
    raw = " ".join(raw.split())
    slug = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "-", raw).strip("-").lower()
    slug = slug[:limit].strip("-")
    return slug or fallback


def _safe_owner_slug(text: str) -> str:
    return _safe_slug(text, fallback="", limit=60) if str(text or "").strip() else ""


def _safe_int(value, default: int = 0, minimum: int = 0, maximum: int = MAX_COUNTER_VALUE) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _safe_float(value, default: float | None = None) -> float:
    fallback = time.time() if default is None else default
    try:
        parsed = float(value)
    except Exception:
        return fallback
    return parsed if math.isfinite(parsed) else fallback


def _safe_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_list(value) -> list:
    return value if isinstance(value, list) else []


def _sanitize_text_list(value, *, count: int, limit: int) -> list[str]:
    out: list[str] = []
    for item in _safe_list(value):
        text = _sanitize_free_text(str(item), limit=limit)
        if text:
            out.append(text)
        if len(out) >= count:
            break
    return out


def _normalize_fingerprint(text: str, limit: int = 16) -> str:
    clean = SAFE_TEXT_RE.sub(" ", _sanitize_free_text(text, limit=240)).lower()
    tokens: list[str] = []
    seen: set[str] = set()
    for token in clean.split():
        if token not in seen:
            seen.add(token)
            tokens.append(token)
        if len(tokens) >= limit:
            break
    return " ".join(tokens)


def _sanitize_arg_keys(arg_keys: list[str]) -> list[str]:
    out: list[str] = []
    for key in arg_keys:
        key = str(key).strip()
        if SAFE_ARG_KEY_RE.match(key):
            out.append(key)
    return out[:16]


def _sanitize_steps(steps: list[dict]) -> list[dict]:
    known = _known_tool_names()
    out: list[dict] = []
    for raw in _safe_list(steps)[:MAX_SKILLLET_STEPS]:
        if not isinstance(raw, dict):
            continue
        tool_name = str(raw.get("tool", "")).strip()
        if tool_name not in known:
            continue
        raw_arg_keys = raw.get("args_keys", [])
        out.append(
            {
                "tool": tool_name,
                "args_keys": _sanitize_arg_keys(raw_arg_keys if isinstance(raw_arg_keys, list) else []),
            }
        )
    return out


def _input_schema_from_steps(steps: list[dict]) -> dict:
    properties: dict[str, dict] = {}
    required: list[str] = []
    for step in steps:
        tool_name = step["tool"]
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
        "note": "Sanitized from submitted workflow; refresh all values locally.",
    }


def _chain_key_from_steps(steps: list[dict]) -> str:
    return " → ".join(step["tool"] for step in steps) or "(no tools)"


def _community_slug(item: skl.Skilllet, used: set[str]) -> str:
    digest = hashlib.sha256(f"{item.fingerprint}|{item.tool_chain}".encode("utf-8")).hexdigest()[:10]
    base = _safe_slug(item.slug or item.fingerprint or item.name, fallback="community-skilllet", limit=44)
    candidate = _safe_slug(f"{base}-{digest}", fallback=f"community-skilllet-{digest}", limit=60)
    counter = 2
    while candidate in used:
        suffix = f"-{counter}"
        candidate = f"{_safe_slug(base, fallback='community-skilllet', limit=60 - len(digest) - len(suffix) - 1)}-{digest}{suffix}"
        counter += 1
    used.add(candidate)
    return candidate


def _sanitize_skilllet(item: skl.Skilllet, *, drop_samples: bool) -> skl.Skilllet | None:
    steps = _sanitize_steps(item.steps)
    fingerprint = _normalize_fingerprint(item.fingerprint)
    if not steps or not fingerprint:
        return None
    tool_chain = _chain_key_from_steps(steps)
    chain_stats = _safe_dict(item.chain_stats)
    chain_count = _safe_int(chain_stats.get(tool_chain, item.success_count), default=_safe_int(item.success_count, 1))
    success_count = _safe_int(item.success_count, default=1)
    failure_count = _safe_int(item.failure_count)
    hit_count = _safe_int(item.hit_count)
    sanitized = skl.Skilllet(
        name=_sanitize_free_text(item.name, limit=80) or "Skilllet",
        slug=_safe_slug(item.slug or item.name or fingerprint, fallback="skilllet"),
        fingerprint=fingerprint,
        summary="",
        version=_safe_int(item.version, default=1, minimum=1, maximum=99),
        steps=steps,
        input_schema=_input_schema_from_steps(steps),
        source_samples=[] if drop_samples else _sanitize_text_list(item.source_samples, count=2, limit=120),
        hit_count=hit_count,
        success_count=success_count,
        failure_count=failure_count,
        chain_stats={tool_chain: chain_count},
        owner_slug=_safe_owner_slug(item.owner_slug),
        inherited_from="",
        created_at=_safe_float(item.created_at),
        updated_at=_safe_float(item.updated_at),
    )
    sanitized.summary = (
        f"Portable workflow gene. Best-known path: {sanitized.tool_chain}. "
        f"Reliability: ok={sanitized.success_count}, fail={sanitized.failure_count}."
    )
    return sanitized


def _exports_dir(home: Path) -> Path:
    fp = home / "exports"
    fp.mkdir(parents=True, exist_ok=True)
    return fp


def _persona_payload(persona: per.Persona) -> dict:
    return {
        "name": _sanitize_free_text(persona.name, limit=80) or "Unknown",
        "slug": _safe_slug(persona.slug or persona.name, fallback="persona", limit=50),
        "essence": _sanitize_free_text(persona.essence, limit=240),
        "mental_models": _sanitize_text_list(persona.mental_models, count=6, limit=220),
        "decision_heuristics": _sanitize_text_list(persona.decision_heuristics, count=6, limit=220),
        "voice_dna": _sanitize_text_list(persona.voice_dna, count=6, limit=180),
        "limits": _sanitize_text_list(persona.limits, count=5, limit=180),
        "sample_openers": _sanitize_text_list(persona.sample_openers, count=5, limit=180),
        "source_sentence": _sanitize_free_text(persona.source_sentence, limit=180),
        "style_modes": {
            _safe_slug(key, fallback="mode", limit=40).replace("-", "_"): _sanitize_free_text(value, limit=220)
            for key, value in dict(persona.style_modes).items()
            if _sanitize_free_text(value, limit=220)
        },
        "parent_slug": _safe_owner_slug(persona.parent_slug or "") or None,
        "other_parent_slug": _safe_owner_slug(persona.other_parent_slug or "") or None,
        "family_name": _sanitize_free_text(persona.family_name or "", limit=80) or None,
        "refinement_notes": _sanitize_text_list(persona.refinement_notes[-10:], count=10, limit=180),
        "updated_at": _safe_float(persona.updated_at),
    }


def _persona_from_payload(payload: dict) -> per.Persona:
    payload = _safe_dict(payload)
    style_modes = _safe_dict(payload.get("style_modes", {}))
    return per.Persona(
        name=_sanitize_free_text(str(payload.get("name", "")), limit=80) or "Unknown",
        slug=_safe_slug(payload.get("slug", ""), fallback="persona", limit=50),
        essence=_sanitize_free_text(str(payload.get("essence", "")), limit=240),
        mental_models=_sanitize_text_list(payload.get("mental_models", []), count=6, limit=220),
        decision_heuristics=_sanitize_text_list(payload.get("decision_heuristics", []), count=6, limit=220),
        voice_dna=_sanitize_text_list(payload.get("voice_dna", []), count=6, limit=180),
        limits=_sanitize_text_list(payload.get("limits", []), count=5, limit=180),
        sample_openers=_sanitize_text_list(payload.get("sample_openers", []), count=5, limit=180),
        source_sentence=_sanitize_free_text(str(payload.get("source_sentence", "")), limit=180),
        style_modes={
            _safe_slug(k, fallback="mode", limit=40).replace("-", "_"): _sanitize_free_text(str(v), limit=220)
            for k, v in style_modes.items()
            if _sanitize_free_text(str(v), limit=220)
        },
        parent_slug=_safe_owner_slug(payload.get("parent_slug") or "") or None,
        other_parent_slug=_safe_owner_slug(payload.get("other_parent_slug") or "") or None,
        family_name=_sanitize_free_text(str(payload.get("family_name") or ""), limit=80) or None,
        refinement_notes=_sanitize_text_list(payload.get("refinement_notes", []), count=10, limit=180),
        updated_at=_safe_float(payload.get("updated_at", time.time())),
    )


def _skilllet_payload(item: skl.Skilllet) -> dict:
    return {
        "name": item.name,
        "slug": item.slug,
        "fingerprint": item.fingerprint,
        "summary": item.summary,
        "version": item.version,
        "steps": list(item.steps),
        "input_schema": dict(item.input_schema),
        "source_samples": list(item.source_samples),
        "hit_count": item.hit_count,
        "success_count": item.success_count,
        "failure_count": item.failure_count,
        "chain_stats": dict(item.chain_stats),
        "owner_slug": item.owner_slug,
        "inherited_from": item.inherited_from,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "maturity": gene_maturity(item),
    }


def _skilllet_from_payload(payload: dict) -> skl.Skilllet:
    payload = _safe_dict(payload)
    return skl.Skilllet(
        name=str(payload.get("name", "")).strip() or "Skilllet",
        slug=str(payload.get("slug", "")).strip() or "skilllet",
        fingerprint=str(payload.get("fingerprint", "")).strip(),
        summary=str(payload.get("summary", "")).strip(),
        version=_safe_int(payload.get("version", 3), default=3, minimum=1, maximum=99),
        steps=_safe_list(payload.get("steps", [])),
        input_schema=_safe_dict(payload.get("input_schema", {})),
        source_samples=_safe_list(payload.get("source_samples", [])),
        hit_count=_safe_int(payload.get("hit_count", 0)),
        success_count=_safe_int(payload.get("success_count", 1), default=1),
        failure_count=_safe_int(payload.get("failure_count", 0)),
        chain_stats=_safe_dict(payload.get("chain_stats", {})),
        owner_slug=str(payload.get("owner_slug", "")).strip(),
        inherited_from=str(payload.get("inherited_from", "")).strip(),
        created_at=_safe_float(payload.get("created_at", time.time())),
        updated_at=_safe_float(payload.get("updated_at", time.time())),
    )


def _ancestor_closure(personas_dir: Path, persona: per.Persona) -> list[per.Persona]:
    out: list[per.Persona] = []
    seen: set[str] = set()

    def visit(slug: str | None) -> None:
        if not slug or slug in seen:
            return
        item = per.load(personas_dir, slug)
        if not item:
            return
        seen.add(item.slug)
        out.append(item)
        visit(item.parent_slug)
        visit(item.other_parent_slug)

    visit(persona.parent_slug)
    visit(persona.other_parent_slug)
    return out


def _accessible_owner_slugs(personas_dir: Path, persona: per.Persona) -> list[str]:
    ordered = [persona.slug]
    for ancestor in _ancestor_closure(personas_dir, persona):
        if ancestor.slug not in ordered:
            ordered.append(ancestor.slug)
    return ordered


def gene_maturity(item: skl.Skilllet) -> dict[str, float | str | int]:
    """Score whether a local skill gene is ready to be proposed upstream."""
    total = max(item.success_count + item.failure_count, 1)
    reliability = item.success_count / total
    success_signal = min(item.success_count / 5.0, 1.0)
    reuse_signal = min(item.hit_count / 5.0, 1.0)
    chain_signal = min(len(item.chain_stats) / 3.0, 1.0) if item.chain_stats else 0.0
    score = round((0.45 * success_signal) + (0.30 * reliability) + (0.20 * reuse_signal) + (0.05 * chain_signal), 3)
    if score >= 0.82 and item.success_count >= 5:
        level = "proven"
    elif score >= 0.62 and item.success_count >= 3:
        level = "stable"
    elif score >= 0.35:
        level = "sprout"
    else:
        level = "seed"
    tools = {str(step.get("tool", "")) for step in item.steps}
    if tools & HIGH_RISK_TOOLS:
        risk = "high"
    elif tools & MEDIUM_RISK_TOOLS:
        risk = "medium"
    else:
        risk = "low"
    return {
        "score": score,
        "level": level,
        "risk": risk,
        "success_count": item.success_count,
        "failure_count": item.failure_count,
        "hit_count": item.hit_count,
    }


def export_family_bundle(
    home: Path,
    personas_dir: Path,
    skilllets_dir: Path,
    slug_or_name: str,
    output_path: Path | None = None,
) -> Path:
    target = per.load(personas_dir, slug_or_name)
    if not target:
        raise ValueError(f"no persona named '{slug_or_name}'")
    ancestors = _ancestor_closure(personas_dir, target)
    owner_slugs = set(_accessible_owner_slugs(personas_dir, target))
    family_skilllets = []
    for item in skl.list_all(skilllets_dir):
        if item.owner_slug not in owner_slugs:
            continue
        sanitized = _sanitize_skilllet(item, drop_samples=False)
        if sanitized:
            family_skilllets.append(sanitized)
    bundle = {
        "bundle_type": FAMILY_BUNDLE_TYPE,
        "bundle_version": BUNDLE_VERSION,
        "exported_at": time.time(),
        "target_slug": target.slug,
        "family_name": target.family_name or target.name,
        "personas": [_persona_payload(item) for item in [*ancestors, target]],
        "skilllets": [_skilllet_payload(item) for item in family_skilllets],
    }
    output_path = output_path or (_exports_dir(home) / f"family-{_safe_slug(target.slug, fallback='persona')}.xirang.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def import_family_bundle(personas_dir: Path, skilllets_dir: Path, bundle_path: Path) -> dict[str, int | str]:
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    if data.get("bundle_type") != FAMILY_BUNDLE_TYPE:
        raise ValueError("not a xirang family bundle")

    persona_saved = 0
    persona_skipped = 0
    for payload in data.get("personas", []):
        item = _persona_from_payload(payload)
        existing = per.load(personas_dir, item.slug)
        if existing and existing.updated_at > item.updated_at:
            persona_skipped += 1
            continue
        per.save(personas_dir, item)
        persona_saved += 1

    skill_saved = 0
    skill_skipped = 0
    for payload in data.get("skilllets", [])[:MAX_BUNDLE_SKILLLETS]:
        raw_item = _skilllet_from_payload(payload)
        item = _sanitize_skilllet(raw_item, drop_samples=False)
        if not item:
            skill_skipped += 1
            continue
        fp = skilllets_dir / f"{item.slug}.md"
        existing = skl.load(fp) if fp.exists() else None
        if existing and existing.updated_at > item.updated_at:
            skill_skipped += 1
            continue
        skilllets_dir.mkdir(parents=True, exist_ok=True)
        fp.write_text(item.to_markdown(), encoding="utf-8")
        skill_saved += 1

    return {
        "target_slug": str(data.get("target_slug", "")),
        "personas_saved": persona_saved,
        "personas_skipped": persona_skipped,
        "skilllets_saved": skill_saved,
        "skilllets_skipped": skill_skipped,
    }


def export_genome_proposal(
    home: Path,
    skilllets_dir: Path,
    owner_slug: str = "",
    output_path: Path | None = None,
) -> Path:
    items = skl.list_all(skilllets_dir)
    if owner_slug:
        items = [item for item in items if item.owner_slug == owner_slug]
    else:
        items = [item for item in items if item.owner_slug]
    items = [sanitized for item in items if (sanitized := _sanitize_skilllet(item, drop_samples=True))]
    bundle = {
        "bundle_type": GENOME_PROPOSAL_BUNDLE_TYPE,
        "bundle_version": BUNDLE_VERSION,
        "exported_at": time.time(),
        "owner_slug": _safe_owner_slug(owner_slug),
        "skilllet_count": len(items),
        "skilllets": [_skilllet_payload(item) for item in items],
        "proposal_kind": "skill_gene",
        "proposal_policy": {
            "local_only_by_default": True,
            "contains_full_persona": False,
            "contains_source_samples": False,
            "requires_manual_review": True,
        },
        "note": (
            "Inspect locally, then commit or open a PR manually. "
            "Xirang does not auto-push local evolution to the network; "
            "users contribute sanitized genome proposals, not full children."
        ),
    }
    suffix = _safe_owner_slug(owner_slug) or "all"
    output_path = output_path or (_exports_dir(home) / f"genome-proposal-{suffix}.xirang.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def export_skill_contribution_bundle(
    home: Path,
    skilllets_dir: Path,
    owner_slug: str = "",
    output_path: Path | None = None,
) -> Path:
    return export_genome_proposal(home, skilllets_dir, owner_slug=owner_slug, output_path=output_path)


def review_genome_proposal(bundle_path: Path) -> dict:
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    if data.get("bundle_type") not in {GENOME_PROPOSAL_BUNDLE_TYPE, LEGACY_SKILL_CONTRIBUTION_BUNDLE_TYPE}:
        raise ValueError("not a xirang genome proposal bundle")
    accepted: list[dict] = []
    rejected: list[dict] = []
    for payload in data.get("skilllets", [])[:MAX_BUNDLE_SKILLLETS]:
        raw_item = _skilllet_from_payload(payload)
        item = _sanitize_skilllet(raw_item, drop_samples=True)
        if not item:
            rejected.append({"slug": raw_item.slug, "reason": "invalid_or_unsafe_skilllet"})
            continue
        accepted.append(_skilllet_payload(item))
    mature = [
        payload for payload in accepted
        if payload.get("maturity", {}).get("level") in {"stable", "proven"}
    ]
    high_risk = [
        payload for payload in accepted
        if payload.get("maturity", {}).get("risk") == "high"
    ]
    return {
        "bundle_path": str(bundle_path),
        "bundle_type": str(data.get("bundle_type", "")),
        "owner_slug": str(data.get("owner_slug", "")),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "mature_count": len(mature),
        "high_risk_count": len(high_risk),
        "review_note": (
            "Prefer stable/proven genes. High-risk genes are allowed only after manual sandbox review."
        ),
        "accepted_skilllets": accepted,
        "rejected_skilllets": rejected,
    }


def review_contribution_bundle(bundle_path: Path) -> dict:
    return review_genome_proposal(bundle_path)


def merge_genome_proposals(bundle_paths: list[Path], output_dir: Path) -> dict[str, int | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    merged: dict[tuple[str, str], skl.Skilllet] = {}
    accepted_total = 0
    rejected_total = 0
    reports: list[dict] = []

    for bundle_path in bundle_paths:
        report = review_genome_proposal(bundle_path)
        reports.append(report)
        accepted_total += int(report["accepted_count"])
        rejected_total += int(report["rejected_count"])
        for payload in report["accepted_skilllets"]:
            item = _skilllet_from_payload(payload)
            key = (item.fingerprint, item.tool_chain)
            existing = merged.get(key)
            if not existing:
                item.owner_slug = ""
                item.inherited_from = "community"
                merged[key] = item
                continue
            existing.hit_count += item.hit_count
            existing.success_count += item.success_count
            existing.failure_count += item.failure_count
            existing.updated_at = max(existing.updated_at, item.updated_at)
            existing.created_at = min(existing.created_at, item.created_at)

    skilllets_dir = output_dir / "community_genome"
    skilllets_dir.mkdir(parents=True, exist_ok=True)
    used_slugs: set[str] = set()
    for item in merged.values():
        item.slug = _community_slug(item, used_slugs)
        (skilllets_dir / f"{item.slug}.md").write_text(item.to_markdown(), encoding="utf-8")

    report_path = output_dir / "genome_pack.json"
    report_path.write_text(
        json.dumps(
            {
                "bundle_type": GENOME_PACK_BUNDLE_TYPE,
                "bundle_version": BUNDLE_VERSION,
                "genome_stage": "community_pack",
                "merged_skilllets": len(merged),
                "accepted_total": accepted_total,
                "rejected_total": rejected_total,
                "skilllets_dir": str(skilllets_dir),
                "policy": {
                    "source": "sanitized_user_genome_proposals",
                    "network_sync": "never_automatic",
                    "review": "manual_before_commit",
                },
                "reports": reports,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "merged_skilllets": len(merged),
        "accepted_total": accepted_total,
        "rejected_total": rejected_total,
        "report_path": str(report_path),
    }


def merge_contribution_bundles(bundle_paths: list[Path], output_dir: Path) -> dict[str, int | str]:
    return merge_genome_proposals(bundle_paths, output_dir)
