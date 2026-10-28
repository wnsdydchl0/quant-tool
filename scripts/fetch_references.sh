#!/usr/bin/env bash
# 레퍼런스 원본 저장소를 references/에 얕게 클론한다 (gitignore 대상).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p references
[ -d references/QuantLib-SWIG ] || git clone --depth 1 https://github.com/lballabio/QuantLib-SWIG.git references/QuantLib-SWIG
[ -d references/Engine ] || git clone --depth 1 https://github.com/OpenSourceRisk/Engine.git references/Engine
[ -d references/ORE-SWIG ] || git clone --depth 1 https://github.com/OpenSourceRisk/ORE-SWIG.git references/ORE-SWIG
