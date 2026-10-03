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
    "workload.slow_query_ms": numbers.Real, "workload.q1_runs": int, "workload.q2_runs": int,
    "workload.q2_month": str, "workload.qor_regions": list,
    "postgres.pg_stat_statements_track": str, "postgres.auto_explain_log_analyze": bool,
    "postgres.statement_timeout_plan_generation_s": int,
    "plan_generation.parameter_sets_per_query": int, "plan_generation.target_plan_count": int,
    "plan_generation.early_sample_size": int,
    "plan_generation.index_setups_per_query_min": int, "plan_generation.index_setups_per_query_max": int,
    "plan_generation.dsb_scale_factor": int, "plan_generation.tpch_scale_factor": int,
    "plan_generation.workers": int, "plan_generation.quickmart_scales": list,
    "plan_generation.max_copies_per_shape": int, "plan_generation.shape_rows_log2_bucket": numbers.Real,
    "plan_generation.output_dir": str,
    "gateway.hmac_code_hex_chars": int, "gateway.hmac_key_bytes": int,
    "gateway.round_significant_figures": int, "gateway.skew_top_mcv_count": int,
    "gateway.resolver_top_templates": int, "gateway.canary_fragment_chars": int,
    "miner.min_weighted_support": float, "miner.max_index_columns": int, "miner.candidates_kept": int,
    "miner.min_leading_distinct": int, "miner.drift_window_production_s": int,
    "miner.drift_window_demo_s": int, "miner.drift_js_threshold": float, "miner.drift_windows_required": int,
    "miner.drift_window_mode": str, "miner.drift_sample_s": numbers.Real, "miner.drift_windows_kept": int,
    "workload.q4_segment": str, "workload.q4_dates": list, "workload.drift_before": list,
    "workload.drift_after": list,
    "gnn.layers": int, "gnn.hidden_size": int, "gnn.dropout": float, "gnn.learning_rate": float,
    "gnn.batch_size": int, "gnn.max_epochs": int, "gnn.patience": int, "gnn.template_split": list,
    "gnn.dataset_dir": str, "gnn.misestimate_ratio_alert": numbers.Real,
    "rl.alpha": float, "rl.gamma": float, "rl.epsilon_start": float, "rl.epsilon_min": float,
    "rl.episodes": int, "rl.actions_per_episode": int, "rl.lambda_write": float,
    "rl.lambda_storage": float, "rl.storage_budget_table_share": float, "rl.configs_verified_on_twin": int,
    "rl.write_penalty_ms_per_index": float, "rl.q_init": float,
    "rl.lambda_disagreement": float, "rl.sim_cache_s": int,
    "sandbox.twin_hero_table_scale": float, "sandbox.twin_other_tables_scale": float,
    "sandbox.timing_runs": int, "sandbox.pgbench_insert_rate_per_s": int, "sandbox.pgbench_duration_s": int,
    "sandbox.fidelity_queries": dict, "sandbox.fidelity_path": str,
    "verify.verieql_rows_per_table": int, "verify.verieql_timeout_s": int,
    "llm.provider": str, "llm.model": str, "llm.api_key_env": str, "llm.temperature": numbers.Real,
    "llm.max_tool_calls": int, "llm.retry_max_attempts": int,
    "llm.fallback": list, "llm.nim.model": str, "llm.openai.base_url": str, "llm.openai.model": str,
    "llm.openai.api_key_env": str, "llm.openai.max_tokens": int, "llm.openai.max_tokens_field": str,
    "llm.openai.send_temperature": bool, "llm.nim.max_tokens_field": str, "llm.nim.send_temperature": bool,
    "llm.ollama.base_url": str, "llm.ollama.model": str, "llm.ollama.num_ctx": int, "llm.ollama.num_predict": int,
    "llm.ollama.chars_per_token": float, "llm.ollama.malformed_retries": int, "llm.ollama.timeout_s": int,
    "approve.post_deploy_check_minutes": int, "approve.rollback_if_median_worse_by": float,
    "approve.demo_check_minutes": float,
    "tests.fast_suite_limit_s": int, "tests.q1_min_twin_speedup": float, "tests.q2_min_twin_speedup": float,
    "privacy.adversarial_max_chars": int,
    "egress.allowed_hosts": list, "egress.allowed_ports": list, "egress.connect_timeout_s": numbers.Real,
}

# Module path (relative to the repo root) -> the config keys that govern it. Only these
# modules and keys are checked (additional requirement 3 in PLAN.md). Each build step
# registers its modules here as it creates them.
GOVERNED: dict[str, list[str]] = {
    "db/generate.py": ["dataset.sales_rows", "dataset.regions_rows", "dataset.stores_rows",
                       "dataset.products_rows", "dataset.customers_per_sale", "dataset.returns_per_sale",
                       "dataset.hero_region_id", "dataset.hero_region_share", "dataset.top_product_share",
                       "dataset.top_product_revenue_share", "dataset.recent_density_ratio",
                       "dataset.return_lag_days_min", "dataset.return_lag_days_max", "dataset.random_seed",
                       "workload.copy_batch_rows"],
    "db/apply_settings.py": ["workload.slow_query_ms"],
    "db/run_q1.py": ["workload.q1_runs", "workload.q2_runs"],
    "db/workload.py": ["dataset.hero_region_id"],
    "gateway/keys.py": ["gateway.hmac_key_bytes"],
    "gateway/hashing.py": ["gateway.hmac_code_hex_chars"],
    "gateway/rounding.py": ["gateway.round_significant_figures"],
    "gateway/canary_scan.py": ["gateway.canary_fragment_chars"],
    "gateway/ingest/stats.py": ["gateway.skew_top_mcv_count"],
    "miner/fpgrowth.py": ["miner.unweighted_min_support", "miner.min_weighted_support",
                          "miner.max_index_columns", "miner.min_leading_distinct", "miner.candidates_kept"],
    "db/twin/build.py": ["sandbox.twin_hero_table_scale", "sandbox.twin_other_tables_scale", "dataset.random_seed",
                         "workload.copy_batch_rows"],
    "db/sandbox/twin_measure.py": ["sandbox.timing_runs", "sandbox.warmup_runs"],
    "db/sandbox/write_cost.py": ["sandbox.pgbench_insert_rate_per_s", "sandbox.pgbench_duration_s",
                                 "dataset.random_seed"],
    "db/sandbox/fidelity.py": ["sandbox.timing_runs", "sandbox.warmup_runs"],
    "agent/llm.py": ["llm.temperature", "llm.retry_max_attempts", "llm.retry_initial_backoff_s",
                     "llm.retry_backoff_multiplier", "llm.retry_max_backoff_s", "llm.ollama.num_ctx",
                     "llm.ollama.num_predict", "llm.ollama.chars_per_token", "llm.ollama.malformed_retries",
                     "llm.ollama.timeout_s", "llm.nim.max_tokens", "llm.nim.timeout_s",
                     "llm.nim.min_request_interval_s", "llm.openai.max_tokens", "llm.openai.timeout_s"],
    "scripts/llm_bench.py": ["llm.nim.bench_candidates"],
    "agent/agent.py": ["llm.max_tool_calls", "llm.checker_retries"],
    "rl/search.py": ["rl.lambda_write", "rl.lambda_storage", "rl.write_penalty_ms_per_index",
                     "rl.storage_budget_table_share", "rl.actions_per_episode", "rl.alpha", "rl.gamma",
                     "rl.epsilon_start", "rl.epsilon_min", "rl.episodes", "rl.lambda_disagreement",
                     "rl.sim_cache_s"],
    "db/plangen/run.py": ["plan_generation.parameter_sets_per_query", "plan_generation.early_sample_size",
                          "plan_generation.target_plan_count", "plan_generation.workers",
                          "postgres.statement_timeout_plan_generation_s"],
    "db/plangen/quickmart_templates.py": ["dataset.regions_rows",
                                          "dataset.stores_rows"],
    "models/gnn/train.py": ["gnn.learning_rate", "gnn.batch_size", "gnn.max_epochs", "gnn.patience", "gnn.weight_decay",
                            "gnn.hidden_size", "gnn.layers", "gnn.dropout"],
    # drift_windows_required (2) is not listed for miner/drift.py: its literal 2 is the log base of
    # the Jensen-Shannon distance (the doc's 0-to-1 scale), not a window count.
    "miner/drift.py": ["miner.drift_js_threshold"],
    "gateway/windows.py": ["miner.drift_sample_s", "miner.drift_windows_kept", "miner.drift_window_demo_s",
                           "miner.drift_window_production_s"],
    "db/drift_demo.py": ["miner.drift_windows_required"],
    "gateway/service.py": ["gateway.plans_per_template", "gateway.resolver_top_templates",
                           "gateway.dehash_query_chars", "workload.slow_query_ms"],
    "gateway/approve.py": ["approve.post_deploy_check_minutes", "approve.rollback_if_median_worse_by",
                           "approve.demo_check_minutes", "sandbox.warmup_runs"],
    "gateway/post_deploy_check.py": ["approve.post_deploy_check_minutes", "approve.rollback_if_median_worse_by",
                                     "sandbox.warmup_runs"],
    "agent/adversary.py": ["privacy.adversarial_max_chars"],
    "infra/egress_proxy.py": ["egress.connect_timeout_s"],
}

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


def hardcoded_config_values(source: str, keys: list[str]) -> list[tuple[int, object]]:
    """Numeric constants in source that equal the value of one of the governing keys."""
    governed = {v for k in keys if isinstance(v := cfg(k), (int, float)) and not isinstance(v, bool)} - IGNORED_VALUES
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))                 and not isinstance(node.value, bool) and node.value in governed:
            hits.append((node.lineno, node.value))
    return hits


def test_detector_flags_a_hardcoded_value():
    # Self-test: the check must catch a miner value typed into code.
    bad = "MAX_COLS = 3\nTHRESHOLD = 0.05\n"
    keys = ["miner.max_index_columns", "miner.min_weighted_support"]
    assert {v for _, v in hardcoded_config_values(bad, keys)} == {3, 0.05}
    assert hardcoded_config_values("x = cfg('miner.max_index_columns')\n", keys) == []


@pytest.mark.parametrize("module,keys", sorted(GOVERNED.items()))
def test_governed_module_has_no_hardcoded_config_values(module, keys):
    source = (REPO_ROOT / module).read_text(encoding="utf-8")
    assert hardcoded_config_values(source, keys) == [], f"{module} hardcodes config values"
