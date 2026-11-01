#!/bin/sh
set -eu
pip install --quiet --no-cache-dir -r requirements-test.txt
python -m pytest -q
