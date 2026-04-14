#!/bin/bash
set -e

# Clone or update a git repo.
# Usage: clone_or_pull <repo_url> <dest> [depth] [branch]
#   branch: if set, checkout that branch; otherwise track remote default
clone_or_pull() {
    local repo_url="$1"
    local dest="$2"
    local depth="${3:-1}"
    local branch="${4:-}"

    [ -z "$repo_url" ] && return

    # Inject token into HTTPS URL for private repos
    if [ -n "$GITHUB_TOKEN" ]; then
        repo_url="${repo_url/https:\/\//https://${GITHUB_TOKEN}@}"
    fi

    if [ -d "$dest/.git" ]; then
        # Clean up any stale lock files from previous crashes
        find "$dest/.git" -name "*.lock" -delete 2>/dev/null || true

        if [ -n "$branch" ]; then
            echo "[entrypoint] Fetching branch '$branch' in $dest"
            git -C "$dest" fetch --depth="$depth" origin "$branch"
            git -C "$dest" checkout -B "$branch" FETCH_HEAD
        else
            echo "[entrypoint] Pulling $dest (default branch)"
            git -C "$dest" fetch --depth="$depth" origin
            git -C "$dest" reset --hard FETCH_HEAD
        fi
    else
        local branch_arg=""
        [ -n "$branch" ] && branch_arg="--branch $branch"
        echo "[entrypoint] Cloning $repo_url -> $dest (depth=$depth branch=${branch:-default})"
        git clone --depth="$depth" $branch_arg "$repo_url" "$dest"
    fi
}

clone_or_pull "$SKILLS_REPO"         "/skills"                 1   "${SKILLS_BRANCH:-}"
clone_or_pull "$VANCE_ANDROID_REPO"  "/codebase/vance-android" 500
clone_or_pull "$VANCE_IOS_REPO"      "/codebase/vance-ios"     500

exec agentura-server
