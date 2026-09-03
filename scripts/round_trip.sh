#!/bin/bash
set -e

[ $# -eq 1 ] || { echo "Usage: $0 <copy_script>"; exit 1; }

REF=tests/integration/reference.yaml

mkdir -p tmp
$1 $REF tmp/raw1.yaml
$1 tmp/raw1.yaml tmp/raw2.yaml
# Round‑trip without canonicalization
diff tmp/raw1.yaml tmp/raw2.yaml
python tools/yaml_canonicalize.py tmp/raw1.yaml tmp/out.yaml
# Round‑trip with canonicalization
diff tmp/out.yaml $REF
