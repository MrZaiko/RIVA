#!/bin/bash

export PYTHONIOENCODING="utf-8"
export KUBECONFIG="$1"
export MODEL="$2"

echo "Script started with arguments:"
echo "KUBECONFIG: $KUBECONFIG"
echo "MODEL: $MODEL"

RANDOM_ID=$((RANDOM))
kind delete clusters --all --kubeconfig $KUBECONFIG
kind create cluster --config kind/kind-config-x86.yaml --kubeconfig $KUBECONFIG --name isolated-$RANDOM_ID

INVALID_ACTIONS="${@:3}"

if [ -z "$INVALID_ACTIONS" ]; then
    echo "Running RIVA client..."
    "KUBECONFIG=$KUBECONFIG MODEL=$MODEL ./.venv/bin/python3 clients/riva.py"
    "KUBECONFIG=$KUBECONFIG MODEL=$MODEL ./.venv/bin/python3 clients/react.py"
else
    echo "Running RIVA client with invalid actions: $INVALID_ACTIONS..."
    "KUBECONFIG=$KUBECONFIG MODEL=$MODEL ./.venv/bin/python3 clients/riva.py --invalid-actions $INVALID_ACTIONS"
    "KUBECONFIG=$KUBECONFIG MODEL=$MODEL ./.venv/bin/python3 clients/react.py --invalid-actions $INVALID_ACTIONS"
fi
