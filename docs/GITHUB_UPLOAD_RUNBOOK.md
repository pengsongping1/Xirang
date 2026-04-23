# GitHub Upload Runbook

This repo is currently **not** a Git repository yet. Before I can push it to
GitHub, I need a few exact pieces of information from you.

## I Need From You

- GitHub username or organization name
- target repository name
- whether the repo should be `public` or `private`
- whether to create a **new** repo or push to an **existing** repo
- preferred default branch name, usually `main`
- whether you want me to use:
  - an already logged-in `gh` CLI session, or
  - a GitHub Personal Access Token

## Safest Auth Options

### Option A: `gh` CLI already logged in

If your machine already has GitHub CLI authenticated, I can use:

```bash
gh auth status
```

### Option B: Personal Access Token

If you want me to create the repo and push with a token, prepare a token with:

- `repo`

If the repository belongs to an org with stricter settings, more scopes may be
needed, but `repo` is the normal baseline.

## What I Can Do Next

Once you give me the repo info and auth path, I can do the full sequence:

```bash
git init
git checkout -b main
git add .
git commit -m "release: Xirang 0.2.0a1 public alpha"
git remote add origin <repo-url>
git push -u origin main
git tag v0.2.0a1
git push origin v0.2.0a1
```

And if `gh` is available and authenticated, I can also create the release with:

```bash
gh release create v0.2.0a1 dist/xirang-0.2.0a1.tar.gz dist/xirang-0.2.0a1-py3-none-any.whl --title "Xirang 0.2.0a1 — local-first self-evolving agent public alpha" --notes-file docs/GITHUB_RELEASE_BODY_0.2.0a1.md
```

## Local Release Assets Already Ready

These files already exist locally:

- `dist/xirang-0.2.0a1.tar.gz`
- `dist/xirang-0.2.0a1-py3-none-any.whl`
- `docs/GITHUB_RELEASE_BODY_0.2.0a1.md`
- `docs/PUBLISHING.md`

## Recommended Repo Description

Local-first self-evolving agent with memory, persona families, inherited skill genes, and explicit desktop co-pilot.

## Recommended Topics

- `agent`
- `ai-agent`
- `cli`
- `local-first`
- `memory`
- `automation`
- `desktop-automation`
- `persona`
- `python`

