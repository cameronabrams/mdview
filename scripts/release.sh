#!/usr/bin/env bash
# Release mdview at a given version.
#
# Usage: ./scripts/release.sh <version>
# Example: ./scripts/release.sh 0.2.0
#
# Prerequisites (checked automatically):
#   - Working tree must be clean (no uncommitted changes)
#   - Must be on the main branch
#   - The tag v<version> must not already exist (locally or on origin)
#
# What it does:
#   1. If CHANGELOG.md exists, rotates it: renames [Unreleased] to
#      [<version>] - <date> and inserts a fresh empty [Unreleased] above it.
#      (mdview has no CHANGELOG.md yet — the step is skipped until one exists.)
#   2. Updates the version in pyproject.toml
#   3. Commits the change(s) as "Release v<version>"
#   4. Creates tag v<version>
#   5. Pushes the commit and the tag to origin
#
# NOTE: mdview is installed straight from GitHub (the distribution is
# `mdview-web`, but it is not yet published to PyPI and there is no release CI
# workflow). So the pushed tag currently just marks the release on GitHub — it
# does NOT trigger a build/publish. When a PyPI publish workflow is added (see
# ROADMAP.md), wire it to `v*` tags and expand the preflight below, mirroring the
# sibling repos (pestifer/pidibble/ycleptic).

set -euo pipefail

VERSION="${1:?Usage: scripts/release.sh <version>  (e.g. 0.2.0)}"
TODAY="$(date +%Y-%m-%d)"

# ── Preconditions ─────────────────────────────────────────────────────────────

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "ERROR: working tree has uncommitted changes — commit or stash them first"
    exit 1
fi

BRANCH="$(git branch --show-current)"
if [ "$BRANCH" != "main" ]; then
    echo "ERROR: must be on main branch (currently on '$BRANCH')"
    exit 1
fi

if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "ERROR: tag v$VERSION already exists locally"
    exit 1
fi

if git ls-remote --tags origin "refs/tags/v$VERSION" | grep -q .; then
    echo "ERROR: tag v$VERSION already exists on origin"
    exit 1
fi

# ── CHANGELOG rotation (only if a CHANGELOG.md is present) ─────────────────────

CHANGED_FILES=(pyproject.toml)
if [ -f CHANGELOG.md ]; then
    if ! grep -q "^## \[Unreleased\]" CHANGELOG.md; then
        echo "ERROR: CHANGELOG.md has no '## [Unreleased]' section to rotate"
        exit 1
    fi
    echo "Rotating CHANGELOG.md: [Unreleased] -> [$VERSION] - $TODAY"
    sed -i "s/^## \[Unreleased\]/## [$VERSION] - $TODAY/" CHANGELOG.md
    # Insert a fresh [Unreleased] section above the new release
    sed -i "s/^## \[$VERSION\] - $TODAY/## [Unreleased]\n\n## [$VERSION] - $TODAY/" CHANGELOG.md
    CHANGED_FILES+=(CHANGELOG.md)
else
    echo "No CHANGELOG.md — skipping changelog rotation."
fi

# ── Version bump ──────────────────────────────────────────────────────────────

echo "Bumping pyproject.toml version to $VERSION"
sed -i "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml

ACTUAL="$(grep -m1 '^version = ' pyproject.toml | sed 's/version = \"\(.*\)\"/\1/')"
if [ "$ACTUAL" != "$VERSION" ]; then
    echo "ERROR: version in pyproject.toml is '$ACTUAL' after sed — check the file"
    git checkout "${CHANGED_FILES[@]}"
    exit 1
fi

# ── Commit, tag, push ─────────────────────────────────────────────────────────

git add "${CHANGED_FILES[@]}"
git commit -m "Release v$VERSION"
git tag "v$VERSION"

echo "Pushing commit and tag v$VERSION to origin..."
git push origin main
git push origin "v$VERSION"

echo ""
echo "Done. Tagged v$VERSION and pushed to origin."
echo "(No publish workflow is wired yet — see the note at the top of this script.)"
