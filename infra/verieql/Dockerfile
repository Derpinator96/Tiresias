# VeriEQL (SQL equivalence verifier) in its own image. Licence: CC BY-NC-SA 4.0
# (non-commercial, share-alike). It is cloned here and called as a separate tool; none of its
# code is copied into this MIT repository. Must be replaced if Blind Tuner is ever used
# commercially (infra/NOTES.md). Private network only: it sees real SQL, never the internet.
# VeriEQL/VeriEQL tag v1.0 = commit 3b99928bf976c11cb59c9db6a177adba21f75798.
FROM python:3.11.17-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock && rm /tmp/requirements.lock

RUN git clone https://github.com/VeriEQL/VeriEQL.git /opt/verieql \
 && git -C /opt/verieql checkout --quiet 3b99928bf976c11cb59c9db6a177adba21f75798 \
 && cp /opt/verieql/z3py_libs/*.py "$(python -c 'import os, z3; print(os.path.dirname(z3.__file__))')/"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VERIEQL_HOME=/opt/verieql
WORKDIR /opt/verieql
