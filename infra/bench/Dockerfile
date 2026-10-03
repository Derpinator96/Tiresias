# Plan generation image (step 18): the shared Python image plus the DSB and TPC-H
# generators, built from pinned commits. Used only by the `bench` tools service on the
# private network; never by gateway, ai or dashboard. Build context: infra/.
#
# microsoft/dsb  ec9a156ceee923db1114cbe388f6183b53d49787 (MIT License)
# gregrahn/tpch-kit 852ad0a5ee31ebefeed884cea4188781dd9613a3 (TPC EULA 2.2: used locally,
#   not redistributed; no performance results are published from it)
FROM python:3.11.17-slim AS kits

RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc make bison flex git ca-certificates libc6-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone https://github.com/microsoft/dsb.git \
 && git -C dsb checkout --quiet ec9a156ceee923db1114cbe388f6183b53d49787 \
 && make -C dsb/code/tools LINUX_YACC="bison -y"
# Old C sources: -fcommon restores the pre-GCC-10 handling of tentative definitions.
RUN git clone https://github.com/gregrahn/tpch-kit.git \
 && git -C tpch-kit checkout --quiet 852ad0a5ee31ebefeed884cea4188781dd9613a3 \
 && make -C tpch-kit/dbgen MACHINE=LINUX DATABASE=POSTGRESQL CC="gcc -fcommon"

# Reuse the shared Python image (built by `make up`) instead of reinstalling the lock: on a
# slow network that saves the whole package download.
FROM blind-tuner-python:local

ENV DSB_HOME=/opt/dsb \
    TPCH_HOME=/opt/tpch

COPY --from=kits /src/dsb/code/tools /opt/dsb/tools
COPY --from=kits /src/dsb/scripts /opt/dsb/scripts
COPY --from=kits /src/dsb/query_templates_pg /opt/dsb/query_templates_pg
COPY --from=kits /src/tpch-kit/dbgen /opt/tpch/dbgen

WORKDIR /app
