#!/usr/bin/env bash
set -euo pipefail

TAG="${TAG:-v0.2.0a1}"
BRANCH="${BRANCH:-main}"
TITLE="${TITLE:-Xirang 0.2.0a1 — local-first self-evolving agent public alpha}"
REMOTE_URL="${REMOTE_URL:-}"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

if [ ! -d .git ]; then
  git init
fi

current_branch="$(git branch --show-current 2>/dev/null || true)"
if [ -z "$current_branch" ]; then
  git checkout -b "$BRANCH"
fi

git add .

if ! git diff --cached --quiet; then
  git commit -m "release: Xirang 0.2.0a1 public alpha"
fi

if [ -n "$REMOTE_URL" ]; then
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$REMOTE_URL"
  else
    git remote add origin "$REMOTE_URL"
  fi
  git push -u origin "$BRANCH"
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "tag $TAG already exists"
else
  git tag "$TAG"
fi

if [ -n "$REMOTE_URL" ]; then
  git push origin "$TAG"
fi

if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    gh release create "$TAG" \
      dist/xirang-0.2.0a1.tar.gz \
      dist/xirang-0.2.0a1-py3-none-any.whl \
      --title "$TITLE" \
      --notes-file docs/GITHUB_RELEASE_BODY_0.2.0a1.md || true
  fi
fi

echo "Done. Review repo, tag, and release on GitHub."
