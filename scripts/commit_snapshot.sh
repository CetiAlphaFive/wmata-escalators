#!/usr/bin/env bash
# Commit the snapshot scrape.sh just appended and push it. Called by
# scripts/scrape_loop.sh after every scrape, from the repo root.
#
# Commits data only; docs/index.html is a pure function of the CSV and is
# regenerated AFTER syncing with the remote, so the generated HTML is never
# 3-way-merged. The append-only CSV rebases cleanly.
set -euo pipefail

if [[ -z "$(git status --porcelain data/ docs/)" ]]; then
  echo "No changes to commit."
  exit 0
fi
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add data/
git commit -m "data: hourly snapshot $(date -u +%Y-%m-%dT%H:%MZ)"
git checkout -- docs/ 2>/dev/null || true
for attempt in 1 2 3; do
  if ! git pull --rebase origin "$GITHUB_REF_NAME"; then
    git rebase --abort || true
    sleep 5
    continue
  fi
  python3 render.py
  git add docs/
  git commit --amend --no-edit
  if git push; then
    echo "pushed (attempt $attempt)"
    exit 0
  fi
  echo "push rejected, remote advanced; retrying (attempt $attempt)"
  sleep 5
done
echo "push failed after retries"
exit 1
