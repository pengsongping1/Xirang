# Desktop Co-pilot Example

This example shows the intended human + agent collaboration model.

## Enable

```bash
pip install ".[desktop]"
XIRANG_DESKTOP_ENABLE=1 xirang --mode ask
```

`--mode ask` is recommended for the first run because desktop actions are
powerful. You can switch to `default` after you trust the workflow.

Inside the REPL you can also start a visible co-pilot session:

```text
/copilot start help me edit the current document
/copilot observe 3
/copilot invite join this writing task and wait for my next move
```

## Prompt

```text
Observe my screen for 3 seconds, tell me what window appears active, then wait.
```

Then:

```text
Move to the Save button and click it.
```

## Safety Model

- No background keylogger.
- No hidden always-on listener.
- `/copilot` is a visible opt-in session wrapper, not a background monitor.
- `watch` is explicit, bounded, and screenshot-based.
- All desktop actions are tool calls and go through the permission/audit system.
