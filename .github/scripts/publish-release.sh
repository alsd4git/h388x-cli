#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_REF_NAME:?GITHUB_REF_NAME is required}"

# GraphQL returns null for a missing release; authentication/API errors fail closed.
exists="$(gh api graphql \
  -F owner="${GITHUB_REPOSITORY%/*}" \
  -F name="${GITHUB_REPOSITORY#*/}" \
  -F tag="$GITHUB_REF_NAME" \
  -f query='query($owner: String!, $name: String!, $tag: String!) {
    repository(owner: $owner, name: $name) { release(tagName: $tag) { id } }
  }' \
  --jq '.data.repository.release != null')"

case "$exists" in
  true)
    echo "Release $GITHUB_REF_NAME already exists; preserving notes and assets."
    ;;
  false)
    gh release create "$GITHUB_REF_NAME" dist/* --verify-tag --generate-notes --title "$GITHUB_REF_NAME"
    ;;
  *)
    echo "Unexpected release lookup response; refusing to publish." >&2
    exit 1
    ;;
esac
