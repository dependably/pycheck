#!/bin/sh
# Point git's hooks path at the tracked .githooks/ directory so every developer
# gets the same pre-commit checks. Re-run after cloning.
set -e
git config core.hooksPath .githooks
echo "Git hooks installed (core.hooksPath -> .githooks)."
