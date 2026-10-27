#!/usr/bin/env bash

set -euo pipefail

current_path=$(git config --get core.hooksPath || true)
if [[ -n "$current_path" && "$current_path" != ".githooks" ]]; then
    echo "A different hooks directory is already configured: $current_path"
    exit 1
fi

default_hook=$(git rev-parse --git-path hooks/pre-push)
if [[ -z "$current_path" && -e "$default_hook" ]]; then
    echo "An existing pre-push hook would be bypassed: $default_hook"
    exit 1
fi

git config --local core.hooksPath .githooks
echo "Installed the repository hooks."
