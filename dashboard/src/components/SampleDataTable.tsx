/**
 * SampleDataTable.tsx
 *
 * Fetches GET /demo/scenarios/{scenarioId} and renders the accounts array
 * as a sortable table: account_id, name, balance, orc_category, coverage_status
 */

import React, { useEffect, useState } from "react";
import type { ScenarioId } from "../types/demo";

interface AccountRow {
  account_id: string;
  name: string;
  current_balance: number;
  orc_code: string;
  coverage_status?: string;
  account_type?: string;
}

interface SampleDataTableProps {
  scenarioId: ScenarioId | null;
}

const SMDIA = 250_000;

function coverageStatus(row: AccountRow): { label: string; color: string } {
  if (row.current_balance > SMDIA) {
    return { label: "OVER SMDIA", color: "#f87171" };
  }
  return { label: "OK", color: "#4ade80" };
}

function formatBalance(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

export default function SampleDataTable({ scenarioId }: SampleDataTableProps) {
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!scenarioId) {
      setAccounts([]);
      return;
    }
    setLoading(true);
    setError(null);

    fetch(`/demo/scenarios/${scenarioId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<{ accounts: AccountRow[] }>;
      })
      .then((data) => {
        setAccounts(data.accounts ?? []);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setLoading(false));
  }, [scenarioId]);

  if (!scenarioId) {
    return (
      <div style={emptyStyle}>Select a scenario to view sample data.</div>
    );
  }

  if (loading) {
    return <div style={emptyStyle}>Loading accounts…</div>;
  }

  if (error) {
    return (
      <div style={{ ...emptyStyle, color: "#f87171" }}>
        Failed to load accounts: {error}
      </div>
    );
  }

  if (accounts.length === 0) {
    return <div style={emptyStyle}>No accounts found.</div>;
  }

  const overSmdia = accounts.filter((a) => a.current_balance > SMDIA).length;

  return (
    <div style={{ padding: "12px 16px" }}>
      <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ color: "#94a3b8", fontSize: 12 }}>
          {accounts.length} accounts
        </span>
        {overSmdia > 0 && (
          <span
            style={{
              background: "#2c0a0a",
              border: "1px solid #7f1d1d",
              borderRadius: 4,
              padding: "2px 8px",
              color: "#f87171",
              fontSize: 11,
            }}
          >
            {overSmdia} over SMDIA ($250K)
          </span>
        )}
      </div>

      <div style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: 12,
            fontFamily: "monospace",
          }}
        >
          <thead>
            <tr>
              {["Account ID", "Name", "Balance", "ORC", "Coverage"].map((h) => (
                <th
                  key={h}
                  style={{
                    textAlign: "left",
                    padding: "6px 12px",
                    color: "#64748b",
                    fontWeight: 600,
                    borderBottom: "1px solid #1f2937",
                    fontSize: 11,
                    letterSpacing: "0.04em",
                    whiteSpace: "nowrap",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {accounts.map((row, idx) => {
              const { label, color } = coverageStatus(row);
              return (
                <tr
                  key={row.account_id}
                  style={{
                    background: idx % 2 === 0 ? "#0a0c10" : "#0d0f15",
                  }}
                >
                  <td style={tdStyle}>{row.account_id}</td>
                  <td style={{ ...tdStyle, color: "#e2e8f0", fontFamily: "sans-serif" }}>
                    {row.name}
                  </td>
                  <td
                    style={{
                      ...tdStyle,
                      color: row.current_balance > SMDIA ? "#f87171" : "#94a3b8",
                      textAlign: "right",
                    }}
                  >
                    {formatBalance(row.current_balance)}
                  </td>
                  <td style={tdStyle}>{row.orc_code}</td>
                  <td style={{ ...tdStyle, color }}>
                    <span
                      style={{
                        background: label === "OVER SMDIA" ? "#450a0a" : "#052e16",
                        borderRadius: 3,
                        padding: "1px 7px",
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: "0.04em",
                      }}
                    >
                      {label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const emptyStyle: React.CSSProperties = {
  padding: 24,
  color: "#4b5563",
  fontSize: 13,
  textAlign: "center",
};

const tdStyle: React.CSSProperties = {
  padding: "6px 12px",
  color: "#94a3b8",
  borderBottom: "1px solid #111827",
};
