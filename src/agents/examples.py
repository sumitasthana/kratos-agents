"""
Example usage of the Query Understanding Agent.

Run with: python -m src.agents.examples
"""

import asyncio
import os
from .query_understanding import QueryUnderstandingAgent
from .base import LLMConfig


# Sample fingerprint data (minimal example)
SAMPLE_FINGERPRINT = {
    "semantic": {
        "semantic_hash": "a1b2c3d4e5f6789",
        "description": "Read parquet, filter by date, join with users, aggregate by region",
        "dag": {
            "total_stages": 4,
            "stages": [
                {
                    "stage_id": 0,
                    "stage_name": "FileScan parquet",
                    "num_partitions": 200,
                    "is_shuffle_stage": False,
                    "description": "Scan orders table from parquet files"
                },
                {
                    "stage_id": 1,
                    "stage_name": "FileScan parquet",
                    "num_partitions": 10,
                    "is_shuffle_stage": False,
                    "description": "Scan users dimension table"
                },
                {
                    "stage_id": 2,
                    "stage_name": "ShuffledHashJoin",
                    "num_partitions": 200,
                    "is_shuffle_stage": True,
                    "description": "Join orders with users on user_id"
                },
                {
                    "stage_id": 3,
                    "stage_name": "HashAggregate",
                    "num_partitions": 200,
                    "is_shuffle_stage": True,
                    "description": "Aggregate order totals by region"
                }
            ],
            "edges": [
                {
                    "from_stage_id": 0,
                    "to_stage_id": 2,
                    "shuffle_required": True,
                    "reason": "join key shuffle"
                },
                {
                    "from_stage_id": 1,
                    "to_stage_id": 2,
                    "shuffle_required": True,
                    "reason": "join key shuffle"
                },
                {
                    "from_stage_id": 2,
                    "to_stage_id": 3,
                    "shuffle_required": True,
                    "reason": "aggregation shuffle"
                }
            ],
            "root_stage_ids": [0, 1],
            "leaf_stage_ids": [3]
        },
        "logical_plan_hash": {
            "plan_hash": "abc123",
            "plan_text": """
Aggregate [region], [sum(order_total) AS total_sales]
+- Filter (order_date >= '2024-01-01')
   +- Join Inner, (orders.user_id = users.user_id)
      :- Relation[order_id, user_id, order_total, order_date] parquet
      +- Relation[user_id, name, region] parquet
            """.strip(),
            "is_sql": True
        },
        "physical_plan": {
            "node_id": "0",
            "operator": "HashAggregate",
            "description": "Final aggregation by region",
            "estimated_rows": 50,
            "attributes": {"keys": ["region"], "functions": ["sum(order_total)"]},
            "children": ["1"]
        }
    }
}


async def run_with_llm():
    """Run query understanding with LLM (requires API key)."""
    # Configure LLM - uses OPENAI_API_KEY env var by default
    config = LLMConfig(
        provider="openai",
        model="gpt-4o",
        temperature=0.3
    )
    
    agent = QueryUnderstandingAgent(llm_config=config)
    
    print("=" * 60)
    print("Query Understanding Agent (with LLM)")
    print("=" * 60)
    
    response = await agent.analyze(SAMPLE_FINGERPRINT)
    
    print(f"\n✓ Success: {response.success}")
    print(f"✓ Summary: {response.summary}")
    print(f"\n--- Explanation ---\n{response.explanation}")
    print(f"\n--- Key Findings ---")
    for finding in response.key_findings:
        print(f"  • {finding}")
    print(f"\n✓ Confidence: {response.confidence}")
    print(f"✓ Processing time: {response.processing_time_ms}ms")
    
    return response


async def run_without_llm():
    """Run query understanding without LLM (rule-based only)."""
    agent = QueryUnderstandingAgent()
    
    print("=" * 60)
    print("Query Understanding Agent (without LLM)")
    print("=" * 60)
    
    response = await agent.analyze_without_llm(SAMPLE_FINGERPRINT)
    
    print(f"\n✓ Success: {response.success}")
    print(f"✓ Summary: {response.summary}")
    print(f"\n--- Explanation ---\n{response.explanation}")
    print(f"\n--- Key Findings ---")
    for finding in response.key_findings:
        print(f"  • {finding}")
    print(f"\n✓ Confidence: {response.confidence}")
    
    return response


async def main():
    """Run examples."""
    # Always run the non-LLM version
    await run_without_llm()
    
    # Only run LLM version if API key is available
    if os.environ.get("OPENAI_API_KEY"):
        print("\n")
        await run_with_llm()
    else:
        print("\n[Skipping LLM example - set OPENAI_API_KEY to enable]")


if __name__ == "__main__":
    asyncio.run(main())
