"""config.yaml tests.

1. Every value from the doc's "Configuration values" table, and every extra setting approved
   for this session, has a key in config.yaml with the right type.
2. Modules governed by config.yaml do not hardcode the values of the keys that govern them
   (additional requirement 3 in PLAN.md: only those modules and keys are checked).
"""
import ast
import numbers
from pathlib import Path

import pytest

from common.config import REPO_ROOT, cfg, leaves

# Key -> expected Python type. Presence and type only: the values are tunable starting
# points, so the test must not pin them.
REQUIRED = {
    "dataset.sales_rows": int, "dataset.regions_rows": int, "dataset.stores_rows": int,
    "dataset.products_rows": int, "dataset.customers_per_sale": float, "dataset.returns_per_sale": float,
    "dataset.hero_region_id": int, "dataset.hero_region_share": float,
    "dataset.date_start": str, "dataset.date_end": str,
    "dataset.return_lag_days_min": int, "dataset.return_lag_days_max": int,
    "canaries.planted_target": int,
    "workload.slow_query_ms": numbers.Real, "workload.q1_runs": int,
    "postgres.pg_stat_statements_track": str, "postgres.auto_explain_log_analyze": bool,
    "postgres.statement_timeout_plan_generation_s": int,
    "plan_generation.parameter_sets_per_query": int, "plan_generation.target_plan_count": int,
    "plan_generation.early_sample_size": int,
    "gateway.hmac_code_hex_chars": int, "gateway.hmac_key_bytes": int,
    "gateway.round_significant_figures": int, "gateway.skew_top_mcv_count": int,
    "gateway.resolver_top_templates": int, "gateway.canary_fragment_chars": int,
    "miner.min_weighted_support": float, "miner.max_index_columns": int, "miner.candidates_kept": int,
    "miner.min_leading_distinct": int, "miner.drift_window_production_s": int,
    "miner.drift_window_demo_s": int, "miner.drift_js_threshold": float, "miner.drift_windows_required": int,
    "gnn.layers": int, "gnn.hidden_size": int, "gnn.dropout": float, "gnn.learning_rate": float,
    "gnn.batch_size": int, "gnn.max_epochs": int, "gnn.patience": int, "gnn.template_split": list,
    "rl.alpha": float, "rl.gamma": float, "rl.epsilon_start": float, "rl.epsilon_min": float,
    "rl.episodes": int, "rl.actions_per_episode": int, "rl.lambda_write": float,
    "rl.lambda_storage": float, "rl.storage_budget_table_share": float, "rl.configs_verified_on_twin": int,
    "rl.write_penalty_ms_per_index": float,
    "sandbox.twin_hero_table_scale": float, "sandbox.twin_other_tables_scale": float,
    "sandbox.timing_runs": int, "sandbox.pgbench_insert_rate_per_s": int,
    "verify.verieql_rows_per_table": int, "verify.verieql_timeout_s": int,
    "llm.provider": str, "llm.model": str, "llm.api_key_env": str, "llm.temperature": numbers.Real,
    "llm.max_tool_calls": int, "llm.retry_max_attempts": int,
    "approve.post_deploy_check_minutes": int, "approve.rollback_if_median_worse_by": float,
    "tests.fast_suite_limit_s": int, "tests.q1_min_twin_speedup": float,
}

# Module paths (relative to the repo root) -> config sections that govern them.
# Each build step adds its modules here as it creates them.
GOVERNED: dict[str, list[str]] = {}

# Values too generic to flag as hardcoded config (loop starts, booleans, identity).
IGNORED_VALUES = {0, 1, -1, True, False}


@pytest.mark.parametrize("key,typ", sorted(REQUIRED.items()))
def test_required_key_present_with_type(key, typ):
    value = cfg(key)
    assert isinstance(value, typ) and not (typ is int and isinstance(value, bool)), (key, value)


def test_missing_key_is_an_error():
    with pytest.raises(KeyError):
        cfg("miner.no_such_key")


def test_llm_key_is_named_not_stored():
    # Decision C: config names the env var; the key itself is never in config.yaml.
    assert cfg("llm.api_key_env") == "GEMINI_API_KEY"
    assert not any("AIza" in str(v) for v in leaves().values())


def hardcoded_config_values(source: str, sections: list[str]) -> list[tuple[int, object]]:
    """Numeric constants in source that equal a value from the governing config sections."""
    governed = {
        v for k, v in leaves().items()
        if k.split(".")[0] in sections and isinstance(v, (int, float)) and not isinstance(v, bool)
    } - IGNORED_VALUES
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool) and node.value in governed:
            hits.append((node.lineno, node.value))
    return hits


def test_detector_flags_a_hardcoded_value():
    # Self-test: the check must catch a miner value typed into code.
    bad = "MAX_COLS = 3\nTHRESHOLD = 0.05\n"
    assert {v for _, v in hardcoded_config_values(bad, ["miner"])} == {3, 0.05}
    assert hardcoded_config_values("x = cfg('miner.max_index_columns')\n", ["miner"]) == []


@pytest.mark.parametrize("module,sections", sorted(GOVERNED.items()) or [pytest.param(None, None, marks=pytest.mark.skip(reason="no governed modules exist yet; steps 5 to 13 register them"))])
def test_governed_module_has_no_hardcoded_config_values(module, sections):
    source = (REPO_ROOT / module).read_text(encoding="utf-8")
    assert hardcoded_config_values(source, sections) == [], f"{module} hardcodes config values"
