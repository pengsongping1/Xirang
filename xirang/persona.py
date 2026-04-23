"""Persona — one-sentence → full personality, Python port of nuwa-skill.

Compressed from nuwa-skill's 5-phase distillation process:
  1. Parse intent (person/style/theme from the user's sentence)
  2. Gather source material (web_search + web_fetch OR user-provided text)
  3. Extract: mental models, decision heuristics, voice DNA, limits
  4. Compose a persona.md with system prompt + few-shot examples
  5. Save to ~/.xirang/personas/<slug>.md

Differs from nuwa-skill: all runs inside Python, uses the configured LLM, no
sub-agents. Good enough for persona 0.8; full 1.0 needs the big 6-Agent swarm.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from xirang.llm import LLM


_DISTILL_SYSTEM = """You are a persona distiller. Given a user's one-sentence description of
a persona they want, produce a compact, runnable persona definition.

Capture HOW this entity thinks, not just WHAT they say:
- mental_models: 3-5 lenses they use to see the world (each 1 sentence)
- decision_heuristics: 3-5 if/then rules they apply under uncertainty
- voice_dna: 3-4 markers of their speaking/writing style
- limits: 2-3 honest boundaries ("cannot do X", "would never Y")
- style_modes: a JSON object with 3-5 output modes, e.g. {"default":"...", "teacher":"...", "reviewer":"...", "strategist":"..."}

Output STRICT JSON only, no prose:
{
  "name": "<short name>",
  "essence": "<one-sentence core identity>",
  "mental_models": ["...", "..."],
  "decision_heuristics": ["if X then Y", ...],
  "voice_dna": ["...", "..."],
  "limits": ["...", "..."],
  "style_modes": {"default": "...", "teacher": "..."},
  "sample_openers": ["<3 opening lines they might naturally say>", ...]
}
"""


_REFINE_SYSTEM = """You are refining an existing persona definition.

You will receive:
1. An existing persona JSON object
2. A refinement instruction from the user

Your job:
- preserve the persona's core identity unless the user explicitly asks to pivot
- improve clarity, coherence, and usefulness
- update mental models, heuristics, voice DNA, limits, and style modes when the instruction requires it
- you MAY rename the persona only if the instruction explicitly suggests a clearer identity
- keep style_modes practical and distinct

Return STRICT JSON only using the same schema as the original distiller:
{
  "name": "<short name>",
  "essence": "<one-sentence core identity>",
  "mental_models": ["...", "..."],
  "decision_heuristics": ["if X then Y", ...],
  "voice_dna": ["...", "..."],
  "limits": ["...", "..."],
  "style_modes": {"default": "...", "teacher": "..."},
  "sample_openers": ["...", "..."]
}
"""


_MODE_SYSTEM = """You are extending a persona with one new output mode.

You will receive:
1. An existing persona JSON object
2. A target mode name
3. A description of what this mode should feel like

Return STRICT JSON only:
{
  "mode_name": "<mode name>",
  "mode_description": "<one sentence describing the mode>",
  "sample_openers": ["...", "...", "..."]
}
"""


@dataclass
class Persona:
    name: str
    slug: str
    essence: str
    mental_models: list[str]
    decision_heuristics: list[str]
    voice_dna: list[str]
    limits: list[str]
    sample_openers: list[str]
    source_sentence: str
    style_modes: dict[str, str] = field(default_factory=dict)
    parent_slug: str | None = None
    other_parent_slug: str | None = None
    family_name: str | None = None
    refinement_notes: list[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def to_system_augmentation(self, mode: str | None = None) -> str:
        """Format the persona for injection into the main agent's system prompt."""
        style_modes = self.style_modes or {"default": "Use the natural baseline voice of this persona."}
        active_mode = mode or "default"
        active_mode_text = style_modes.get(active_mode) or style_modes.get("default", "")
        lines = [
            f"# Active persona: {self.name}",
            f"Essence: {self.essence}",
            "",
            "## Mental models (how you see the world)",
            *(f"- {m}" for m in self.mental_models),
            "",
            "## Decision heuristics",
            *(f"- {h}" for h in self.decision_heuristics),
            "",
            "## Voice DNA (how you speak)",
            *(f"- {v}" for v in self.voice_dna),
            "",
            "## Honest limits",
            *(f"- {l}" for l in self.limits),
            "",
            "## Output modes",
            *(f"- {k}: {v}" for k, v in style_modes.items()),
            "",
            f"## Active output mode",
            f"- {active_mode}: {active_mode_text}",
            "",
            "## Example openers for reference",
            *(f"- \"{o}\"" for o in self.sample_openers),
            "",
            "Apply the persona at the OUTPUT layer — your reasoning and tool-use "
            "decisions stay sharp and correct, but how you PHRASE responses "
            "should sound like this persona.",
        ]
        return "\n".join(lines)

    def to_markdown(self) -> str:
        return (
            f"---\nname: {self.name}\nslug: {self.slug}\n"
            f"source: {self.source_sentence}\n"
            f"parent_slug: {self.parent_slug or ''}\n"
            f"other_parent_slug: {self.other_parent_slug or ''}\n"
            f"family_name: {self.family_name or ''}\n"
            f"updated_at: {self.updated_at}\n"
            f"refinement_notes_json: {json.dumps(self.refinement_notes[-10:], ensure_ascii=False)}\n"
            f"---\n\n"
            + self.to_system_augmentation()
        )

    def to_payload(self) -> dict:
        return {
            "name": self.name,
            "slug": self.slug,
            "essence": self.essence,
            "mental_models": list(self.mental_models),
            "decision_heuristics": list(self.decision_heuristics),
            "voice_dna": list(self.voice_dna),
            "limits": list(self.limits),
            "sample_openers": list(self.sample_openers),
            "source_sentence": self.source_sentence,
            "style_modes": dict(self.style_modes),
            "parent_slug": self.parent_slug,
            "other_parent_slug": self.other_parent_slug,
            "family_name": self.family_name,
            "refinement_notes": list(self.refinement_notes),
        }


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff-]+", "-", name).strip("-").lower()
    return s[:50] or "persona"


def _extract_json(raw: str) -> dict:
    # Strip fenced code if present
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError(f"Distiller returned no JSON:\n{raw[:500]}")
    return json.loads(m.group(0))


def _coerce_list(value, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _coerce_modes(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"default": "Use the natural baseline voice of this persona."}
    out: dict[str, str] = {}
    for key, mode in value.items():
        mode_name = _slugify(str(key)).replace("-", "_")
        if not mode_name:
            continue
        text = str(mode).strip()
        if text:
            out[mode_name] = text
    if "default" not in out:
        out["default"] = "Use the natural baseline voice of this persona."
    return dict(list(out.items())[:8])


def _persona_from_data(
    data: dict,
    *,
    source_sentence: str,
    slug: str | None = None,
    parent_slug: str | None = None,
    other_parent_slug: str | None = None,
    refinement_notes: list[str] | None = None,
    family_name: str | None = None,
) -> Persona:
    name = data.get("name", "Unknown")
    return Persona(
        name=name,
        slug=slug or _slugify(name),
        essence=str(data.get("essence", "")).strip(),
        mental_models=_coerce_list(data.get("mental_models", []), 6),
        decision_heuristics=_coerce_list(data.get("decision_heuristics", []), 6),
        voice_dna=_coerce_list(data.get("voice_dna", []), 6),
        limits=_coerce_list(data.get("limits", []), 5),
        sample_openers=_coerce_list(data.get("sample_openers", []), 5),
        source_sentence=source_sentence,
        style_modes=_coerce_modes(data.get("style_modes", {})),
        parent_slug=parent_slug,
        other_parent_slug=other_parent_slug,
        family_name=family_name,
        refinement_notes=refinement_notes or [],
        updated_at=time.time(),
    )


def distill(llm: LLM, sentence: str) -> Persona:
    """Run the distiller LLM call and parse the JSON."""
    raw = llm.complete(prompt=sentence, system=_DISTILL_SYSTEM, max_tokens=2000)
    data = _extract_json(raw)
    return _persona_from_data(data, source_sentence=sentence)


def refine(llm: LLM, persona: Persona, instruction: str) -> Persona:
    payload = json.dumps(persona.to_payload(), ensure_ascii=False, indent=2)
    prompt = (
        "Existing persona JSON:\n"
        f"{payload}\n\n"
        "Refinement instruction:\n"
        f"{instruction}"
    )
    raw = llm.complete(prompt=prompt, system=_REFINE_SYSTEM, max_tokens=2200)
    data = _extract_json(raw)
    return _persona_from_data(
        data,
        source_sentence=persona.source_sentence,
        slug=persona.slug,
        parent_slug=persona.parent_slug,
        other_parent_slug=persona.other_parent_slug,
        family_name=persona.family_name,
        refinement_notes=[*persona.refinement_notes, instruction.strip()],
    )


def fork(llm: LLM, persona: Persona, instruction: str) -> Persona:
    payload = json.dumps(persona.to_payload(), ensure_ascii=False, indent=2)
    prompt = (
        "Base persona JSON:\n"
        f"{payload}\n\n"
        "Fork instruction:\n"
        f"{instruction}\n\n"
        "Create a new related persona that keeps the useful foundation but follows the new brief."
    )
    raw = llm.complete(prompt=prompt, system=_REFINE_SYSTEM, max_tokens=2200)
    data = _extract_json(raw)
    forked = _persona_from_data(
        data,
        source_sentence=instruction.strip() or persona.source_sentence,
        parent_slug=persona.slug,
        family_name=persona.family_name or persona.name,
        refinement_notes=[f"forked from {persona.slug}: {instruction.strip()}"],
    )
    if forked.slug == persona.slug:
        forked.slug = _slugify(f"{forked.name}-{persona.slug}")[:50]
    return forked


def add_mode(llm: LLM, persona: Persona, mode_name: str, instruction: str) -> Persona:
    mode_name = _slugify(mode_name).replace("-", "_")
    if not mode_name:
        raise ValueError("mode name cannot be empty")
    payload = json.dumps(persona.to_payload(), ensure_ascii=False, indent=2)
    prompt = (
        "Existing persona JSON:\n"
        f"{payload}\n\n"
        f"Target mode name: {mode_name}\n"
        f"Mode brief: {instruction}"
    )
    raw = llm.complete(prompt=prompt, system=_MODE_SYSTEM, max_tokens=1000)
    data = _extract_json(raw)
    description = str(data.get("mode_description", "")).strip() or instruction.strip()
    sample_openers = _coerce_list(data.get("sample_openers", []), 3)
    merged_modes = dict(persona.style_modes)
    merged_modes[mode_name] = description
    merged_openers = list(persona.sample_openers)
    for opener in sample_openers:
        if opener not in merged_openers:
            merged_openers.append(opener)
    return Persona(
        name=persona.name,
        slug=persona.slug,
        essence=persona.essence,
        mental_models=list(persona.mental_models),
        decision_heuristics=list(persona.decision_heuristics),
        voice_dna=list(persona.voice_dna),
        limits=list(persona.limits),
        sample_openers=merged_openers[:6],
        source_sentence=persona.source_sentence,
        style_modes=merged_modes,
        parent_slug=persona.parent_slug,
        other_parent_slug=persona.other_parent_slug,
        family_name=persona.family_name,
        refinement_notes=[*persona.refinement_notes, f"mode {mode_name}: {instruction.strip()}"],
        updated_at=time.time(),
    )


def save(personas_dir: Path, persona: Persona) -> Path:
    personas_dir.mkdir(parents=True, exist_ok=True)
    fp = personas_dir / f"{persona.slug}.md"
    fp.write_text(persona.to_markdown(), encoding="utf-8")
    return fp


def load(personas_dir: Path, slug_or_name: str) -> Persona | None:
    slug = _slugify(slug_or_name)
    fp = personas_dir / f"{slug}.md"
    if not fp.exists():
        # Try scanning by name
        for p in personas_dir.glob("*.md"):
            text = p.read_text(encoding="utf-8")
            if f"name: {slug_or_name}" in text or f"slug: {slug}" in text:
                fp = p
                break
        else:
            return None
    text = fp.read_text(encoding="utf-8")
    # Quick, lenient frontmatter parse
    fm_match = re.match(r"^---\n([\s\S]*?)\n---", text)
    meta: dict = {}
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    body = text[fm_match.end():].strip() if fm_match else text

    def _section(body: str, header: str) -> list[str]:
        rx = re.compile(rf"## {re.escape(header)}[\s\S]*?(?=\n##|\Z)")
        m = rx.search(body)
        if not m:
            return []
        return [
            line.lstrip("- ").strip().strip('"')
            for line in m.group(0).splitlines()[1:]
            if line.strip().startswith("-")
        ]

    def _kv_section(body: str, header: str) -> dict[str, str]:
        rx = re.compile(rf"## {re.escape(header)}[\s\S]*?(?=\n##|\Z)")
        m = rx.search(body)
        if not m:
            return {}
        out: dict[str, str] = {}
        for line in m.group(0).splitlines()[1:]:
            line = line.strip()
            if not line.startswith("-") or ":" not in line:
                continue
            key, value = line.lstrip("- ").split(":", 1)
            out[key.strip()] = value.strip()
        return out

    essence_match = re.search(r"Essence:\s*(.+)", body)
    refinement_notes_raw = meta.get("refinement_notes_json", "[]")
    try:
        refinement_notes = json.loads(refinement_notes_raw)
    except Exception:
        refinement_notes = []
    return Persona(
        name=meta.get("name", slug),
        slug=meta.get("slug", slug),
        essence=essence_match.group(1).strip() if essence_match else "",
        mental_models=_section(body, "Mental models (how you see the world)"),
        decision_heuristics=_section(body, "Decision heuristics"),
        voice_dna=_section(body, "Voice DNA (how you speak)"),
        limits=_section(body, "Honest limits"),
        style_modes=_kv_section(body, "Output modes"),
        sample_openers=_section(body, "Example openers for reference"),
        source_sentence=meta.get("source", ""),
        parent_slug=meta.get("parent_slug") or None,
        other_parent_slug=meta.get("other_parent_slug") or None,
        family_name=meta.get("family_name") or None,
        refinement_notes=refinement_notes if isinstance(refinement_notes, list) else [],
        updated_at=float(meta.get("updated_at", time.time())),
    )


def list_all(personas_dir: Path) -> list[str]:
    return sorted(p.stem for p in personas_dir.glob("*.md"))


def birth(llm: LLM, persona: Persona, instruction: str) -> Persona:
    child = fork(llm, persona, instruction)
    child.parent_slug = persona.slug
    child.family_name = persona.family_name or persona.name
    child.refinement_notes = [
        *child.refinement_notes,
        f"born into family {child.family_name}",
    ]
    return child


def mutate(llm: LLM, persona: Persona, instruction: str) -> Persona:
    child = birth(llm, persona, f"Genetic mutation brief: {instruction.strip()}")
    child.refinement_notes = [
        *child.refinement_notes,
        f"mutated from {persona.slug}: {instruction.strip()}",
    ]
    return child


def mate(llm: LLM, persona: Persona, partner: Persona, instruction: str) -> Persona:
    payload = json.dumps(
        {
            "parent_a": persona.to_payload(),
            "parent_b": partner.to_payload(),
            "child_brief": instruction.strip(),
        },
        ensure_ascii=False,
        indent=2,
    )
    prompt = (
        "Two persona parents are creating a child persona.\n"
        "Blend the practical strengths of both while keeping the child coherent and usable.\n\n"
        f"{payload}"
    )
    raw = llm.complete(prompt=prompt, system=_REFINE_SYSTEM, max_tokens=2200)
    data = _extract_json(raw)
    family_name = persona.family_name or partner.family_name or f"{persona.name}-{partner.name}"
    child = _persona_from_data(
        data,
        source_sentence=instruction.strip() or f"child of {persona.slug} and {partner.slug}",
        parent_slug=persona.slug,
        other_parent_slug=partner.slug,
        family_name=family_name,
        refinement_notes=[
            f"born from love: {persona.slug} + {partner.slug}",
            f"child brief: {instruction.strip()}",
        ],
    )
    if child.slug in {persona.slug, partner.slug}:
        child.slug = _slugify(f"{child.name}-{persona.slug}-{partner.slug}")[:50]
    return child


def ancestors(personas_dir: Path, persona: Persona) -> list[Persona]:
    out: list[Persona] = []
    seen: set[str] = set()
    current = persona
    while current.parent_slug and current.parent_slug not in seen:
        seen.add(current.parent_slug)
        parent = load(personas_dir, current.parent_slug)
        if not parent:
            break
        out.append(parent)
        current = parent
    return out


def lineage(personas_dir: Path, persona: Persona) -> list[Persona]:
    return [*reversed(ancestors(personas_dir, persona)), persona]


def root_of(personas_dir: Path, persona: Persona) -> Persona:
    chain = ancestors(personas_dir, persona)
    return chain[-1] if chain else persona


def children_of(personas_dir: Path, slug_or_name: str) -> list[Persona]:
    parent = load(personas_dir, slug_or_name)
    if not parent:
        return []
    out: list[Persona] = []
    for slug in list_all(personas_dir):
        item = load(personas_dir, slug)
        if item and (item.parent_slug == parent.slug or item.other_parent_slug == parent.slug):
            out.append(item)
    return sorted(out, key=lambda p: (p.updated_at, p.slug))


def family_tree(personas_dir: Path, slug_or_name: str) -> str:
    target = load(personas_dir, slug_or_name)
    if not target:
        return ""
    root = root_of(personas_dir, target)

    def _render(node: Persona, depth: int = 0) -> list[str]:
        prefix = "  " * depth
        co_parent = f" + `{node.other_parent_slug}`" if node.other_parent_slug else ""
        current = " ← current" if node.slug == target.slug else ""
        lines = [f"{prefix}- {node.name} (`{node.slug}`{co_parent}){current}"]
        for child in children_of(personas_dir, node.slug):
            lines.extend(_render(child, depth + 1))
        return lines

    family = root.family_name or root.name
    return "\n".join([f"**{family} family tree**", *_render(root)])
