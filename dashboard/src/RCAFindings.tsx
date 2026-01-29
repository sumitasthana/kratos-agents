import React from "react";

type RCAFindingsProps = {
  orchestratorData: any;
};

export default function RCAFindings({ orchestratorData }: RCAFindingsProps) {
  if (!orchestratorData) {
    return <div style={{ padding: 20, color: "#666" }}>No RCA/Orchestrator data available</div>;
  }

  const summary = orchestratorData.executive_summary || orchestratorData.summary || "";
  const recommendations = orchestratorData.recommendations || [];
  const findings = orchestratorData.key_findings || [];
  const problemType = orchestratorData.problem_type || "unknown";
  const confidence = orchestratorData.confidence || 0;

  return (
    <div style={{ padding: 20, maxWidth: 900 }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
          <div style={{ flex: 1, padding: 16, background: "#f5f5f5", borderRadius: 8 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Problem Type</div>
            <div style={{ fontSize: 18, fontWeight: 700, textTransform: "capitalize" }}>{problemType}</div>
          </div>
          <div style={{ flex: 1, padding: 16, background: "#f5f5f5", borderRadius: 8 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Confidence</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{confidence}%</div>
          </div>
        </div>
      </div>

      {summary && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Executive Summary</div>
          <div
            style={{
              padding: 16,
              background: "#fff",
              border: "1px solid #e5e5e5",
              borderRadius: 8,
              lineHeight: 1.6,
            }}
          >
            {summary}
          </div>
        </div>
      )}

      {findings && findings.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Key Findings</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {findings.map((finding: string, idx: number) => (
              <div
                key={idx}
                style={{
                  padding: 12,
                  background: "#fff",
                  border: "1px solid #e5e5e5",
                  borderRadius: 6,
                  display: "flex",
                  gap: 12,
                }}
              >
                <div style={{ fontWeight: 700, color: "#4a90e2" }}>•</div>
                <div style={{ flex: 1 }}>{finding}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {recommendations && recommendations.length > 0 && (
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Recommendations</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {recommendations.map((rec: string, idx: number) => (
              <div
                key={idx}
                style={{
                  padding: 12,
                  background: "#f0f6ff",
                  border: "1px solid #4a90e2",
                  borderRadius: 6,
                  display: "flex",
                  gap: 12,
                }}
              >
                <div style={{ fontWeight: 700, color: "#4a90e2" }}>{idx + 1}.</div>
                <div style={{ flex: 1 }}>{rec}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
