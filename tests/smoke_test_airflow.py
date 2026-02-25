import asyncio

import pytest

from agents.airflow_log_analyzer import AirflowLogAnalyzerAgent
from orchestrator import KratosOrchestrator


LOG_LINES = [
    "[2026-02-25, 10:15:00 +0000] {taskinstance.py:1332} INFO - Starting attempt 1 of 2",
    "[2026-02-25, 10:15:00 +0000] {taskinstance.py:1353} INFO - Executing <Task(PythonOperator): load_prices> on 2026-02-25 10:15:00+00:00",
    "[2026-02-25, 10:15:00 +0000] {taskinstance.py:1541} INFO - Running task instance: prices_dag.load_prices "
    "scheduled__2026-02-25T10:15:00+00:00 try_number 1",
    "[2026-02-25, 10:15:00 +0000] {standard_task_runner.py:55} INFO - Started process 21789 to run task",
    "[2026-02-25, 10:15:00 +0000] {standard_task_runner.py:82} INFO - Running: ['airflow', 'tasks', 'run', "
    "'prices_dag', 'load_prices', '2026-02-25T10:15:00+00:00', '--job-id', '11234', '--pool', 'default_pool', "
    "'--raw', '--subdir', 'DAGS_FOLDER/prices_dag.py', '--cfg-path', '/tmp/tmpm8c1z9q0']",
    "[2026-02-25, 10:15:00 +0000] {standard_task_runner.py:83} INFO - Job 11234: Subtask load_prices",
    "[2026-02-25, 10:15:01 +0000] {logging_mixin.py:137} INFO - Running <TaskInstance: prices_dag.load_prices "
    "scheduled__2026-02-25T10:15:00+00:00 [running]> on host airflow-worker-0",
    "[2026-02-25, 10:15:01 +0000] {taskinstance.py:2607} INFO - Exporting env vars: "
    "AIRFLOW_CTX_DAG_ID=prices_dag AIRFLOW_CTX_TASK_ID=load_prices AIRFLOW_CTX_EXECUTION_DATE=2026-02-25T10:15:00+00:00 "
    "AIRFLOW_CTX_DAG_RUN_ID=scheduled__2026-02-25T10:15:00+00:00",
    "[2026-02-25, 10:15:02 +0000] {logging_mixin.py:137} INFO - Importing DAG from DAGS_FOLDER/prices_dag.py",
    "[2026-02-25, 10:15:03 +0000] {logging_mixin.py:137} INFO - Downloading prices for symbol=NVDA date=2026-02-24",
    "[2026-02-25, 10:15:04 +0000] {logging_mixin.py:137} INFO - Requesting data from "
    "https://api.example.com/prices?symbol=NVDA&date=2026-02-24",
    "[2026-02-25, 10:15:05 +0000] {logging_mixin.py:137} INFO - Fetched 390 OHLCV records",
    "[2026-02-25, 10:15:05 +0000] {logging_mixin.py:137} INFO - Normalizing schema: timezone=America/New_York, freq=1min",
    "[2026-02-25, 10:15:06 +0000] {logging_mixin.py:137} INFO - Writing data to s3://quant-data/prices/nvda/2026-02-24.parquet",
    "[2026-02-25, 10:15:07 +0000] {logging_mixin.py:137} INFO - Successfully wrote 390 rows (390 inserts, 0 updates)",
    "[2026-02-25, 10:15:07 +0000] {python.py:179} INFO - Done. Returned value: {'rows': 390, 'symbol': 'NVDA', 'date': '2026-02-24'}",
    "[2026-02-25, 10:15:07 +0000] {taskinstance.py:2100} INFO - Marking task as SUCCESS. "
    "dag_id=prices_dag, task_id=load_prices, execution_date=2026-02-25 10:15:00+00:00",
    "[2026-02-25, 10:15:07 +0000] {taskinstance.py:2151} INFO - 1 downstream tasks scheduled from follow-on schedule check",
    "[2026-02-25, 10:15:07 +0000] {local_task_job.py:222} INFO - Task exited with return code 0",
    "[2026-02-25, 10:15:07 +0000] {taskinstance.py:2741} INFO - 0 rows deleted from task_reschedule for task 'load_prices'",
    "[2026-02-25, 10:15:07 +0000] {taskinstance.py:2793} INFO - Finished task: prices_dag.load_prices "
    "scheduled__2026-02-25T10:15:00+00:00",
]


def _build_airflow_fingerprint() -> dict:
    return {
        "dag_id": "prices_dag",
        "task_id": "load_prices",
        "execution_date": "2026-02-25T10:15:00+00:00",
        "try_number": 1,
        "max_retries": 2,
        "log_lines": LOG_LINES,
    }


@pytest.mark.asyncio
async def test_airflow_log_analyzer_agent_happy_path() -> None:
    agent = AirflowLogAnalyzerAgent()
    fingerprint = _build_airflow_fingerprint()

    resp = await agent.analyze(fingerprint_data=fingerprint)

    # keep your prints if you want console inspection
    print("=== AirflowLogAnalyzerAgent direct ===")
    print("Success:", resp.success)
    print("Summary:", resp.summary)
    print("\nKey findings:")
    for k in resp.key_findings:
        print("-", k)
    print("\nExplanation:\n", resp.explanation)
    print("=" * 80)

    # sanity assertions so CI can catch regressions
    assert resp.success is True
    assert resp.summary
    assert "SUCCESS" in resp.summary.upper() or "healthy" in resp.summary.lower()


@pytest.mark.asyncio
async def test_kratos_orchestrator_with_airflow_happy_path() -> None:
    kratos = KratosOrchestrator()
    airflow_fingerprint = _build_airflow_fingerprint()

    report = await kratos.run(
        user_query="Check Airflow task health and behaviour",
        airflow_fingerprint=airflow_fingerprint,
    )

    issue_profile = report.issue_profile

    print("=== KratosOrchestrator with Airflow ===")
    print("Dominant problem type:", issue_profile.dominant_problem_type)
    print("Overall health score:", issue_profile.overall_health_score)
    print("Overall confidence:", issue_profile.overall_confidence)

    if issue_profile.log_analysis is not None:
        print("\nLog analysis problem type:", issue_profile.log_analysis.problem_type)
        print("Log executive summary:")
        print(issue_profile.log_analysis.executive_summary)

    print("\nExecutive summary (recommendation report):")
    print(report.executive_summary)

    if report.prioritized_fixes:
        print("\nPrioritized fixes:")
        for fix in report.prioritized_fixes:
            print("-", fix.title)
    else:
        print("\nNo fixes generated (as expected for a healthy run).")

    # assertions
    assert issue_profile.dominant_problem_type.name == "HEALTHY"
    assert issue_profile.overall_health_score >= 0.8
    assert report.executive_summary
if __name__ == "__main__":
    asyncio.run(test_airflow_log_analyzer_agent_happy_path())
    asyncio.run(test_kratos_orchestrator_with_airflow_happy_path())
