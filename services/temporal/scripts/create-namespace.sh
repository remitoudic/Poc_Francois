#!/bin/sh
# Register the FOX MLO namespace once the Temporal server is healthy. Safe to run on every start.
set -eu

ADDRESS="${TEMPORAL_ADDRESS:-temporal:7233}"
NAMESPACE="${TEMPORAL_NAMESPACE:-fox-mlo}"
RETENTION="${TEMPORAL_RETENTION:-720h}"

attempt=1
until temporal operator cluster health --address "$ADDRESS" >/dev/null 2>&1; do
  if [ "$attempt" -ge 60 ]; then echo "Temporal not healthy after $attempt attempts"; exit 1; fi
  attempt=$((attempt + 1)); sleep 3
done

if temporal operator namespace describe -n "$NAMESPACE" --address "$ADDRESS" >/dev/null 2>&1; then
  echo "Namespace $NAMESPACE already exists"
else
  temporal operator namespace create -n "$NAMESPACE" --retention "$RETENTION" --address "$ADDRESS"
  echo "Namespace $NAMESPACE created"
fi
