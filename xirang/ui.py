"""UI — Rich-based banner, streaming render, tool-call panels.

Design: pure Python, one dependency (rich), Claude-Code-inspired color palette
(earth/sunrise: ochre → pink → violet). No separate TUI framework.
"""
from __future__ import annotations

from rich.align import Align
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


console = Console()

# "息壤" palette — earth + sunrise
COLOR_PRIMARY = "#ff9966"   # warm orange
COLOR_ACCENT = "#ff5e62"    # sunrise pink
COLOR_DIM = "#7d7c7a"
COLOR_SUCCESS = "#8bc34a"
COLOR_USER = "#89c4f4"
COLOR_ASSIST = "#ffd166"
COLOR_PANEL = "#f4a261"

# Plain-text marker for streaming (Rich markup would interleave with raw text)
ASSIST_MARK = "\033[1;38;2;255;209;102m◆ \033[0m"


BANNER = (
    "██╗  ██╗██╗██████╗  █████╗ ███╗   ██╗ ██████╗\n"
    "╚██╗██╔╝██║██╔══██╗██╔══██╗████╗  ██║██╔════╝\n"
    " ╚███╔╝ ██║██████╔╝███████║██╔██╗ ██║██║  ███╗\n"
    " ██╔██╗ ██║██╔══██╗██╔══██║██║╚██╗██║██║   ██║\n"
    "██╔╝ ██╗██║██║  ██║██║  ██║██║ ╚████║╚██████╔╝\n"
    "╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ "
)


def _meta_rows(rows: list[tuple[str, str]]) -> Text:
    text = Text()
    width = max((len(label) for label, _ in rows), default=0) + 2
    for index, (label, value) in enumerate(rows):
        text.append(label.ljust(width), style=COLOR_DIM)
        text.append(value, style=f"bold {COLOR_ACCENT}")
        if index < len(rows) - 1:
            text.append("\n")
    return text


def show_banner(
    model: str,
    provider: str,
    persona: str | None = None,
    brand: str = "Xirang · 息壤",
    mode: str | None = None,
    session: str | None = None,
    profile: str | None = None,
    persona_mode: str | None = None,
) -> None:
    text = Text(BANNER, style=f"bold {COLOR_PRIMARY}")
    title = Text.assemble((brand, f"bold {COLOR_PRIMARY}"), ("  ·  do-anything local agent", COLOR_DIM))
    rows = [
        ("Provider", provider),
        ("Model", model),
    ]
    if mode:
        rows.append(("Mode", mode))
    if profile:
        rows.append(("Profile", profile))
    if session:
        rows.append(("Session", session))
    if persona:
        persona_value = persona if not persona_mode else f"{persona} · {persona_mode}"
        rows.append(("Persona", persona_value))
    body = Group(text, title, Text(""), _meta_rows(rows))
    console.print(Panel(body, border_style=COLOR_PANEL, padding=(0, 2)))
    console.print(
        Text(
            "commands: /help /persona /brain /llm /cron /webhook /bench /memory /session /exit",
            style=COLOR_DIM,
        )
    )
    console.print()


def user_label() -> None:
    console.print(Text("▸ ", style=COLOR_USER), end="")


def assistant_text(text: str) -> None:
    if not text.strip():
        return
    console.print(Text("◆ ", style=COLOR_ASSIST) + Text(text.rstrip()))


def tool_call_panel(name: str, args: dict) -> None:
    from rich.pretty import Pretty
    panel = Panel(
        Pretty(args, max_depth=3),
        title=Text.assemble(("🛠 ", ""), (name, f"bold {COLOR_ACCENT}")),
        border_style=COLOR_DIM,
        padding=(0, 1),
    )
    console.print(panel)


def tool_result_panel(name: str, output: str) -> None:
    # Truncate long output for display (the model still sees the full thing)
    display = output if len(output) < 2000 else output[:2000] + "\n... [output truncated for display]"
    panel = Panel(
        Text(display),
        title=Text.assemble(("↩ ", ""), (name, COLOR_DIM)),
        border_style=COLOR_DIM,
        padding=(0, 1),
    )
    console.print(panel)


def status(message: str) -> None:
    console.print(Text(f"• {message}", style=COLOR_DIM))


def info(message: str) -> None:
    console.print(Text(message, style=COLOR_PRIMARY))


def warn(message: str) -> None:
    console.print(Text(f"⚠ {message}", style=COLOR_ACCENT))


def error(message: str) -> None:
    console.print(Text(f"✗ {message}", style="bold red"))


def success(message: str) -> None:
    console.print(Text(f"✓ {message}", style=COLOR_SUCCESS))


def markdown(text: str) -> None:
    console.print(Markdown(text))


def code(text: str, lang: str = "python") -> None:
    console.print(Syntax(text, lang, theme="monokai", word_wrap=True))
