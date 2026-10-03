# common/: notes

Owner: humans (not assigned in the doc)

Purpose: Shared helpers, starting with the config.yaml loader.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: the hardcoded-literal test covers only modules and keys governed by config.yaml.
- 2026-10-03: `common/config.py` reads config.yaml. `cfg("a.b")` raises KeyError on a missing key; there are no silent defaults in code. `BT_CONFIG` overrides the path for tests.
- 2026-10-03: `common/tests/test_config.py` checks presence and type of every key, not values: values are tunable starting points, so pinning them would block tuning.
- 2026-10-03: the hardcoded-literal check uses the `GOVERNED` map in that test (module path to config sections). Each build step registers its modules there. A self-test proves the detector flags a hardcoded value. Values 0, 1, -1 and booleans are ignored as too generic.
- 2026-10-03: test packages are pinned in infra/python/requirements.lock (step 4). The interim root requirements-test.txt was removed. contracts/requirements-test.txt is left in place because contracts/ is human-owned; it pins the same versions.
