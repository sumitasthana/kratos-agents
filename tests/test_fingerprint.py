"""
Test: Basic fingerprint generation
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src import ExecutionFingerprintGenerator
from tests.generate_sample_log import generate_sample_event_log


def test_fingerprint_generation():
    """Test complete fingerprint generation."""
    # Generate sample event log
    log_path = "data/test_event_log.json"
    generate_sample_event_log(log_path, num_stages=3, tasks_per_stage=50)

    # Generate fingerprint
    print("\n=== Generating Fingerprint ===")
    gen = ExecutionFingerprintGenerator(log_path)
    fingerprint = gen.generate()

    # Verify structure
    print("\n=== Verification ===")
    print(f"✓ Semantic Hash: {fingerprint.semantic.semantic_hash[:16]}...")
    print(f"✓ Total Stages: {fingerprint.semantic.dag.total_stages}")
    print(f"✓ Total Tasks: {fingerprint.metrics.execution_summary.total_tasks}")
    print(f"✓ Execution Class: {fingerprint.execution_class}")

    # Print description
    print("\n=== High-Level Summary ===")
    print(f"Semantic: {fingerprint.semantic.description}")
    print(f"Context: {fingerprint.context.description}")
    print(f"Metrics: {fingerprint.metrics.description}")

    # Print anomalies
    if fingerprint.metrics.anomalies:
        print("\n=== Anomalies ===")
        for anomaly in fingerprint.metrics.anomalies:
            print(f"  {anomaly.anomaly_type} ({anomaly.severity}): {anomaly.description}")

    return fingerprint


def test_output_formats():
    """Test different output formats."""
    from src.formatter import FingerprintFormatter

    # Generate fingerprint
    log_path = "data/test_event_log.json"
    gen = ExecutionFingerprintGenerator(log_path)
    fingerprint = gen.generate()

    # JSON
    print("\n=== JSON Output ===")
    json_output = FingerprintFormatter.to_json(fingerprint, pretty=False)
    print(f"Length: {len(json_output)} chars")
    FingerprintFormatter.save_json(fingerprint, "data/fingerprint.json")
    print("✓ Saved: data/fingerprint.json")

    # Markdown
    print("\n=== Markdown Output ===")
    md_output = FingerprintFormatter.to_markdown(fingerprint)
    print(f"Length: {len(md_output)} chars")
    FingerprintFormatter.save_markdown(fingerprint, "data/fingerprint.md")
    print("✓ Saved: data/fingerprint.md")

    # YAML (if available)
    try:
        print("\n=== YAML Output ===")
        yaml_output = FingerprintFormatter.to_yaml(fingerprint)
        print(f"Length: {len(yaml_output)} chars")
        FingerprintFormatter.save_yaml(fingerprint, "data/fingerprint.yaml")
        print("✓ Saved: data/fingerprint.yaml")
    except ImportError:
        print("⊘ YAML not available (install pyyaml)")


if __name__ == "__main__":
    test_fingerprint_generation()
    test_output_formats()
    print("\n✓ All tests passed!")
