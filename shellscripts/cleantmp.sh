#!/usr/bin/env bash
set -euo pipefail

shopt -s nullglob
files=(/tmp/rust_mozprofile*)

if (( ${#files[@]} )); then
    echo "Removing:"
    printf '  %s\n' "${files[@]}"
    rm -rf "${files[@]}"
else
    echo "No rust_mozprofile temp files found"
fi

