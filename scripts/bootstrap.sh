#!/usr/bin/env bash
set -e
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp -n .env.example .env || true
