#!/bin/bash
set -ex

echo "=== Python tests ==="
pytest python/tests/unit/ -v
pytest --cov=python/lira python/tests/unit/ --cov-report=term
bash scripts/round_trip.sh "python python/tests/integration/copy_.py"
