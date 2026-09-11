#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: bash scripts/publish_week.sh SEASON WEEK"
    echo "Example: bash scripts/publish_week.sh 2026 2"
    echo "Uses the active Python environment, or venv/.venv when available."
    echo "Override the interpreter with PYTHON=/path/to/python.exe."
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    usage
    exit 0
fi
if [[ $# != 2 || ! $1 =~ ^[0-9]{4}$ || ! $2 =~ ^([1-9]|1[0-8])$ ]]; then
    usage >&2
    exit 1
fi
season=$1
week=$2
cd "$(dirname "${BASH_SOURCE[0]}")/.."

trap 'echo "Publish stopped. Review local changes before retrying; completed database updates are not rolled back." >&2' ERR

branch=$(git symbolic-ref --quiet --short HEAD) || {
    echo "Check out a branch before publishing." >&2
    exit 1
}
git remote get-url origin >/dev/null
if ! git diff --cached --quiet; then
    echo "Commit or unstage existing staged changes before publishing." >&2
    exit 1
fi
if [[ -n $(git status --porcelain -- docs scripts/utils/constants.py) ]]; then
    echo "Commit or stash changes in docs/ and scripts/utils/constants.py first." >&2
    exit 1
fi

if [[ -n ${PYTHON:-} ]]; then
    python_cmd=$PYTHON
elif [[ -n ${VIRTUAL_ENV:-} ]]; then
    python_cmd=python
else
    python_cmd=python
    for candidate in .venv/Scripts/python.exe venv/Scripts/python.exe .venv/bin/python venv/bin/python; do
        if [[ -f $candidate ]]; then
            python_cmd=$candidate
            break
        fi
    done
fi
command -v "$python_cmd" >/dev/null || {
    echo "Python not found. Activate your project environment or set PYTHON." >&2
    exit 1
}

echo "Publishing season $season, week $week to origin/$branch"
# Persist the same settings for the updater and the separate export process.
grep -q '^SEASON = ' scripts/utils/constants.py
grep -q '^CURRENT_WEEK = ' scripts/utils/constants.py
sed -i -e "s/^SEASON = .*/SEASON = $season/" \
       -e "s/^CURRENT_WEEK = .*/CURRENT_WEEK = $week/" scripts/utils/constants.py

"$python_cmd" run_updates.py --season "$season" --week "$week"
"$python_cmd" -m scripts.export_static

git add -- docs scripts/utils/constants.py
if git diff --cached --quiet; then
    echo "No new export changes to commit."
else
    git commit -m "Publish season $season week $week"
fi
# Also retries a previously rejected push when the export has no new changes.
git push origin "$branch"
echo "Published season $season, week $week."
