# """
# Context Fingerprint Generator

# Extracts environment, Spark version, executor config, and runtime settings.
# """

# from datetime import datetime
# from typing import Any, Dict, List, Optional

# from src.schemas import (
#     ContextFingerprint,
#     ExecutorConfig,
#     SubmitParameters,
#     SparkConfig,
# )
# from src.parser import EventLogParser, EventIndex


# class ContextFingerprintGenerator:
#     """
#     Generates context fingerprint (environment + configuration) from event log.
#     Used for environment drift analysis and explaining performance differences.
#     """

#     def __init__(self, event_log_path: str):
#         self.event_log_path = event_log_path
#         self.parser = EventLogParser(event_log_path)
#         self.events, self.metadata = self.parser.parse()
#         self.index = EventIndex(self.events)

#     def generate(self) -> ContextFingerprint:
#         """
#         Generate complete context fingerprint from event log.

#         Returns:
#             ContextFingerprint with environment, config, and metadata
#         """
#         # Extract Spark configuration
#         spark_config = self._extract_spark_config()

#         # Extract executor configuration
#         executor_config = self._extract_executor_config()

#         # Extract submission parameters
#         submit_params = self._extract_submit_parameters()

#         # Extract JVM settings
#         jvm_settings = self._extract_jvm_settings()

#         # Detect enabled optimizations
#         optimizations = self._detect_optimizations()

#         # Generate description
#         description = self._generate_description(spark_config, executor_config, optimizations)

#         # Collect evidence
#         evidence = self._collect_evidence()

#         return ContextFingerprint(
#             spark_config=spark_config,
#             executor_config=executor_config,
#             submit_params=submit_params,
#             jvm_settings=jvm_settings,
#             optimizations_enabled=optimizations,
#             description=description,
#             evidence_sources=evidence,
#         )

#     def _extract_spark_config(self) -> SparkConfig:
#         """Extract Spark version and critical configuration."""
#         app_start_events = self.index.get_by_type("SparkListenerApplicationStart")
#         if not app_start_events:
#             raise ValueError("No SparkListenerApplicationStart event found")

#         app_start = app_start_events[0]

#         app_name = app_start.get("App Name", "unknown")
#         spark_version = app_start.get("Spark Version", "unknown")
#         app_id = self.metadata.get("app_id", "unknown")

#         # Get master URL
#         master_url = self._infer_master_url(app_start)

#         # Extract important config params
#         config_params = self._extract_config_params()

#         # Get version info
#         scala_version = config_params.pop("scala.version", None)
#         java_version = config_params.pop("java.version", None)
#         hadoop_version = config_params.pop("hadoop.version", None)

#         return SparkConfig(
#             spark_version=spark_version,
#             scala_version=scala_version,
#             java_version=java_version,
#             hadoop_version=hadoop_version,
#             app_name=app_name,
#             master_url=master_url,
#             config_params=config_params,
#             description=f"Spark {spark_version} application: {app_name}",
#         )

#     def _extract_executor_config(self) -> ExecutorConfig:
#         """Extract executor resource allocation."""
#         block_manager_events = self.index.get_by_type("SparkListenerBlockManagerAdded")

#         executor_count = 0
#         executor_memory_mb = 0
#         executor_cores = 1

#         # Count unique executors (excluding driver)
#         executor_ids = set()
#         for event in block_manager_events:
#             executor_id = event.get("Executor ID", "driver")
#             if executor_id != "driver":
#                 executor_ids.add(executor_id)
#                 # Try to extract memory from event
#                 mem = event.get("Max Mem", 0)
#                 if mem > 0:
#                     executor_memory_mb = mem // (1024 * 1024)

#         executor_count = len(executor_ids)

#         # Get driver config
#         driver_memory_mb = 0
#         driver_cores = 1
#         for event in block_manager_events:
#             if event.get("Executor ID") == "driver":
#                 driver_memory_mb = event.get("Max Mem", 0) // (1024 * 1024)

#         # Fallback: extract from config params
#         config_params = self._extract_config_params()
#         if not executor_memory_mb:
#             executor_memory_mb = self._parse_memory_param(
#                 config_params.get("spark.executor.memory", "1g")
#             )
#         if not driver_memory_mb:
#             driver_memory_mb = self._parse_memory_param(
#                 config_params.get("spark.driver.memory", "1g")
#             )

#         executor_cores = int(config_params.get("spark.executor.cores", "1"))
#         driver_cores = int(config_params.get("spark.driver.cores", "1"))

#         description = f"{executor_count} executors × {executor_memory_mb}MB × {executor_cores} cores each; Driver: {driver_memory_mb}MB × {driver_cores} cores"

#         return ExecutorConfig(
#             total_executors=executor_count or 2,  # Default if not detected
#             executor_memory_mb=executor_memory_mb or 1024,
#             executor_cores=executor_cores,
#             driver_memory_mb=driver_memory_mb or 1024,
#             driver_cores=driver_cores,
#             description=description,
#         )

#     def _extract_submit_parameters(self) -> SubmitParameters:
#         """Extract application submission parameters."""
#         app_start_events = self.index.get_by_type("SparkListenerApplicationStart")
#         if not app_start_events:
#             raise ValueError("No SparkListenerApplicationStart event found")

#         app_start = app_start_events[0]

#         submit_time_ms = app_start.get("Timestamp", 0)
#         submit_time = datetime.fromtimestamp(submit_time_ms / 1000.0) if submit_time_ms else datetime.now()

#         user = app_start.get("User", None)
#         app_id = self.metadata.get("app_id", "unknown")
#         queue = None  # May not be available in event logs

#         return SubmitParameters(
#             submit_time=submit_time,
#             user=user,
#             app_id=app_id,
#             queue=queue,
#             additional_params={},
#         )

#     def _extract_jvm_settings(self) -> Dict[str, str]:
#         """Extract JVM-relevant settings from config."""
#         config_params = self._extract_config_params()

#         # Filter for JVM-related settings
#         jvm_keys = [
#             "spark.executor.extraJavaOptions",
#             "spark.driver.extraJavaOptions",
#             "spark.memory.fraction",
#             "spark.memory.storageFraction",
#             "spark.serializer",
#             "spark.io.compression.codec",
#         ]

#         jvm_settings = {}
#         for key in jvm_keys:
#             if key in config_params:
#                 jvm_settings[key] = config_params[key]

#         return jvm_settings

#     def _detect_optimizations(self) -> List[str]:
#         """Detect performance optimizations that are enabled."""
#         config_params = self._extract_config_params()
#         optimizations = []

#         # Adaptive Query Execution
#         if config_params.get("spark.sql.adaptive.enabled", "false").lower() == "true":
#             optimizations.append("AdaptiveQueryExecution")

#         # Columnar execution
#         if config_params.get("spark.sql.execution.columnar", "false").lower() == "true":
#             optimizations.append("ColumnarExecution")

#         # Whole stage codegen
#         if config_params.get("spark.sql.codegen.wholeStage", "true").lower() == "true":
#             optimizations.append("WholeStageCodegen")

#         # Dynamic partition pruning
#         if config_params.get("spark.sql.optimizer.dynamicPartitionPruning.enabled", "false").lower() == "true":
#             optimizations.append("DynamicPartitionPruning")

#         # Broadcast join threshold
#         broadcast_threshold = config_params.get("spark.sql.autoBroadcastJoinThreshold")
#         if broadcast_threshold and int(broadcast_threshold) > 0:
#             optimizations.append("BroadcastJoin")

#         return optimizations

#     def _extract_config_params(self) -> Dict[str, str]:
#         """Extract Spark configuration parameters from environment event."""
#         env_events = self.index.get_by_type("SparkListenerEnvironmentUpdate")

#         config_params = {}
#         if env_events:
#             env_update = env_events[0]
#             spark_properties = env_update.get("Spark Properties", [])
#             for key, value in spark_properties.items():
#             # for key, value in spark_properties:
#                 config_params[key] = str(value)

#         return config_params

#     def _infer_master_url(self, app_start: Any) -> str:
#         """Infer Spark master from submission or context."""
#         # This info might be in properties
#         return "unknown"  # Would need additional parsing from properties

#     def _parse_memory_param(self, param: str) -> int:
#         """Parse memory parameter (e.g., '4g' -> 4096 MB)."""
#         param = str(param).lower().strip()

#         multipliers = {"k": 1 / 1024, "m": 1, "g": 1024, "t": 1024 * 1024}

#         for unit, multiplier in multipliers.items():
#             if param.endswith(unit):
#                 try:
#                     value = float(param[:-1]) * multiplier
#                     return int(value)
#                 except ValueError:
#                     pass

#         # Try parsing as plain MB
#         try:
#             return int(float(param))
#         except ValueError:
#             return 1024  # Default

#     def _generate_description(
#         self, spark_config: SparkConfig, executor_config: ExecutorConfig, optimizations: List[str]
#     ) -> str:
#         """Generate natural language description of context."""
#         parts = [
#             f"Spark {spark_config.spark_version}",
#             f"{executor_config.total_executors} executors",
#             f"{executor_config.executor_memory_mb}MB per executor",
#         ]

#         if optimizations:
#             parts.append(f"Optimizations: {', '.join(optimizations)}")

#         return "; ".join(parts)

#     def _collect_evidence(self) -> List[str]:
#         """Collect event IDs supporting context fingerprint."""
#         evidence = []

#         # Reference to ApplicationStart
#         if self.index.get_by_type("SparkListenerApplicationStart"):
#             evidence.append("ApplicationStart")

#         # Reference to EnvironmentUpdate
#         if self.index.get_by_type("SparkListenerEnvironmentUpdate"):
#             evidence.append("EnvironmentUpdate")

#         # Reference to BlockManagerAdded (executor info)
#         bm_events = self.index.get_by_type("SparkListenerBlockManagerAdded")
#         if bm_events:
#             evidence.append(f"BlockManagerAdded({len(bm_events)} events)")

#         return evidence
"""
Context Fingerprint Generator

Extracts environment, Spark version, executor config, and runtime settings.

Enhanced with GRC compliance tracking and root cause analysis context.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

from src.schemas import (
    ContextFingerprint,
    ExecutorConfig,
    SubmitParameters,
    SparkConfig,
)
from src.parser import EventLogParser, EventIndex

logger = logging.getLogger(__name__)


class ContextFingerprintGenerator:
    """
    Generates context fingerprint (environment + configuration) from event log.
    Used for environment drift analysis and explaining performance differences.
    
    Enhanced with GRC compliance tracking for regulatory reporting.
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
        try:
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

            # NEW: Detect compliance-relevant settings
            compliance_context = self._extract_compliance_context()

            # Generate description
            description = self._generate_description(
                spark_config, executor_config, optimizations
            )

            # Collect evidence
            evidence = self._collect_evidence()

            # Create base fingerprint
            fingerprint = ContextFingerprint(
                spark_config=spark_config,
                executor_config=executor_config,
                submit_params=submit_params,
                jvm_settings=jvm_settings,
                optimizations_enabled=optimizations,
                description=description,
                evidence_sources=evidence,
            )
            
            # NEW: Add compliance context if available
            if compliance_context:
                fingerprint.compliance_context = compliance_context

            return fingerprint

        except Exception as e:
            logger.exception(f"Error generating context fingerprint: {e}")
            raise

    def _extract_spark_config(self) -> SparkConfig:
        """Extract Spark version and critical configuration."""
        app_start_events = self.index.get_by_type("SparkListenerApplicationStart")
        if not app_start_events:
            logger.warning("No SparkListenerApplicationStart event found")
            raise ValueError("No SparkListenerApplicationStart event found")

        app_start = app_start_events[0]

        app_name = app_start.get("App Name", "unknown")
        spark_version = app_start.get("Spark Version", "unknown")
        app_id = self.metadata.get("app_id", "unknown")

        logger.info(f"Extracted Spark config: {spark_version}, app={app_name}")

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

        # Extract cores
        try:
            executor_cores = int(config_params.get("spark.executor.cores", "1"))
            driver_cores = int(config_params.get("spark.driver.cores", "1"))
        except (ValueError, TypeError):
            executor_cores = 1
            driver_cores = 1
            logger.warning("Failed to parse executor/driver cores, using defaults")

        description = (
            f"{executor_count} executors × {executor_memory_mb}MB × {executor_cores} cores each; "
            f"Driver: {driver_memory_mb}MB × {driver_cores} cores"
        )

        logger.info(f"Extracted executor config: {description}")

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
            logger.warning("No SparkListenerApplicationStart event found")
            raise ValueError("No SparkListenerApplicationStart event found")

        app_start = app_start_events[0]

        submit_time_ms = app_start.get("Timestamp", 0)
        submit_time = (
            datetime.fromtimestamp(submit_time_ms / 1000.0)
            if submit_time_ms
            else datetime.now()
        )

        user = app_start.get("User", None)
        app_id = self.metadata.get("app_id", "unknown")
        
        # Try to extract queue from config
        config_params = self._extract_config_params()
        queue = config_params.get("spark.yarn.queue") or config_params.get("spark.scheduler.pool")

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
            "spark.rdd.compress",
            "spark.shuffle.compress",
            "spark.shuffle.spill.compress",
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

        # Adaptive Query Execution (AQE)
        if self._is_config_enabled(config_params, "spark.sql.adaptive.enabled"):
            optimizations.append("AdaptiveQueryExecution")

        # Columnar execution
        if self._is_config_enabled(config_params, "spark.sql.execution.columnar"):
            optimizations.append("ColumnarExecution")

        # Whole stage codegen
        if self._is_config_enabled(config_params, "spark.sql.codegen.wholeStage", default_true=True):
            optimizations.append("WholeStageCodegen")

        # Dynamic partition pruning
        if self._is_config_enabled(config_params, "spark.sql.optimizer.dynamicPartitionPruning.enabled"):
            optimizations.append("DynamicPartitionPruning")

        # Broadcast join
        broadcast_threshold = config_params.get("spark.sql.autoBroadcastJoinThreshold", "10485760")
        try:
            if int(broadcast_threshold) > 0:
                optimizations.append("BroadcastJoin")
        except (ValueError, TypeError):
            pass

        # Cost-based optimization
        if self._is_config_enabled(config_params, "spark.sql.cbo.enabled"):
            optimizations.append("CostBasedOptimization")

        # Bucketing
        if self._is_config_enabled(config_params, "spark.sql.sources.bucketing.enabled", default_true=True):
            optimizations.append("Bucketing")

        logger.info(f"Detected {len(optimizations)} optimizations: {', '.join(optimizations)}")

        return optimizations

    def _is_config_enabled(
        self, config_params: Dict[str, str], key: str, default_true: bool = False
    ) -> bool:
        """Check if a config parameter is enabled."""
        value = config_params.get(key, "true" if default_true else "false")
        return str(value).lower() == "true"

    def _extract_config_params(self) -> Dict[str, str]:
        """Extract Spark configuration parameters from environment event."""
        env_events = self.index.get_by_type("SparkListenerEnvironmentUpdate")

        config_params = {}
        if env_events:
            env_update = env_events[0]
            spark_properties = env_update.get("Spark Properties", {})
            
            # Handle both dict and list of tuples
            if isinstance(spark_properties, dict):
                for key, value in spark_properties.items():
                    config_params[key] = str(value)
            elif isinstance(spark_properties, list):
                for item in spark_properties:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        key, value = item
                        config_params[key] = str(value)
            else:
                logger.warning(f"Unexpected Spark Properties format: {type(spark_properties)}")

        logger.info(f"Extracted {len(config_params)} config parameters")
        return config_params

    def _infer_master_url(self, app_start: Dict[str, Any]) -> str:
        """Infer Spark master from submission or context."""
        config_params = self._extract_config_params()
        
        # Try to extract from common config keys
        master = config_params.get("spark.master")
        if master:
            return master
        
        # Check for YARN/K8s indicators
        if "spark.yarn.am.memory" in config_params:
            return "yarn"
        elif "spark.kubernetes.namespace" in config_params:
            return "k8s"
        elif "spark.mesos.coarse" in config_params:
            return "mesos"
        
        return "unknown"

    def _parse_memory_param(self, param: str) -> int:
        """
        Parse memory parameter (e.g., '4g' -> 4096 MB).
        
        Supports: k, m, g, t suffixes
        """
        if not param:
            return 1024

        param = str(param).lower().strip()

        # Remove common suffixes like 'b' for bytes
        if param.endswith("b") and len(param) > 1 and param[-2] in "kmgt":
            param = param[:-1]

        multipliers = {
            "k": 1 / 1024,      # KB to MB
            "m": 1,             # MB
            "g": 1024,          # GB to MB
            "t": 1024 * 1024,   # TB to MB
        }

        for unit, multiplier in multipliers.items():
            if param.endswith(unit):
                try:
                    value = float(param[:-1]) * multiplier
                    return max(int(value), 256)  # Minimum 256MB
                except (ValueError, TypeError):
                    logger.warning(f"Failed to parse memory param: {param}")
                    pass

        # Try parsing as plain MB
        try:
            return max(int(float(param)), 256)
        except (ValueError, TypeError):
            logger.warning(f"Failed to parse memory param: {param}, using default")
            return 1024  # Default 1GB

    def _generate_description(
        self,
        spark_config: SparkConfig,
        executor_config: ExecutorConfig,
        optimizations: List[str],
    ) -> str:
        """Generate natural language description of context."""
        parts = [
            f"Spark {spark_config.spark_version}",
            f"{executor_config.total_executors} executors",
            f"{executor_config.executor_memory_mb}MB per executor",
        ]

        if optimizations:
            parts.append(f"Optimizations: {', '.join(optimizations[:3])}")
            if len(optimizations) > 3:
                parts.append(f"(+{len(optimizations) - 3} more)")

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

    # ========================================================================
    # NEW: GRC Compliance Context Extraction
    # ========================================================================

    def _extract_compliance_context(self) -> Optional[Dict[str, Any]]:
        """
        Extract GRC compliance-relevant context.
        
        Returns metadata useful for regulatory reporting and incident analysis.
        """
        config_params = self._extract_config_params()
        
        compliance = {}
        
        # Environment type detection
        compliance["environment_type"] = self._detect_environment_type(config_params)
        
        # Data sensitivity indicators
        compliance["encryption_enabled"] = self._check_encryption_enabled(config_params)
        
        # Audit trail settings
        compliance["event_logging_enabled"] = self._check_event_logging(config_params)
        
        # Resource quotas (for capacity planning compliance)
        compliance["resource_limits"] = self._extract_resource_limits(config_params)
        
        # Dynamic allocation (affects capacity compliance)
        compliance["dynamic_allocation_enabled"] = self._is_config_enabled(
            config_params, "spark.dynamicAllocation.enabled"
        )
        
        # Checkpointing (data integrity)
        compliance["checkpoint_enabled"] = self._check_checkpointing(config_params)
        
        # Data quality settings
        compliance["data_validation"] = self._check_data_validation(config_params)
        
        logger.info(f"Extracted compliance context: {compliance}")
        
        return compliance if any(compliance.values()) else None

    def _detect_environment_type(self, config_params: Dict[str, str]) -> str:
        """Detect whether this is prod/staging/dev."""
        app_name = config_params.get("spark.app.name", "").lower()
        
        if "prod" in app_name or "production" in app_name:
            return "production"
        elif "stag" in app_name or "uat" in app_name:
            return "staging"
        elif "dev" in app_name or "test" in app_name:
            return "development"
        
        # Check queue name
        queue = config_params.get("spark.yarn.queue", "").lower()
        if "prod" in queue:
            return "production"
        elif "dev" in queue:
            return "development"
        
        return "unknown"

    def _check_encryption_enabled(self, config_params: Dict[str, str]) -> bool:
        """Check if encryption is enabled."""
        encryption_keys = [
            "spark.ssl.enabled",
            "spark.io.encryption.enabled",
            "spark.network.crypto.enabled",
        ]
        
        for key in encryption_keys:
            if self._is_config_enabled(config_params, key):
                return True
        
        return False

    def _check_event_logging(self, config_params: Dict[str, str]) -> bool:
        """Check if event logging is enabled for audit trails."""
        return self._is_config_enabled(config_params, "spark.eventLog.enabled")

    def _extract_resource_limits(self, config_params: Dict[str, str]) -> Dict[str, Any]:
        """Extract resource limits for capacity compliance."""
        limits = {}
        
        # Dynamic allocation limits
        if self._is_config_enabled(config_params, "spark.dynamicAllocation.enabled"):
            limits["min_executors"] = int(
                config_params.get("spark.dynamicAllocation.minExecutors", "0")
            )
            limits["max_executors"] = int(
                config_params.get("spark.dynamicAllocation.maxExecutors", "infinity")
            )
        
        # Memory overhead
        overhead = config_params.get("spark.executor.memoryOverhead")
        if overhead:
            limits["memory_overhead_mb"] = self._parse_memory_param(overhead)
        
        return limits

    def _check_checkpointing(self, config_params: Dict[str, str]) -> bool:
        """Check if checkpointing is configured (data integrity)."""
        checkpoint_dir = config_params.get("spark.checkpoint.dir")
        return bool(checkpoint_dir)

    def _check_data_validation(self, config_params: Dict[str, str]) -> Dict[str, bool]:
        """Check data quality/validation settings."""
        return {
            "null_check_enabled": self._is_config_enabled(
                config_params, "spark.sql.ansi.enabled"
            ),
            "type_coercion_strict": self._is_config_enabled(
                config_params, "spark.sql.storeAssignmentPolicy", default_true=False
            ),
        }

    # ========================================================================
    # NEW: Resource Adequacy Analysis (for RCA)
    # ========================================================================

    def analyze_resource_adequacy(
        self, executor_config: ExecutorConfig, workload_size_gb: float
    ) -> Dict[str, Any]:
        """
        Analyze if executor configuration is adequate for workload.
        
        Useful for root cause analysis of memory spills and OOM errors.
        """
        total_memory_mb = (
            executor_config.total_executors * executor_config.executor_memory_mb
        )
        total_memory_gb = total_memory_mb / 1024
        
        total_cores = executor_config.total_executors * executor_config.executor_cores
        
        # Rule of thumb: need ~3x workload size in total executor memory
        recommended_memory_gb = workload_size_gb * 3
        memory_adequate = total_memory_gb >= recommended_memory_gb
        
        # Parallelism check: should have at least 2 cores per GB of data
        recommended_cores = int(workload_size_gb * 2)
        cores_adequate = total_cores >= recommended_cores
        
        return {
            "total_memory_gb": round(total_memory_gb, 2),
            "total_cores": total_cores,
            "workload_size_gb": workload_size_gb,
            "memory_adequate": memory_adequate,
            "memory_ratio": round(total_memory_gb / workload_size_gb, 2) if workload_size_gb > 0 else 0,
            "cores_adequate": cores_adequate,
            "recommended_memory_gb": round(recommended_memory_gb, 2),
            "recommended_cores": recommended_cores,
        }
