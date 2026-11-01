#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose run --rm --no-deps --user 0 -v "$PWD/scripts:/scripts:ro" api sh /scripts/test-container.sh
