#!/usr/bin/env bash
# Build, install and test MoDeNa inside the ci/Dockerfile image.
#
#   ci/run-tests.sh [PRESET]      PRESET: a configure + test preset (dev, full)
#
# Expects MODENA_TEST_URI to name a reachable MongoDB database for the live
# tier (ci/docker-tests starts one).  If /results is mounted, the CTest JUnit
# report is written there.
set -euo pipefail

preset="${1:-dev}"
: "${MODENA_TEST_URI:?set MODENA_TEST_URI to the test database}"

cmake --preset "$preset" -DMODENA_TEST_URI="$MODENA_TEST_URI"
cmake --build --preset "$preset" -j "$(nproc)"
cmake --install build

# modena-env.sh is written for interactive shells and reads variables that
# may be unset.
set +u
# shellcheck disable=SC1091
. "$HOME/share/modena/modena-env.sh"
set -u
export PATH="$HOME/bin:$PATH"

# Which tests registered is itself worth recording: a wrapper that silently
# stops registering its tests is a failure mode this repository has hit.
ctest --test-dir build -N

junit=()
if [ -d /results ] && [ -w /results ]; then
    junit=(--output-junit /results/ctest-"$preset".xml)
fi
ctest --preset "$preset" "${junit[@]}"
