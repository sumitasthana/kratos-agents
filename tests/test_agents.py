"""
Tests for Spark fingerprint analysis agents.
"""

import pytest
import pytest_asyncio
from datetime import datetime

pytestmark = pytest.mark.asyncio(loop_scope="function")

from src.agents.base import AgentType, AgentResponse, LLMConfig, BaseAgent
from src.agents.query_understanding import QueryUnderstandingAgent


# Sample fingerprint for testing
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
            "plan_text": "Aggregate -> Join -> Scan",
            "is_sql": True
        }
    }
}


class TestAgentResponse:
    """Tests for AgentResponse model."""
    
    def test_create_response(self):
        response = AgentResponse(
            agent_type=AgentType.QUERY_UNDERSTANDING,
            agent_name="Test Agent",
            success=True,
            summary="Test summary",
            explanation="Test explanation"
        )
        assert response.success is True
        assert response.agent_type == AgentType.QUERY_UNDERSTANDING
        assert response.confidence == 1.0  # default
    
    def test_response_with_findings(self):
        response = AgentResponse(
            agent_type=AgentType.QUERY_UNDERSTANDING,
            agent_name="Test Agent",
            success=True,
            summary="Test",
            explanation="Test",
            key_findings=["Finding 1", "Finding 2"],
            confidence=0.85
        )
        assert len(response.key_findings) == 2
        assert response.confidence == 0.85


class TestLLMConfig:
    """Tests for LLM configuration."""
    
    def test_default_config(self):
        config = LLMConfig()
        assert config.provider == "openai"
        assert config.model == "gpt-4.1"
        assert config.temperature == 0.2
    
    def test_custom_config(self):
        config = LLMConfig(
            provider="anthropic",
            model="claude-3-sonnet-20240229",
            temperature=0.5
        )
        assert config.provider == "anthropic"
        assert config.model == "claude-3-sonnet-20240229"


class TestQueryUnderstandingAgent:
    """Tests for Query Understanding Agent."""
    
    def test_agent_properties(self):
        agent = QueryUnderstandingAgent()
        assert agent.agent_type == AgentType.QUERY_UNDERSTANDING
        assert agent.agent_name == "Query Understanding Agent"
        assert "explain" in agent.description.lower()
    
    def test_extract_semantic_full_fingerprint(self):
        agent = QueryUnderstandingAgent()
        semantic = agent._extract_semantic(SAMPLE_FINGERPRINT)
        assert semantic is not None
        assert "dag" in semantic
        assert semantic["semantic_hash"] == "a1b2c3d4e5f6789"
    
    def test_extract_semantic_semantic_only(self):
        agent = QueryUnderstandingAgent()
        semantic_only = SAMPLE_FINGERPRINT["semantic"]
        result = agent._extract_semantic(semantic_only)
        assert result is not None
        assert "dag" in result
    
    def test_extract_semantic_missing(self):
        agent = QueryUnderstandingAgent()
        result = agent._extract_semantic({"metrics": {}})
        assert result is None
    
    def test_build_context(self):
        agent = QueryUnderstandingAgent()
        semantic = SAMPLE_FINGERPRINT["semantic"]
        context = agent._build_context(semantic, include_dag=True, include_plan=True)
        
        assert "dag" in context
        assert context["dag"]["total_stages"] == 4
        assert len(context["dag"]["stages"]) == 4
    
    def test_summarize_stages(self):
        agent = QueryUnderstandingAgent()
        stages = SAMPLE_FINGERPRINT["semantic"]["dag"]["stages"]
        summaries = agent._summarize_stages(stages)
        
        assert len(summaries) == 4
        assert summaries[0]["id"] == 0
        assert summaries[2]["is_shuffle"] is True
    
    def test_build_user_prompt(self):
        agent = QueryUnderstandingAgent()
        semantic = SAMPLE_FINGERPRINT["semantic"]
        context = agent._build_context(semantic, include_dag=True, include_plan=False)
        prompt = agent._build_user_prompt(context)
        
        assert "Stage 0" in prompt
        assert "Stage 2" in prompt
        assert "SHUFFLE" in prompt
        assert "join key shuffle" in prompt
    
    @pytest.mark.asyncio
    async def test_analyze_without_llm(self):
        agent = QueryUnderstandingAgent()
        response = await agent.analyze_without_llm(SAMPLE_FINGERPRINT)
        
        assert response.success is True
        assert response.agent_type == AgentType.QUERY_UNDERSTANDING
        assert "shuffle" in response.explanation.lower() or len(response.key_findings) > 0
        assert response.confidence < 1.0  # Lower confidence without LLM
    
    @pytest.mark.asyncio
    async def test_analyze_without_llm_missing_data(self):
        agent = QueryUnderstandingAgent()
        response = await agent.analyze_without_llm({"metrics": {}})
        
        assert response.success is False
        assert response.error is not None
    
    def test_parse_llm_response(self):
        agent = QueryUnderstandingAgent()
        import time
        
        llm_response = """**Summary**: This query joins orders with users and aggregates by region.

**Data Flow**:
- Stage 0 scans the orders table
- Stage 1 scans the users table
- Stage 2 performs a hash join
- Stage 3 aggregates results

**Key Operations**:
- ShuffledHashJoin on user_id
- HashAggregate by region
"""
        
        response = agent._parse_llm_response(llm_response, time.time())
        
        assert response.success is True
        assert "joins orders" in response.summary.lower()
        assert len(response.key_findings) > 0


class TestAgentIntegration:
    """Integration tests for agent system."""
    
    @pytest.mark.asyncio
    async def test_full_workflow_without_llm(self):
        """Test complete workflow without LLM dependency."""
        agent = QueryUnderstandingAgent()
        
        # Analyze
        response = await agent.analyze_without_llm(SAMPLE_FINGERPRINT)
        
        # Verify response structure
        assert isinstance(response, AgentResponse)
        assert response.agent_type == AgentType.QUERY_UNDERSTANDING
        assert response.timestamp is not None
        assert response.processing_time_ms is not None
        assert response.processing_time_ms >= 0
