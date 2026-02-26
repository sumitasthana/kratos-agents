/**
 * demoScenarios.ts
 *
 * Hard-coded demo fingerprints for the four RCA analysis paths.
 * Each entry supplies a label, a default user query, and the full JSON body
 * to POST to /api/run_rca.  Tweak values here to adjust demo behaviour.
 *
 * Fingerprint shapes mirror the Python smoke tests in tests/test_smoke_all_agents.py.
 */

// ── Scenario key ──────────────────────────────────────────────────────────────

export type ScenarioKey =
  | "spark_failure"
  | "airflow_failure"
  | "data_null_spike"
  | "infra_pressure"
  | "demo_incident";

/** ScenarioKey values that use real fixture logs via /api/run_rca_from_logs. */
export const FROM_LOGS_SCENARIOS = new Set<ScenarioKey>(["demo_incident"]);

export interface DemoScenario {
  label:        string;
  defaultQuery: string;
  /** Merged verbatim into the POST /api/run_rca body alongside user_query. */
  payload:      Record<string, unknown>;
}

// ── 1. Spark failure — memory pressure + data skew ────────────────────────────

const SPARK_FAILURE_FINGERPRINT = {
  metadata: {
    fingerprint_schema_version: "2.0.0",
    generated_at:               "2026-02-25T09:00:00Z",
    generator_version:          "demo",
    event_log_path:             "demo://spark-failure",
    event_log_size_bytes:       52_428_800,
    events_parsed:              1_240,
  },
  semantic: {
    dag: {
      stages: [
        { stage_id: 0, stage_name: "read_raw_events",     num_partitions: 200, is_shuffle_stage: false, rdd_name: null, description: "Read raw event parquet from S3 — 120 GB" },
        { stage_id: 1, stage_name: "explode_attributes",  num_partitions: 200, is_shuffle_stage: false, rdd_name: null, description: "Explode nested attribute arrays" },
        { stage_id: 2, stage_name: "join_user_profiles",  num_partitions: 400, is_shuffle_stage: true,  rdd_name: null, description: "Broadcast join with user profile dimension" },
        { stage_id: 3, stage_name: "aggregate_by_region", num_partitions: 400, is_shuffle_stage: true,  rdd_name: null, description: "COUNT(*) GROUP BY region, date — skewed partition" },
      ],
      edges: [
        { from_stage_id: 0, to_stage_id: 1, shuffle_required: false, reason: "narrow" },
        { from_stage_id: 1, to_stage_id: 2, shuffle_required: true,  reason: "join" },
        { from_stage_id: 2, to_stage_id: 3, shuffle_required: true,  reason: "groupBy" },
      ],
      root_stage_ids: [0],
      leaf_stage_ids: [3],
      total_stages:   4,
    },
    physical_plan: null,
    logical_plan_hash: {
      plan_hash:  "demo-failure-hash",
      plan_text:  "SELECT region, date, COUNT(*) FROM events JOIN users ON events.user_id = users.id GROUP BY region, date",
      is_sql:     true,
    },
    semantic_hash:    "demo-failure-semantic",
    description:      "Event aggregation pipeline with user profile join — 4 stages, heavy shuffle",
    evidence_sources: [],
  },
  context: {
    spark_config: {
      spark_version:  "3.4.1",
      scala_version:  null,
      java_version:   null,
      hadoop_version: null,
      app_name:       "event-aggregation-prod",
      master_url:     "yarn",
      config_params: {
        "spark.executor.memory":            "4g",
        "spark.driver.memory":              "8g",
        "spark.sql.shuffle.partitions":     "400",
        "spark.sql.autoBroadcastJoinThreshold": "-1",
      },
      description: "Production YARN cluster — 4 GB executors, no auto-broadcast",
    },
    executor_config: {
      total_executors:    40,
      executor_memory_mb: 4_096,
      executor_cores:     2,
      driver_memory_mb:   8_192,
      driver_cores:       4,
      description:        "40 executors × 4 GB × 2 cores",
    },
    submit_params: {
      submit_time:       "2026-02-25T08:45:00Z",
      user:              "etl-service",
      app_id:            "application_1708858800_0042",
      queue:             "production",
      additional_params: {},
    },
    jvm_settings:         {},
    optimizations_enabled: [],
    description:          "Production YARN cluster",
    compliance_context:   null,
    evidence_sources:     [],
  },
  metrics: {
    execution_summary: {
      total_duration_ms:   1_800_000,          // 30 min — 3× baseline
      total_tasks:         800,
      total_stages:        4,
      total_input_bytes:   120_000_000_000,    // 120 GB
      total_output_bytes:  500_000_000,
      total_shuffle_bytes: 95_000_000_000,     // 95 GB shuffle — massive
      total_spill_bytes:   18_000_000_000,     // 18 GB spill → OOM pressure
      failed_task_count:   35,                 // ← key failure indicator
      executor_loss_count: 3,
      max_concurrent_tasks: 64,
    },
    stage_metrics: [],
    task_distribution: {
      duration_ms:         { min_val: 500,   p25: 2_000,        p50: 8_000,      p75: 45_000,       p99: 420_000,       max_val: 860_000,       mean: 18_000,       stddev: 55_000,      count: 800, outlier_count: 42 },
      input_bytes:         { min_val: 0,     p25: 50_000_000,   p50: 120_000_000, p75: 450_000_000, p99: 3_500_000_000, max_val: 12_000_000_000, mean: 150_000_000,  stddev: 800_000_000, count: 800, outlier_count: 38 },
      output_bytes:        { min_val: 0,     p25: 1_000,        p50: 5_000,      p75: 20_000,       p99: 200_000,       max_val: 500_000,        mean: 8_000,        stddev: 25_000,      count: 800, outlier_count: 12 },
      shuffle_read_bytes:  { min_val: 0,     p25: 10_000_000,   p50: 80_000_000, p75: 500_000_000,  p99: 4_000_000_000, max_val: 15_000_000_000, mean: 200_000_000,  stddev: 900_000_000, count: 800, outlier_count: 45 },
      shuffle_write_bytes: { min_val: 0,     p25: 5_000_000,    p50: 60_000_000, p75: 400_000_000,  p99: 3_500_000_000, max_val: 12_000_000_000, mean: 180_000_000,  stddev: 800_000_000, count: 800, outlier_count: 40 },
      spill_bytes:         { min_val: 0,     p25: 0,            p50: 200_000_000, p75: 2_000_000_000, p99: 8_000_000_000, max_val: 18_000_000_000, mean: 600_000_000, stddev: 2_000_000_000, count: 800, outlier_count: 55 },
    },
    anomalies:                  [],
    key_performance_indicators: {},
    description:                "30 min with 35 task failures, 18 GB spill, 95 GB shuffle",
    evidence_sources:           [],
  },
  execution_class:  "memory_bound",
  analysis_hints:   ["high_spill", "data_skew", "executor_loss"],
};

// ── 2. Airflow failure — ConnectionError on final retry ───────────────────────

const AIRFLOW_FAILURE_FINGERPRINT = {
  dag_id:         "prices_dag",
  task_id:        "load_prices",
  execution_date: "2026-02-25T04:00:00+00:00",
  try_number:     2,
  max_retries:    2,
  log_lines: [
    "[2026-02-25, 04:00:00 +0000] {taskinstance.py:1332} INFO - Starting attempt 2 of 2",
    "[2026-02-25, 04:00:00 +0000] {taskinstance.py:1353} INFO - Executing <Task(PythonOperator): load_prices> on 2026-02-25 04:00:00+00:00",
    "[2026-02-25, 04:00:01 +0000] {standard_task_runner.py:55} INFO - Started process 31245 to run task",
    "[2026-02-25, 04:00:02 +0000] {logging_mixin.py:137} INFO - Downloading prices for symbol=AAPL date=2026-02-24",
    "[2026-02-25, 04:00:03 +0000] {logging_mixin.py:137} INFO - Requesting data from https://api.example.com/prices?symbol=AAPL&date=2026-02-24",
    "[2026-02-25, 04:00:08 +0000] {logging_mixin.py:137} ERROR - HTTPConnectionPool(host='api.example.com', port=443): Max retries exceeded with url: /prices?symbol=AAPL&date=2026-02-24 (Caused by NewConnectionError: Failed to establish a new connection: [Errno -2] Name or service not known)",
    "[2026-02-25, 04:00:08 +0000] {logging_mixin.py:137} ERROR - Failed to download prices for AAPL: ConnectionError",
    "[2026-02-25, 04:00:08 +0000] {taskinstance.py:2100} ERROR - Task failed with exception",
    "Traceback (most recent call last):",
    "  File \"/opt/airflow/dags/prices_dag.py\", line 58, in load_prices",
    "    data = client.fetch_prices(symbol=symbol, date=trade_date)",
    "  File \"/opt/airflow/dags/prices_dag.py\", line 23, in fetch_prices",
    "    response = requests.get(url, timeout=5)",
    "requests.exceptions.ConnectionError: HTTPConnectionPool(host='api.example.com', port=443): Max retries exceeded",
    "[2026-02-25, 04:00:09 +0000] {taskinstance.py:2151} ERROR - Marking task as FAILED. dag_id=prices_dag, task_id=load_prices, execution_date=2026-02-25 04:00:00+00:00, try_number=2",
    "[2026-02-25, 04:00:09 +0000] {local_task_job.py:222} INFO - Task exited with return code 1",
  ],
};

// ── 3. Data null spike — OHLCV columns ≈40 % null vs 0 % baseline ────────────

const DATA_NULL_SPIKE_FINGERPRINT = {
  dataset_name: "prices_daily",
  row_count:    390,
  columns: [
    { name: "symbol", dtype: "object",  null_rate: 0.00 },
    { name: "date",   dtype: "object",  null_rate: 0.00 },
    { name: "open",   dtype: "float64", null_rate: 0.43, mean: 125.3 },   // ← spike
    { name: "high",   dtype: "float64", null_rate: 0.41, mean: 127.1 },
    { name: "low",    dtype: "float64", null_rate: 0.42, mean: 123.8 },
    { name: "close",  dtype: "float64", null_rate: 0.45, mean: 126.0 },   // worst
    { name: "volume", dtype: "int64",   null_rate: 0.00, mean: 4_200_000 },
  ],
  reference: {
    dataset_name: "prices_daily_baseline",
    row_count:    385,
    columns: [
      { name: "symbol", dtype: "object",  null_rate: 0.00 },
      { name: "date",   dtype: "object",  null_rate: 0.00 },
      { name: "open",   dtype: "float64", null_rate: 0.00, mean: 124.9 },
      { name: "high",   dtype: "float64", null_rate: 0.00, mean: 126.5 },
      { name: "low",    dtype: "float64", null_rate: 0.00, mean: 123.2 },
      { name: "close",  dtype: "float64", null_rate: 0.00, mean: 125.5 },
      { name: "volume", dtype: "int64",   null_rate: 0.00, mean: 4_100_000 },
    ],
  },
};

// ── 4. Infra pressure — mirrors build_infra_fingerprint() in smoke tests ──────

const INFRA_PRESSURE_FINGERPRINT = {
  cluster_id:             "prod-spark-01",
  environment:            "production",
  time_window:            "2026-02-25T08:00:00Z / 2026-02-25T09:00:00Z",
  cpu_utilization:        87.5,   // > 85 % → HIGH
  memory_utilization:     91.0,   // near 92 % → approaching CRITICAL
  disk_io_utilization:    62.0,
  network_io_utilization: 45.0,
  total_workers:          20,
  available_workers:       8,     // 40 % free → HIGH
  queued_tasks:           310,    // > 200 → HIGH
  autoscale_events: [
    { direction: "down", delta: 4, timestamp: "2026-02-25T08:30:00Z" },
  ],
  alert_count:  6,
  error_count: 14,
};

// ── Exported map ──────────────────────────────────────────────────────────────

export const DEMO_SCENARIOS: Record<ScenarioKey, DemoScenario> = {
  spark_failure: {
    label:        "Spark Failure",
    defaultQuery: "Why are my Spark tasks failing with OOM errors?",
    payload: {
      execution_fingerprint: SPARK_FAILURE_FINGERPRINT,
    },
  },
  airflow_failure: {
    label:        "Airflow Failure",
    defaultQuery: "Why did my Airflow DAG task fail on the last retry?",
    payload: {
      airflow_fingerprint: AIRFLOW_FAILURE_FINGERPRINT,
    },
  },
  data_null_spike: {
    label:        "Data Null Spike",
    defaultQuery: "Are there data quality issues in the latest prices dataset?",
    payload: {
      data_fingerprint: DATA_NULL_SPIKE_FINGERPRINT,
    },
  },
  infra_pressure: {
    label:        "Infra Pressure",
    defaultQuery: "Why is the production cluster performing poorly?",
    payload: {
      trigger:           "infra_check",
      infra_fingerprint: INFRA_PRESSURE_FINGERPRINT,
    },
  },
  demo_incident: {
    label:        "Demo Incident (Real Logs)",
    defaultQuery: "Investigate the OHLCV pipeline incident using real fixture logs",
    // payload is unused — the UI calls /api/run_rca_from_logs with an
    // `include` dict built from checkboxes instead.
    payload: {},
  },
};
