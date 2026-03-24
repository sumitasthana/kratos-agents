/**
 * dashboard/src/components/LogStream.tsx
 *
 * Fixed-height scrollable log viewer backed by useLogs SSE.
 * Auto-scrolls to the bottom unless the user has manually scrolled up.
 * Level colours: DEBUG=slate, INFO=sky, WARNING=amber, ERROR=red, CRITICAL=rose.
 */

import React, { useEffect, useRef, useState } from "react";
import { useLogs, type UseLogsFilter } from "../hooks/useLogs";
import type { ObsLogLine } from "../types/observability";

const LEVEL_COLORS: Record<string, string> = {
  DEBUG:    "#64748b",
  INFO:     "#38bdf8",
  WARNING:  "#fbbf24",
  ERROR:    "#f87171",
  CRITICAL: "#fb7185",
};

function LogRow({ line }: { line: ObsLogLine }): React.JSX.Element {
  const color = LEVEL_COLORS[line.level] ?? "#e2e8f0";
  const ts = line.timestamp.slice(11, 23); // HH:MM:SS.mmm
  return (
    <div style={{
      display: "flex",
      gap: 8,
      fontSize: 11,
      fontFamily: "monospace",
      lineHeight: "18px",
      borderBottom: "1px solid #0f172a",
      padding: "1px 4px",
    }}>
      <span style={{ color: "#475569", flexShrink: 0, width: 88 }}>{ts}</span>
      <span style={{ color, flexShrink: 0, width: 60 }}>{line.level}</span>
      <span style={{ color: "#94a3b8", flexShrink: 0, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {line.logger}
      </span>
      <span style={{ color: "#e2e8f0", flex: 1, wordBreak: "break-word" }}>{line.message}</span>
    </div>
  );
}

export interface LogStreamProps {
  filter?: UseLogsFilter;
  height?: number;
}

export default function LogStream({ filter, height = 320 }: LogStreamProps): React.JSX.Element {
  const { lines, connected, clear } = useLogs(filter);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Detect manual scroll-up
  function handleScroll(): void {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  }

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [lines, autoScroll]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height }}>
      {/* toolbar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "4px 8px",
        background: "#0f172a",
        borderBottom: "1px solid #1e293b",
        fontSize: 11,
        color: "#64748b",
        flexShrink: 0,
      }}>
        <span>
          <span style={{
            display: "inline-block",
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: connected ? "#4ade80" : "#f87171",
            marginRight: 6,
          }} />
          {connected ? "connected" : "disconnected"} · {lines.length} lines
        </span>
        <button
          onClick={clear}
          style={{
            background: "none",
            border: "1px solid #334155",
            borderRadius: 4,
            color: "#94a3b8",
            cursor: "pointer",
            fontSize: 10,
            padding: "2px 8px",
          }}
        >
          clear
        </button>
      </div>

      {/* scroll body */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          overflow: "auto",
          background: "#020817",
        }}
      >
        {lines.map((line, i) => (
          <LogRow key={i} line={line} /> // eslint-disable-line react/no-array-index-key
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
