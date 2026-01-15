"""
Test utilities: Generate synthetic Spark event logs for testing.
"""

import json
import random
from datetime import datetime
from pathlib import Path


def generate_sample_event_log(output_path: str, num_stages: int = 5, tasks_per_stage: int = 100) -> None:
    """
    Generate a minimal but realistic Spark event log for testing.

    Args:
        output_path: Where to write the event log
        num_stages: Number of stages to simulate
        tasks_per_stage: Tasks per stage
    """
    events = []
    base_time = int(datetime.now().timestamp() * 1000)

    # SparkListenerApplicationStart
    events.append({
        "Event": "SparkListenerApplicationStart",
        "App Name": "test-app",
        "App ID": "app-123456",
        "Timestamp": base_time,
        "User": "testuser",
        "Spark Version": "3.4.0",
    })

    # SparkListenerEnvironmentUpdate
    events.append({
        "Event": "SparkListenerEnvironmentUpdate",
        "environmentDetails": {
            "Spark Properties": [
                ["spark.executor.memory", "4g"],
                ["spark.executor.cores", "4"],
                ["spark.sql.adaptive.enabled", "true"],
            ]
        },
    })

    # SparkListenerBlockManagerAdded (driver)
    events.append({
        "Event": "SparkListenerBlockManagerAdded",
        "Timestamp": base_time + 100,
        "Executor ID": "driver",
        "Block Manager Info": {
            "Max Mem": 2147483648,  # 2GB
        },
    })

    # SparkListenerBlockManagerAdded (executors)
    for i in range(2):
        events.append({
            "Event": "SparkListenerBlockManagerAdded",
            "Timestamp": base_time + 100 + i,
            "Executor ID": str(i),
            "Block Manager Info": {
                "Max Mem": 4294967296,  # 4GB
            },
        })

    # SparkListenerSQLExecutionStart (if SQL)
    events.append({
        "Event": "SparkListenerSQLExecutionStart",
        "Execution ID": 0,
        "SQL": "SELECT * FROM table WHERE date > '2024-01-01'",
        "Physical Plan": {
            "class": "org.apache.spark.sql.execution.aggregate.HashAggregateExec",
            "children": [
                {
                    "class": "org.apache.spark.sql.execution.SortExec",
                    "children": [
                        {
                            "class": "org.apache.spark.sql.execution.joins.SortMergeJoinExec",
                            "children": []
                        }
                    ]
                }
            ]
        }
    })

    # Stages and tasks
    current_time = base_time + 1000
    for stage_id in range(num_stages):
        is_shuffle = stage_id > 0
        parent_ids = [stage_id - 1] if stage_id > 0 else []

        # SparkListenerStageSubmitted
        events.append({
            "Event": "SparkListenerStageSubmitted",
            "Stage Info": {
                "Stage ID": stage_id,
                "Stage Name": f"Stage {stage_id}: " + ("Shuffle" if is_shuffle else "Read"),
                "Number of Tasks": tasks_per_stage,
                "RDD Info": [
                    {
                        "Name": f"{'shuffle' if is_shuffle else 'rdd'}-{stage_id}",
                        "Scope": None,
                    }
                ],
                "Parent IDs": parent_ids,
                "Details": "",
                "Submission Time": current_time,
            }
        })

        # SparkListenerTaskStart/End
        for task_id in range(tasks_per_stage):
            full_task_id = stage_id * 1000 + task_id

            events.append({
                "Event": "SparkListenerTaskStart",
                "Stage ID": stage_id,
                "Task Info": {
                    "Task ID": full_task_id,
                    "Index": task_id,
                    "Attempt": 0,
                    "Launch Time": current_time + 100 + task_id * 10,
                }
            })

            # Most tasks succeed
            if random.random() > 0.02:  # 2% failure rate
                duration = random.randint(100, 2000)
                finish_time = current_time + 100 + task_id * 10 + duration

                events.append({
                    "Event": "SparkListenerTaskEnd",
                    "Stage ID": stage_id,
                    "Task Type": "ShuffleMapTask" if is_shuffle else "ResultTask",
                    "Task Info": {
                        "Task ID": full_task_id,
                        "Index": task_id,
                        "Attempt": 0,
                        "Launch Time": current_time + 100 + task_id * 10,
                        "Finish Time": finish_time,
                        "Duration": duration,
                        "Failed": False,
                        "Status": "FINISHED",
                    },
                    "Task Metrics": {
                        "Executor Deserialize Time": random.randint(1, 50),
                        "Executor Run Time": duration - random.randint(1, 50),
                        "Result Size": random.randint(100, 10000),
                        "JVM GC Time": random.randint(0, 100),
                        "Result Serialization Time": random.randint(1, 20),
                        "Memory Bytes Spilled": random.randint(0, 1000000) if is_shuffle else 0,
                        "Disk Bytes Spilled": 0,
                        "Input Bytes Read": random.randint(1000, 100000) if stage_id == 0 else 0,
                        "Input Records Read": random.randint(100, 10000) if stage_id == 0 else 0,
                        "Output Bytes": random.randint(500, 50000),
                        "Output Records": random.randint(100, 5000),
                        "Shuffle Read Bytes": random.randint(10000, 1000000) if is_shuffle else 0,
                        "Shuffle Read Records": random.randint(100, 10000) if is_shuffle else 0,
                        "Shuffle Write Bytes": random.randint(10000, 1000000) if is_shuffle else 0,
                        "Shuffle Write Records": random.randint(100, 10000) if is_shuffle else 0,
                    }
                })

        # SparkListenerStageCompleted
        events.append({
            "Event": "SparkListenerStageCompleted",
            "Stage Info": {
                "Stage ID": stage_id,
                "Stage Name": f"Stage {stage_id}",
                "Number of Tasks": tasks_per_stage,
                "RDD Info": [{"Name": f"rdd-{stage_id}"}],
                "Parent IDs": parent_ids,
                "Submission Time": current_time,
                "Completion Time": current_time + 50000,
                "Task Metrics": {
                    "Executor Deserialize Time": 1000,
                    "Executor Run Time": 40000,
                }
            }
        })

        current_time += 60000

    # SparkListenerApplicationEnd
    events.append({
        "Event": "SparkListenerApplicationEnd",
        "Timestamp": current_time + 10000,
        "App ID": "app-123456",
    })

    # Write event log
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    print(f"Generated sample event log: {output_path}")
    print(f"  Stages: {num_stages}, Tasks: {num_stages * tasks_per_stage}, Events: {len(events)}")


if __name__ == "__main__":
    # Generate sample
    generate_sample_event_log("data/sample_event_log.json", num_stages=5, tasks_per_stage=100)
