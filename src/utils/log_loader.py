from pathlib import Path

LOG_ROOT = Path(__file__).parents[2] / "logs" / "test_fixtures"

def load_log(category: str, filename: str) -> str:
    path = LOG_ROOT / category / filename
    return path.read_text(encoding="utf-8")

# Convenience shortcuts
def spark_failure_log():
    return load_log("spark", "spark_failure_spill.jsonl")

def airflow_failure_log():
    return load_log("airflow", "airflow_retries_failure.log")

def dq_null_spike_log():
    return load_log("data_quality", "ohlcv_null_spike.log")

def infra_pressure_log():
    return load_log("infra", "node_pressure_oom.log")
