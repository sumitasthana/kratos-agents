import pytest

from src.agents.git_diff_dataflow import GitDiffDataFlowAgent
from src.agents.base import AgentType


SAMPLE_GIT_ARTIFACTS = {
    "repository": {"name": "demo", "url": "demo"},
    "files": [
        {
            "file_path": "etl/job.py",
            "commits": [
                {
                    "commit_hash": "abc123",
                    "author": "dev",
                    "date": "2026-01-20T00:00:00Z",
                    "message": "add join and write",
                    "diff": """
diff --git a/etl/job.py b/etl/job.py
index 000..111 100644
--- a/etl/job.py
+++ b/etl/job.py
@@ -1,3 +1,12 @@
+df_orders = spark.table(\"sales.orders\")
+df_users = spark.read.parquet(\"s3://bucket/users\")
+df = df_orders.join(df_users, on=[\"user_id\"], how=\"inner\")
+df2 = df.filter(\"amount > 0\").groupBy(\"region\").agg({\"amount\": \"sum\"})
+df2.write.mode(\"overwrite\").saveAsTable(\"sales.order_rollups\")
""",
                    "added_lines": 5,
                    "deleted_lines": 0,
                }
            ],
        }
    ],
}


@pytest.mark.asyncio
async def test_git_diff_dataflow_agent_heuristics_extracts_patterns():
    agent = GitDiffDataFlowAgent()
    resp = await agent.analyze_without_llm(SAMPLE_GIT_ARTIFACTS)

    assert resp.success is True
    assert resp.agent_type == AgentType.GIT_DIFF_DATAFLOW

    # explanation is JSON text containing extracted results
    assert "sales.orders" in resp.explanation
    assert "sales.order_rollups" in resp.explanation
    assert "dataframe_join" in resp.explanation
    assert "groupBy" in resp.explanation
