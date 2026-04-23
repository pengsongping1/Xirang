# Security Policy

Xirang is local-first. Memories, personas, sessions, and skill genes stay under
`~/.xirang/` unless the user manually exports and shares them.

## Desktop Co-pilot Boundary

- Desktop control is off by default.
- Use `XIRANG_DESKTOP_ENABLE=1` or `/copilot start` to opt in for the current run.
- Xirang does not install keyloggers, global hooks, or hidden background monitors.
- `/copilot observe` and `desktop.watch` are bounded screenshot sessions.

## Genome Contributions

Genome proposals are treated as untrusted input.

- Do not submit private memory, full sessions, secrets, or complete persona files.
- Use `/genome propose` to create a sanitized proposal.
- Review with `/genome review <path>` before opening a PR.
- Maintainers should merge with `scripts/merge_genome_proposals.py`, then inspect
  high-risk genes manually before release.

## Reporting

If you find a vulnerability, open a private report if GitHub security advisories
are enabled for the repository. Otherwise, open an issue with a minimal
reproduction and avoid posting secrets or exploit payloads.
