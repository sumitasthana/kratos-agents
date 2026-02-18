"""
Spark Event Log Downloader - Fixed
- Bypasses SSL cert issues (corporate network)
- Correct Zenodo file resolution
- Generates synthetic logs when external sources fail
Run: python download_spark_logs.py
"""

import os
import sys
import ssl
import shutil
import zipfile
import json
import gzip
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

# ── Bypass SSL cert verification (corporate proxy fix) ────────────────────────
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# ── Config ────────────────────────────────────────────────────────────────────
LOGS_DIR      = Path("./logs")
RAW_DIR       = LOGS_DIR / "raw"
PROCESSED_DIR = LOGS_DIR / "processed"
ARCHIVES_DIR  = LOGS_DIR / "archives"
TEMP_DIR      = LOGS_DIR / ".temp_download"

ZENODO_API    = "https://zenodo.org/api/records/2555074"
KAGGLE_SLUG   = "omduggineni/loghub-spark-log-data"

SKIP_KAGGLE   = "--skip-kaggle"   in sys.argv
SKIP_KUBEFLOW = "--skip-kubeflow" in sys.argv
CLEAN_TEMP    = "--clean"         in sys.argv

# ── Helpers ───────────────────────────────────────────────────────────────────
def header(text):
    print(f"\n{'=' * 65}")
    print(f"  {text}")
    print(f"{'=' * 65}\n")

def step(n, total, msg):  print(f"[{n}/{total}] {msg}")
def ok(msg):              print(f"  [OK] {msg}")
def warn(msg):            print(f"  [!!] {msg}")
def fail(msg):            print(f"  [XX] {msg}")
def info(msg):            print(f"       {msg}")

def count_files(path):
    p = Path(path)
    if not p.exists():
        return 0
    return len([f for f in p.rglob("*") if f.is_file()])

def dir_size(path):
    p = Path(path)
    if not p.exists():
        return "0 B"
    total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    for unit in ["B", "KB", "MB", "GB"]:
        if total < 1024:
            return f"{total:.1f} {unit}"
        total /= 1024
    return f"{total:.1f} TB"

def download_file(url, dest):
    info(f"URL : {url}")
    info(f"Dest: {dest}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        # Use SSL_CONTEXT to bypass corporate cert issues
        with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as r:
            total = int(r.headers.get("content-length", 0))
            done  = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = r.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done / total * 100
                        print(f"\r       Progress: {pct:.1f}%  ", end="", flush=True)
        print()
        return True
    except Exception as e:
        fail(f"Download failed: {e}")
        return False

# ── Synthetic log builder ─────────────────────────────────────────────────────
def make_event_log(
    app_id, app_name, spark_version,
    executor_memory, executor_cores, num_executors,
    aqe_enabled, broadcast_threshold, shuffle_partitions,
    num_stages, tasks_per_stage, spill_bytes, shuffle_bytes,
    duration_ms_per_task, failed_tasks
):
    """Build a realistic Spark event log (JSONL format)."""

    now_ms  = int(datetime.now(timezone.utc).timestamp() * 1000)
    events  = []

    # ── ApplicationStart ──────────────────────────────────────────────────────
    events.append({
        "Event": "SparkListenerApplicationStart",
        "App Name": app_name,
        "App ID": app_id,
        "Timestamp": now_ms,
        "User": "testuser",
        "Spark Version": spark_version,
    })

    # ── EnvironmentUpdate ─────────────────────────────────────────────────────
    events.append({
        "Event": "SparkListenerEnvironmentUpdate",
        "Spark Properties": {
            "spark.executor.memory":                  executor_memory,
            "spark.executor.cores":                   str(executor_cores),
            "spark.driver.memory":                    "2g",
            "spark.driver.cores":                     "2",
            "spark.sql.adaptive.enabled":             str(aqe_enabled).lower(),
            "spark.sql.autoBroadcastJoinThreshold":   str(broadcast_threshold),
            "spark.sql.shuffle.partitions":           str(shuffle_partitions),
            "spark.sql.cbo.enabled":                  "true" if aqe_enabled else "false",
            "spark.memory.fraction":                  "0.8" if aqe_enabled else "0.5",
            "spark.memory.storageFraction":           "0.3",
            "spark.eventLog.enabled":                 "true",
            "spark.serializer":                       "org.apache.spark.serializer.KryoSerializer",
            "scala.version":                          "2.12.15",
            "java.version":                           "11.0.17",
            "hadoop.version":                         "3.3.4",
        },
    })

    # ── BlockManagerAdded (driver + executors) ────────────────────────────────
    events.append({
        "Event":       "SparkListenerBlockManagerAdded",
        "Executor ID": "driver",
        "Block Manager ID": {"Executor ID": "driver", "Host": "localhost", "Port": 55555},
        "Max Mem":     2 * 1024 * 1024 * 1024,
        "Timestamp":   now_ms + 100,
    })
    mem_bytes = int(_parse_mem(executor_memory) * 1024 * 1024)
    for i in range(1, num_executors + 1):
        events.append({
            "Event":       "SparkListenerBlockManagerAdded",
            "Executor ID": str(i),
            "Block Manager ID": {"Executor ID": str(i), "Host": f"worker-{i}", "Port": 50000 + i},
            "Max Mem":     mem_bytes,
            "Timestamp":   now_ms + 200 + i * 10,
        })

    # ── Stages & Tasks ────────────────────────────────────────────────────────
    task_id   = 0
    stage_start = now_ms + 500

    for stage_id in range(num_stages):
        stage_name = ["csv at read.py:12", "groupBy at etl.py:34",
                      "join at transform.py:67", "write at sink.py:89",
                      "count at validate.py:22"][stage_id % 5]

        events.append({
            "Event": "SparkListenerStageSubmitted",
            "Stage Info": {
                "Stage ID":         stage_id,
                "Stage Attempt ID": 0,
                "Stage Name":       stage_name,
                "Number of Tasks":  tasks_per_stage,
                "Submission Time":  stage_start,
                "RDD Info":         [],
                "Parent IDs":       [stage_id - 1] if stage_id > 0 else [],
            },
        })

        stage_end = stage_start
        for t in range(tasks_per_stage):
            is_failed = (t < failed_tasks and stage_id == num_stages - 1)
            spill_t   = spill_bytes // tasks_per_stage
            shuffle_t = shuffle_bytes // tasks_per_stage

            task_end_ms = stage_start + duration_ms_per_task * (t + 1)
            events.append({
                "Event":          "SparkListenerTaskEnd",
                "Stage ID":       stage_id,
                "Stage Attempt ID": 0,
                "Task Type":      "ResultTask" if stage_id == num_stages - 1 else "ShuffleMapTask",
                "Task End Reason": {"Reason": "ExceptionFailure", "Description": "TaskKilled"} if is_failed else {"Reason": "Success"},
                "Task Info": {
                    "Task ID":        task_id,
                    "Attempt":        0,
                    "Launch Time":    stage_start + t * duration_ms_per_task,
                    "Executor ID":    str((t % num_executors) + 1),
                    "Host":           f"worker-{(t % num_executors) + 1}",
                    "Locality":       "PROCESS_LOCAL",
                    "Speculative":    False,
                    "Getting Result Time": 0,
                    "Finish Time":    task_end_ms,
                    "Failed":         is_failed,
                    "Killed":         False,
                    "Accumulables":   [],
                },
                "Task Metrics": {
                    "Executor Deserialize Time":   10,
                    "Executor Deserialize CPU Time": 5000000,
                    "Executor Run Time":           duration_ms_per_task - 20,
                    "Executor CPU Time":           (duration_ms_per_task - 20) * 900000,
                    "Peak Execution Memory":       mem_bytes // tasks_per_stage,
                    "Result Size":                 1024,
                    "JVM GC Time":                 50 if not aqe_enabled else 10,
                    "Result Serialization Time":   5,
                    "Memory Bytes Spilled":        spill_t,
                    "Disk Bytes Spilled":          spill_t,
                    "Shuffle Read Metrics": {
                        "Remote Blocks Fetched":  10,
                        "Local Blocks Fetched":   5,
                        "Fetch Wait Time":        20 if not aqe_enabled else 5,
                        "Remote Bytes Read":      shuffle_t // 2,
                        "Local Bytes Read":       shuffle_t // 4,
                        "Total Records Read":     10000,
                    },
                    "Shuffle Write Metrics": {
                        "Shuffle Bytes Written":  shuffle_t,
                        "Shuffle Write Time":     30 if not aqe_enabled else 8,
                        "Shuffle Records Written": 10000,
                    },
                    "Input Metrics": {"Bytes Read": 1024 * 1024, "Records Read": 50000},
                    "Output Metrics": {"Bytes Written": 0, "Records Written": 0},
                },
            })
            task_id  += 1
            stage_end = max(stage_end, task_end_ms)

        events.append({
            "Event": "SparkListenerStageCompleted",
            "Stage Info": {
                "Stage ID":         stage_id,
                "Stage Attempt ID": 0,
                "Stage Name":       stage_name,
                "Number of Tasks":  tasks_per_stage,
                "Submission Time":  stage_start,
                "Completion Time":  stage_end,
                "Failure Reason":   None,
                "Accumulables":     [],
                "RDD Info":         [],
                "Parent IDs":       [stage_id - 1] if stage_id > 0 else [],
            },
        })

        stage_start = stage_end + 50

    # ── ApplicationEnd ────────────────────────────────────────────────────────
    events.append({
        "Event":     "SparkListenerApplicationEnd",
        "Timestamp": stage_start + 200,
    })

    return events

def _parse_mem(param):
    """Convert memory string to MB."""
    param = str(param).strip().lower()
    if param.endswith("g"):
        return float(param[:-1]) * 1024
    if param.endswith("m"):
        return float(param[:-1])
    if param.endswith("k"):
        return float(param[:-1]) / 1024
    return float(param)

def write_event_log(events, path):
    """Write events as JSONL to path."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

# ── Step 1 — Directories ──────────────────────────────────────────────────────
header("Spark Event Log Downloader (Fixed)")
step(1, 5, "Setting up directory structure...")

for d in [
    RAW_DIR / "baseline",
    RAW_DIR / "degraded",
    RAW_DIR / "kaggle",
    RAW_DIR / "kubeflow",
    PROCESSED_DIR,
    ARCHIVES_DIR,
    TEMP_DIR,
]:
    d.mkdir(parents=True, exist_ok=True)

ok("Directories ready")
print()

# ── Step 2 — Zenodo (with SSL bypass) ────────────────────────────────────────
step(2, 5, "Downloading Zenodo BigDataBench dataset...")

zenodo_zip = TEMP_DIR / "zenodo_spark_logs.zip"
zenodo_ext = TEMP_DIR / "zenodo_extracted"
zenodo_ok  = False

if zenodo_zip.exists():
    info("Already downloaded, skipping")
    zenodo_ok = True
else:
    # Try REST API first
    try:
        info("Resolving file list from Zenodo API (SSL bypass)...")
        req = urllib.request.Request(ZENODO_API, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as r:
            record = json.loads(r.read())

        # Zenodo new API uses "files" list
        files = record.get("files", [])
        zip_entry = next((f for f in files if ".zip" in f.get("key", "")), None)

        if zip_entry:
            dl_url    = zip_entry["links"]["self"]
            zenodo_ok = download_file(dl_url, zenodo_zip)
        else:
            # Try direct URL patterns for this record
            info("No zip found in API, trying direct URLs...")
            urls_to_try = [
                "https://zenodo.org/record/2555074/files/logs.zip",
                "https://zenodo.org/record/2555074/files/spark-logs.zip",
                "https://zenodo.org/records/2555074/files/logs.zip",
            ]
            for url in urls_to_try:
                zenodo_ok = download_file(url, zenodo_zip)
                if zenodo_ok:
                    break

    except Exception as e:
        warn(f"Zenodo API error: {e}")

if zenodo_ok and zenodo_zip.exists():
    info("Extracting zip...")
    zenodo_ext.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zenodo_zip, "r") as z:
            z.extractall(zenodo_ext)
        info("Organising by performance profile...")

        for f in zenodo_ext.rglob("*"):
            if not f.is_file():
                continue
            name = f.name.lower()
            if "executor16" in name or "128" in name:
                shutil.copy2(f, RAW_DIR / "baseline")
            elif "executor4" in name or "32" in name:
                shutil.copy2(f, RAW_DIR / "degraded")
            elif any(name.startswith(p) for p in ("app-", "local-", "spark-")):
                bc = count_files(RAW_DIR / "baseline")
                dc = count_files(RAW_DIR / "degraded")
                shutil.copy2(f, RAW_DIR / "baseline" if bc <= dc else RAW_DIR / "degraded")

        bc = count_files(RAW_DIR / "baseline")
        dc = count_files(RAW_DIR / "degraded")
        ok(f"Zenodo done — Baseline: {bc}  |  Degraded: {dc}")
    except Exception as e:
        fail(f"Extraction failed: {e}")
        zenodo_ok = False

if not zenodo_ok:
    warn("Zenodo download failed — generating synthetic logs instead")

print()

# ── Step 3 — Kaggle ───────────────────────────────────────────────────────────
step(3, 5, "Checking Kaggle LogHub dataset...")

if SKIP_KAGGLE:
    warn("Skipped via --skip-kaggle flag")
else:
    kaggle_cli   = False
    kaggle_creds = Path.home() / ".kaggle" / "kaggle.json"

    try:
        result = subprocess.run(
            ["kaggle", "--version"],
            capture_output=True, text=True, timeout=10
        )
        kaggle_cli = result.returncode == 0
    except Exception:
        kaggle_cli = False

    if not kaggle_cli:
        warn("Kaggle CLI not found — run: pip install kaggle")
        info("Token: https://www.kaggle.com/settings -> API -> Create New Token")
        info("Then re-run this script")
    elif not kaggle_creds.exists():
        warn(f"Place kaggle.json at: {kaggle_creds}")
    else:
        info(f"Downloading {KAGGLE_SLUG} ...")
        try:
            subprocess.run(
                ["kaggle", "datasets", "download",
                 "-d", KAGGLE_SLUG, "-p", str(TEMP_DIR), "--unzip", "-q"],
                check=True, timeout=300
            )
            kaggle_src = TEMP_DIR / "loghub-spark-log-data"
            if kaggle_src.exists():
                for f in kaggle_src.rglob("*"):
                    if f.is_file():
                        shutil.copy2(f, RAW_DIR / "kaggle")
                ok(f"Kaggle done: {count_files(RAW_DIR / 'kaggle')} files")
            else:
                warn("Kaggle output directory not found")
        except Exception as e:
            warn(f"Kaggle failed: {e}")

print()

# ── Step 4 — Synthetic Logs (Baseline + Degraded) ────────────────────────────
step(4, 5, "Generating synthetic Spark event logs...")

# ── BASELINE configs (well-tuned) ─────────────────────────────────────────────
BASELINE_JOBS = [
    dict(
        label="grep_32gb_exec16",
        app_name="BigDataBench-Grep",
        spark_version="3.5.0",
        executor_memory="4g",   executor_cores=2,  num_executors=16,
        aqe_enabled=True,       broadcast_threshold=10485760,
        shuffle_partitions=200, num_stages=3,      tasks_per_stage=64,
        spill_bytes=0,          shuffle_bytes=512*1024*1024,
        duration_ms_per_task=800, failed_tasks=0,
    ),
    dict(
        label="wordcount_64gb_exec16",
        app_name="BigDataBench-WordCount",
        spark_version="3.5.0",
        executor_memory="4g",   executor_cores=2,  num_executors=16,
        aqe_enabled=True,       broadcast_threshold=10485760,
        shuffle_partitions=200, num_stages=4,      tasks_per_stage=80,
        spill_bytes=0,          shuffle_bytes=1024*1024*1024,
        duration_ms_per_task=950, failed_tasks=0,
    ),
    dict(
        label="kmeans_128gb_exec16",
        app_name="BigDataBench-KMeans",
        spark_version="3.5.0",
        executor_memory="8g",   executor_cores=4,  num_executors=16,
        aqe_enabled=True,       broadcast_threshold=10485760,
        shuffle_partitions=400, num_stages=5,      tasks_per_stage=100,
        spill_bytes=0,          shuffle_bytes=2*1024*1024*1024,
        duration_ms_per_task=1100, failed_tasks=0,
    ),
    dict(
        label="etl_pipeline_exec16",
        app_name="ETL-CustomerOrders",
        spark_version="3.5.0",
        executor_memory="6g",   executor_cores=2,  num_executors=16,
        aqe_enabled=True,       broadcast_threshold=10485760,
        shuffle_partitions=300, num_stages=6,      tasks_per_stage=50,
        spill_bytes=0,          shuffle_bytes=768*1024*1024,
        duration_ms_per_task=700, failed_tasks=0,
    ),
    dict(
        label="risk_aggregation_exec16",
        app_name="RiskAggregation-Daily",
        spark_version="3.5.0",
        executor_memory="8g",   executor_cores=4,  num_executors=16,
        aqe_enabled=True,       broadcast_threshold=20971520,
        shuffle_partitions=200, num_stages=4,      tasks_per_stage=40,
        spill_bytes=0,          shuffle_bytes=256*1024*1024,
        duration_ms_per_task=600, failed_tasks=0,
    ),
]

# ── DEGRADED configs (under-resourced, mis-tuned) ─────────────────────────────
DEGRADED_JOBS = [
    dict(
        label="grep_32gb_exec4",
        app_name="BigDataBench-Grep",
        spark_version="3.5.0",
        executor_memory="512m", executor_cores=1,  num_executors=4,
        aqe_enabled=False,      broadcast_threshold=-1,
        shuffle_partitions=1000, num_stages=3,     tasks_per_stage=64,
        spill_bytes=2*1024*1024*1024, shuffle_bytes=4*1024*1024*1024,
        duration_ms_per_task=4500, failed_tasks=5,
    ),
    dict(
        label="wordcount_64gb_exec4",
        app_name="BigDataBench-WordCount",
        spark_version="3.5.0",
        executor_memory="512m", executor_cores=1,  num_executors=4,
        aqe_enabled=False,      broadcast_threshold=-1,
        shuffle_partitions=1000, num_stages=4,     tasks_per_stage=80,
        spill_bytes=4*1024*1024*1024, shuffle_bytes=8*1024*1024*1024,
        duration_ms_per_task=5200, failed_tasks=8,
    ),
    dict(
        label="kmeans_128gb_exec4",
        app_name="BigDataBench-KMeans",
        spark_version="3.5.0",
        executor_memory="1g",   executor_cores=1,  num_executors=4,
        aqe_enabled=False,      broadcast_threshold=-1,
        shuffle_partitions=2000, num_stages=5,     tasks_per_stage=100,
        spill_bytes=8*1024*1024*1024, shuffle_bytes=16*1024*1024*1024,
        duration_ms_per_task=7800, failed_tasks=12,
    ),
    dict(
        label="etl_pipeline_exec4",
        app_name="ETL-CustomerOrders",
        spark_version="3.5.0",
        executor_memory="512m", executor_cores=1,  num_executors=4,
        aqe_enabled=False,      broadcast_threshold=-1,
        shuffle_partitions=1000, num_stages=6,     tasks_per_stage=50,
        spill_bytes=3*1024*1024*1024, shuffle_bytes=6*1024*1024*1024,
        duration_ms_per_task=6100, failed_tasks=6,
    ),
    dict(
        label="risk_aggregation_exec4",
        app_name="RiskAggregation-Daily",
        spark_version="3.5.0",
        executor_memory="1g",   executor_cores=1,  num_executors=4,
        aqe_enabled=False,      broadcast_threshold=-1,
        shuffle_partitions=1000, num_stages=4,     tasks_per_stage=40,
        spill_bytes=1*1024*1024*1024, shuffle_bytes=3*1024*1024*1024,
        duration_ms_per_task=3900, failed_tasks=3,
    ),
]

ts   = int(datetime.now(timezone.utc).timestamp())

for i, cfg in enumerate(BASELINE_JOBS):
    label  = cfg.pop("label")
    app_id = f"local-{ts + i * 1000}-baseline-{label}"
    events = make_event_log(app_id=app_id, **cfg)
    dest   = RAW_DIR / "baseline" / app_id
    write_event_log(events, dest)
    info(f"Baseline: {label}  ({len(events)} events)")

ok(f"Baseline synthetic logs: {count_files(RAW_DIR / 'baseline')} files")

for i, cfg in enumerate(DEGRADED_JOBS):
    label  = cfg.pop("label")
    app_id = f"local-{ts + i * 1000}-degraded-{label}"
    events = make_event_log(app_id=app_id, **cfg)
    dest   = RAW_DIR / "degraded" / app_id
    write_event_log(events, dest)
    info(f"Degraded: {label}  ({len(events)} events)")

ok(f"Degraded synthetic logs: {count_files(RAW_DIR / 'degraded')} files")
print()

# ── Step 5 — Archive ──────────────────────────────────────────────────────────
step(5, 5, "Creating archive backup...")

stamp        = datetime.now().strftime("%Y%m%d_%H%M%S")
archive_path = ARCHIVES_DIR / f"spark_logs_{stamp}.zip"

try:
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in RAW_DIR.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(LOGS_DIR))
    ok(f"Archive: {archive_path.name}  ({dir_size(archive_path)})")
except Exception as e:
    warn(f"Archive failed: {e}")

# ── Cleanup ───────────────────────────────────────────────────────────────────
print()
if CLEAN_TEMP:
    do_clean = "y"
else:
    do_clean = input("Clean up temp files? [Y/n]: ").strip().lower() or "y"

if do_clean != "n":
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    ok("Temp files removed")

# ── Manifest ──────────────────────────────────────────────────────────────────
bc   = count_files(RAW_DIR / "baseline")
dc   = count_files(RAW_DIR / "degraded")
kc   = count_files(RAW_DIR / "kaggle")
tot  = count_files(RAW_DIR)

manifest = f"""Spark Event Logs - Download Manifest
Generated : {datetime.now()}

Sources
  1. Zenodo BigDataBench  https://zenodo.org/records/2555074
  2. Kaggle LogHub        https://kaggle.com/datasets/omduggineni/loghub-spark-log-data
  3. Synthetic generator  (baseline vs degraded pairs)

Counts
  Baseline  : {bc}
  Degraded  : {dc}
  Kaggle    : {kc}
  Total     : {tot}

Jobs generated
  Baseline: Grep/WordCount/KMeans/ETL/RiskAgg  16 executors, AQE on,  no spill
  Degraded: Grep/WordCount/KMeans/ETL/RiskAgg   4 executors, AQE off, heavy spill
"""

(LOGS_DIR / "DOWNLOAD_MANIFEST.txt").write_text(manifest, encoding="utf-8")
ok(f"Manifest: {LOGS_DIR / 'DOWNLOAD_MANIFEST.txt'}")

# ── Summary ───────────────────────────────────────────────────────────────────
header("Download Complete")

print(f"  {'Source':<16} {'Files':>6}    Size")
print(f"  {'─' * 42}")
print(f"  {'Baseline':<16} {bc:>6}    {dir_size(RAW_DIR / 'baseline')}")
print(f"  {'Degraded':<16} {dc:>6}    {dir_size(RAW_DIR / 'degraded')}")
print(f"  {'Kaggle':<16} {kc:>6}    {dir_size(RAW_DIR / 'kaggle')}")
print(f"  {'─' * 42}")
print(f"  {'Total':<16} {tot:>6}    {dir_size(RAW_DIR)}")
print("""
  Next Steps:

  # Fingerprint baseline
  python -m src.cli fingerprint logs\\raw\\baseline\\local-*baseline* --output runs\\fingerprints\\baseline.json

  # Fingerprint degraded
  python -m src.cli fingerprint logs\\raw\\degraded\\local-*degraded* --output runs\\fingerprints\\degraded.json

  # RCA on degraded
  python -m src.cli rca --fingerprint runs\\fingerprints\\degraded.json --mode spark
""")
