#!/usr/bin/env bash
set -euo pipefail
mkdir -p backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker run --rm -v factory_data:/source -v "$PWD/backups:/backup" alpine:3.22 sh -c "tar -czf /backup/factory-data-$STAMP.tar.gz -C /source ."
echo "Created backups/factory-data-$STAMP.tar.gz"
