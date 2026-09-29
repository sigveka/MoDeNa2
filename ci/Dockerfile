# Clean-install test image for MoDeNa.
#
# Answers "does MoDeNa build, install and pass its tests on a machine that has
# only what we declare?".  A GitHub runner is not such a machine -- it ships
# with dozens of preinstalled toolchains -- and neither is a developer's
# workstation, where an old install can quietly satisfy a missing dependency.
#
# Do not `docker build` this directly: use ci/docker-tests, which builds it
# from the git-tracked files only (so an untracked file that makes a local
# build work cannot hide here) and runs it next to a MongoDB.
#
# Stages:
#   core  the dependencies of the `dev` preset: C library + Python
#   full  + gfortran, Octave, R (+testthat) and the portal's Python packages,
#         for the `full` preset.  Julia and MATLAB are not in apt; the `full`
#         preset skips them with a warning.

# ---------------------------------------------------------------------------
FROM ubuntu:24.04 AS deps-core

ENV DEBIAN_FRONTEND=noninteractive \
    # `modena install` and `cmake --install` both shell out to pip, and
    # Ubuntu's interpreter is marked externally managed under PEP 668.
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_NO_CACHE_DIR=1

# libltdl is a hard dependency (find_package(LTDL REQUIRED)).  libmodena
# embeds CPython, so it needs a shared libpython from python3-dev.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates \
        libltdl-dev python3-dev python3-pip \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install \
        'pydantic>=2.0' mongoengine fireworks scipy jinja2 pytest mongomock

# A non-root user whose $HOME is the install prefix, as for a real developer.
RUN useradd --create-home --shell /bin/bash modena

# ---------------------------------------------------------------------------
FROM deps-core AS deps-full

# testthat from apt, not CRAN: install.packages() compiles ~20 dependencies
# from source and only *warns* when one fails, which once left the R smoke
# silently unregistered while CI stayed green.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        gfortran octave octave-dev r-base-core r-base-dev r-cran-testthat \
 && rm -rf /var/lib/apt/lists/*

# Fail the build rather than let the R smoke quietly not register: its CMake
# gate skips it (with a warning) when testthat is not importable.
RUN R --no-save --slave -e "stopifnot(requireNamespace('testthat', quietly=TRUE))"

RUN python3 -m pip install dash dash-bootstrap-components dash-cytoscape

# ---------------------------------------------------------------------------
# The source goes in last, so dependency layers stay cached across edits.
FROM deps-core AS core
USER modena
WORKDIR /home/modena/MoDeNa
COPY --chown=modena:modena . .
ENTRYPOINT ["ci/run-tests.sh"]
CMD ["dev"]

FROM deps-full AS full
USER modena
WORKDIR /home/modena/MoDeNa
COPY --chown=modena:modena . .
ENTRYPOINT ["ci/run-tests.sh"]
CMD ["full"]
