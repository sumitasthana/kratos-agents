import React, { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

type LineageGraphProps = {
  lineageData: any;
};

export default function LineageGraph({ lineageData }: LineageGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  function asTableName(v: any): string | null {
    if (!v) return null;
    if (typeof v === "string") return v;
    if (typeof v === "object") {
      if (typeof v.table === "string") return v.table;
      if (typeof v.name === "string") return v.name;
    }
    return null;
  }

  function addNode(elements: any[], seen: Set<string>, table: string) {
    if (!table || seen.has(table)) return;
    seen.add(table);
    elements.push({
      data: {
        id: table,
        label: table,
        type: "table",
      },
    });
  }

  useEffect(() => {
    if (!containerRef.current || !lineageData) return;

    const elements: any[] = [];
    const seenNodes = new Set<string>();

    const tables = Array.isArray(lineageData.tables) ? lineageData.tables : [];
    // lineage-map output commonly uses `lineage` as column-level mappings.
    const mappings = Array.isArray(lineageData.lineage)
      ? lineageData.lineage
      : Array.isArray(lineageData.mappings)
        ? lineageData.mappings
        : [];

    // Add nodes from explicit tables list when available
    for (const t of tables) {
      const name = asTableName(t);
      if (name) addNode(elements, seenNodes, name);
    }

    // Add edges derived from column lineage mappings
    // mapping shape:
    // { target: {table, column}, sources: [{table, column}, ...] }
    let edgeIdx = 0;
    for (const m of mappings) {
      const targetTable = asTableName(m?.target);
      const targetCol = typeof m?.target?.column === "string" ? m.target.column : "";
      if (targetTable) addNode(elements, seenNodes, targetTable);

      const sources = Array.isArray(m?.sources) ? m.sources : [];
      for (const s of sources) {
        const sourceTable = asTableName(s);
        const sourceCol = typeof s?.column === "string" ? s.column : "";
        if (!sourceTable || !targetTable) continue;
        addNode(elements, seenNodes, sourceTable);
        elements.push({
          data: {
            id: `edge-${edgeIdx++}`,
            source: sourceTable,
            target: targetTable,
            label: targetCol ? `${sourceCol} → ${targetCol}` : "",
          },
        });
      }
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#4a90e2",
            label: "data(label)",
            color: "#fff",
            "text-valign": "center",
            "text-halign": "center",
            "font-size": "12px",
            width: 80,
            height: 80,
            "border-width": 2,
            "border-color": "#2c5aa0",
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#999",
            "target-arrow-color": "#999",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": "10px",
            color: "#666",
            "text-rotation": "autorotate",
          },
        },
      ],
      layout: {
        name: "breadthfirst",
        directed: true,
        spacingFactor: 1.5,
      },
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
    };
  }, [lineageData]);

  if (!lineageData) {
    return <div style={{ padding: 20, color: "#666" }}>No lineage data available</div>;
  }

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}
