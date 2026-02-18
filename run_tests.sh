#!/bin/bash
# Simple test runner
export PYTHONPATH=$PYTHONPATH:.
export ENV_MODE=test

echo "🚀 Running smoke tests..."
pytest tests/test_smoke.py -v

if [ $? -eq 0 ]; then
    echo "✅ Tests passed!"
else
    echo "❌ Tests failed!"
    exit 1
fi
