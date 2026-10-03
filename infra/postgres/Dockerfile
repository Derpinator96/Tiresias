# PostgreSQL 16 with pg_stat_statements and auto_explain (both ship with Postgres) and HypoPG.
# Versions checked on 2026-10-03: PG_VERSION 16.15-1.pgdg12+2, HypoPG 1.4.3-1.pgdg12+2.
FROM postgres:16.15-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-hypopg=1.4.3-1.pgdg12+2 \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /var/log/pglog \
 && chown postgres:postgres /var/log/pglog \
 && chmod 755 /var/log/pglog

COPY postgresql.conf /etc/postgresql/postgresql.conf
COPY init/ /docker-entrypoint-initdb.d/
