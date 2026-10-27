#!/usr/bin/env bash

set -euo pipefail

if ! command -v gh >/dev/null; then
    echo "Install GitHub CLI before using make push."
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "GitHub CLI is not authenticated. Run gh auth login first."
    exit 1
fi

branch=$(git symbolic-ref --quiet --short HEAD) || {
    echo "Switch to a branch before using make push."
    exit 1
}
commit=$(git rev-parse HEAD)
remote_url=$(git remote get-url --push origin)

case "$remote_url" in
    git@github.com:*) repository=${remote_url#git@github.com:} ;;
    https://github.com/*) repository=${remote_url#https://github.com/} ;;
    *)
        echo "The origin push URL must point to a GitHub repository."
        exit 1
        ;;
esac
repository=${repository%.git}

remote_ref=$(git ls-remote --heads "$remote_url" "refs/heads/$branch")
remote_commit=${remote_ref%%[[:space:]]*}
if [[ "$remote_commit" == "$commit" ]]; then
    echo "The branch is already up to date. No new CI run was started."
    exit 0
fi

query='[.[] | select(.workflowName == "CI")][0].databaseId // empty'
previous_run=$(gh run list --repo "$repository" --branch "$branch" --commit "$commit" --event push --json databaseId,workflowName --jq "$query")

git push origin "HEAD:refs/heads/$branch"

echo "Waiting for CI for $branch at $commit."
run_id=""
for ((attempt = 1; attempt <= 60; attempt++)); do
    run_id=$(gh run list --repo "$repository" --branch "$branch" --commit "$commit" --event push --json databaseId,workflowName --jq "$query") || {
        echo "The push succeeded, but GitHub Actions could not be queried."
        exit 1
    }
    if [[ -n "$run_id" && "$run_id" != "$previous_run" ]]; then
        break
    fi
    run_id=""
    sleep 5
done

if [[ -z "$run_id" ]]; then
    echo "The push succeeded, but no new CI run appeared within five minutes."
    echo "Check whether GitHub Actions is enabled and the CI workflow is present."
    exit 1
fi

if gh run watch "$run_id" --repo "$repository" --exit-status --compact; then
    echo "CI passed."
    exit 0
fi

echo "CI did not pass or its status could not be read. Inspect the run before retrying."
gh run view "$run_id" --repo "$repository" --log-failed || true
echo "Run: https://github.com/$repository/actions/runs/$run_id"
exit 1
