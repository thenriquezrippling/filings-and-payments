#!/usr/bin/env bash
# Run this once from the repo root to install GitHub Actions workflows.
# Then commit and push the .github/workflows/ directory.
set -e
mkdir -p .github/workflows
cp taxops/github-workflows/*.yml .github/workflows/
echo "Workflow files copied. Now run:"
echo "  git add .github/workflows/"
echo "  git commit -m 'ci: install TaxOps GitHub Actions workflows'"
echo "  git push"
