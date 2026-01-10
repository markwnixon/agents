#!/usr/bin/env bash

pkill -9 geckodriver
pkill -9 firefox
echo "Killed geckodriver and firefox zombie processes"

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

