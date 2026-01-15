"""
Spark Execution Fingerprint (v3)

Main entry point and public API.
"""

from src.fingerprint import (
    ExecutionFingerprintGenerator,
    generate_fingerprint,
)
from src.schemas import ExecutionFingerprint

__version__ = "3.0.0"
__all__ = [
    "ExecutionFingerprintGenerator",
    "generate_fingerprint",
    "ExecutionFingerprint",
]
