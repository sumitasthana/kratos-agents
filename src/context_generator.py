"""
Context Fingerprint Generator

Extracts environment, Spark version, executor config, and runtime settings.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.schemas import (
    ContextFingerprint,
    ExecutorConfig,
    SubmitParameters,
    SparkConfig,
)
from src.parser import EventLogParser, EventIndex


class ContextFingerprintGenerator:
    """
    Generates context fingerprint (environment + configuration) from event log.
    Used for environment drift analysis and explaining performance differences.
    """

    def __init__(self, event_log_path: str):
        self.event_log_path = event_log_path
        self.parser = EventLogParser(event_log_path)
        self.events, self.metadata = self.parser.parse()
        self.index = EventIndex(self.events)

    def generate(self) -> ContextFingerprint:
        """
        Generate complete context fingerprint from event log.

        Returns:
            ContextFingerprint with environment, config, and metadata
        """
        # Extract Spark configuration
        spark_config = self._extract_spark_config()

        # Extract executor configuration
        executor_config = self._extract_executor_config()

        # Extract submission parameters
        submit_params = self._extract_submit_parameters()

        # Extract JVM settings
        jvm_settings = self._extract_jvm_settings()

        # Detect enabled optimizations
        optimizations = self._detect_optimizations()

        # Generate description
        description = self._generate_description(spark_config, executor_config, optimizations)

        # Collect evidence
        evidence = self._collect_evidence()

        return ContextFingerprint(
            spark_config=spark_config,
            executor_config=executor_config,
            submit_params=submit_params,
            jvm_settings=jvm_settings,
            optimizations_enabled=optimizations,
            description=description,
            evidence_sources=evidence,
        )

    def _extract_spark_config(self) -> SparkConfig:
        """Extract Spark version and critical configuration."""
        app_start_events = self.index.get_by_type("SparkListenerApplicationStart")
        if not app_start_events:
            raise ValueError("No SparkListenerApplicationStart event found")

        app_start = app_start_events[0]

        app_name = app_start.get("App Name", "unknown")
        spark_version = app_start.get("Spark Version", "unknown")
        app_id = self.metadata.get("app_id", "unknown")

        # Get master URL
        master_url = self._infer_master_url(app_start)

        # Extract important config params
        config_params = self._extract_config_params()

        # Get version info
        scala_version = config_params.pop("scala.version", None)
        java_version = config_params.pop("java.version", None)
        hadoop_version = config_params.pop("hadoop.version", None)

        return SparkConfig(
            spark_version=spark_version,
            scala_version=scala_version,
            java_version=java_version,
            hadoop_version=hadoop_version,
            app_name=app_name,
            master_url=master_url,
            config_params=config_params,
            description=f"Spark {spark_version} application: {app_name}",
        )

    def _extract_executor_config(self) -> ExecutorConfig:
        """Extract executor resource allocation."""
        block_manager_events = self.index.get_by_type("SparkListenerBlockManagerAdded")

        executor_count = 0
        executor_memory_mb = 0
        executor_cores = 1

        # Count unique executors (excluding driver)
        executor_ids = set()
        for event in block_manager_events:
            executor_id = event.get("Executor ID", "driver")
            if executor_id != "driver":
                executor_ids.add(executor_id)
                # Try to extract memory from event
                mem = event.get("Max Mem", 0)
                if mem > 0:
                    executor_memory_mb = mem // (1024 * 1024)

        executor_count = len(executor_ids)

        # Get driver config
        driver_memory_mb = 0
        driver_cores = 1
        for event in block_manager_events:
            if event.get("Executor ID") == "driver":
                driver_memory_mb = event.get("Max Mem", 0) // (1024 * 1024)

        # Fallback: extract from config params
        config_params = self._extract_config_params()
        if not executor_memory_mb:
            executor_memory_mb = self._parse_memory_param(
                config_params.get("spark.executor.memory", "1g")
            )
        if not driver_memory_mb:
            driver_memory_mb = self._parse_memory_param(
                config_params.get("spark.driver.memory", "1g")
            )

        executor_cores = int(config_params.get("spark.executor.cores", "1"))
        driver_cores = int(config_params.get("spark.driver.cores", "1"))

        description = f"{executor_count} executors × {executor_memory_mb}MB × {executor_cores} cores each; Driver: {driver_memory_mb}MB × {driver_cores} cores"

        return ExecutorConfig(
            total_executors=executor_count or 2,  # Default if not detected
            executor_memory_mb=executor_memory_mb or 1024,
            executor_cores=executor_cores,
            driver_memory_mb=driver_memory_mb or 1024,
            driver_cores=driver_cores,
            description=description,
        )

    def _extract_submit_parameters(self) -> SubmitParameters:
        """Extract application submission parameters."""
        app_start_events = self.index.get_by_type("SparkListenerApplicationStart")
        if not app_start_events:
            raise ValueError("No SparkListenerApplicationStart event found")

        app_start = app_start_events[0]

        submit_time_ms = app_start.get("Timestamp", 0)
        submit_time = datetime.fromtimestamp(submit_time_ms / 1000.0) if submit_time_ms else datetime.now()

        user = app_start.get("User", None)
        app_id = self.metadata.get("app_id", "unknown")
        queue = None  # May not be available in event logs

        return SubmitParameters(
            submit_time=submit_time,
            user=user,
            app_id=app_id,
            queue=queue,
            additional_params={},
        )

    def _extract_jvm_settings(self) -> Dict[str, str]:
        """Extract JVM-relevant settings from config."""
        config_params = self._extract_config_params()

        # Filter for JVM-related settings
        jvm_keys = [
            "spark.executor.extraJavaOptions",
            "spark.driver.extraJavaOptions",
            "spark.memory.fraction",
            "spark.memory.storageFraction",
            "spark.serializer",
            "spark.io.compression.codec",
        ]

        jvm_settings = {}
        for key in jvm_keys:
            if key in config_params:
                jvm_settings[key] = config_params[key]

        return jvm_settings

    def _detect_optimizations(self) -> List[str]:
        """Detect performance optimizations that are enabled."""
        config_params = self._extract_config_params()
        optimizations = []

        # Adaptive Query Execution
        if config_params.get("spark.sql.adaptive.enabled", "false").lower() == "true":
            optimizations.append("AdaptiveQueryExecution")

        # Columnar execution
        if config_params.get("spark.sql.execution.columnar", "false").lower() == "true":
            optimizations.append("ColumnarExecution")

        # Whole stage codegen
        if config_params.get("spark.sql.codegen.wholeStage", "true").lower() == "true":
            optimizations.append("WholeStageCodegen")

        # Dynamic partition pruning
        if config_params.get("spark.sql.optimizer.dynamicPartitionPruning.enabled", "false").lower() == "true":
            optimizations.append("DynamicPartitionPruning")

        # Broadcast join threshold
        broadcast_threshold = config_params.get("spark.sql.autoBroadcastJoinThreshold")
        if broadcast_threshold and int(broadcast_threshold) > 0:
            optimizations.append("BroadcastJoin")

        return optimizations

    def _extract_config_params(self) -> Dict[str, str]:
        """Extract Spark configuration parameters from environment event."""
        env_events = self.index.get_by_type("SparkListenerEnvironmentUpdate")

        config_params = {}
        if env_events:
            env_update = env_events[0]
            spark_properties = env_update.get("Spark Properties", [])
            for key, value in spark_properties:
                config_params[key] = str(value)

        return config_params

    def _infer_master_url(self, app_start: Any) -> str:
        """Infer Spark master from submission or context."""
        # This info might be in properties
        return "unknown"  # Would need additional parsing from properties

    def _parse_memory_param(self, param: str) -> int:
        """Parse memory parameter (e.g., '4g' -> 4096 MB)."""
        param = str(param).lower().strip()

        multipliers = {"k": 1 / 1024, "m": 1, "g": 1024, "t": 1024 * 1024}

        for unit, multiplier in multipliers.items():
            if param.endswith(unit):
                try:
                    value = float(param[:-1]) * multiplier
                    return int(value)
                except ValueError:
                    pass

        # Try parsing as plain MB
        try:
            return int(float(param))
        except ValueError:
            return 1024  # Default

    def _generate_description(
        self, spark_config: SparkConfig, executor_config: ExecutorConfig, optimizations: List[str]
    ) -> str:
        """Generate natural language description of context."""
        parts = [
            f"Spark {spark_config.spark_version}",
            f"{executor_config.total_executors} executors",
            f"{executor_config.executor_memory_mb}MB per executor",
        ]

        if optimizations:
            parts.append(f"Optimizations: {', '.join(optimizations)}")

        return "; ".join(parts)

    def _collect_evidence(self) -> List[str]:
        """Collect event IDs supporting context fingerprint."""
        evidence = []

        # Reference to ApplicationStart
        if self.index.get_by_type("SparkListenerApplicationStart"):
            evidence.append("ApplicationStart")

        # Reference to EnvironmentUpdate
        if self.index.get_by_type("SparkListenerEnvironmentUpdate"):
            evidence.append("EnvironmentUpdate")

        # Reference to BlockManagerAdded (executor info)
        bm_events = self.index.get_by_type("SparkListenerBlockManagerAdded")
        if bm_events:
            evidence.append(f"BlockManagerAdded({len(bm_events)} events)")

        return evidence
