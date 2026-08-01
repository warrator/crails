#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# push_to_github.sh
# Run this once from the root of your local clone of the repo.
# Replace REPO_URL with your actual GitHub repo URL.
# ─────────────────────────────────────────────────────────────

set -euo pipefail

REPO_URL="https://github.com/warrator/<YOUR-REPO-NAME>.git"   # ← update this
BRANCH="main"

echo "→ Initialising git (if not already a repo)..."
git init
git remote remove origin 2>/dev/null || true
git remote add origin "$REPO_URL"

echo "→ Staging all files..."
git add .

echo "→ Committing..."
git commit -m "docs: Add CRAILS platform documentation suite (HLD, LLD, SLO/SLI, Runbook, Chaos, Dashboard)"

echo "→ Pushing to $BRANCH..."
git push -u origin "$BRANCH"

echo "✅ Done — check https://github.com/warrator/<YOUR-REPO-NAME>"
