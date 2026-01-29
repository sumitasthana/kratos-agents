import React, { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

type GitDataflowGraphProps = {
  dataflowData: any;
};

export default function GitDataflowGraph({ dataflowData }: GitDataflowGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    if (!containerRef.current || !dataflowData) return;

    const elements: any[] = [];
    const nodes = new Set<string>();

    // Extract dataflow patterns
    const patterns = dataflowData.dataflow_patterns || dataflowData.patterns || [];

    patterns.forEach((pattern: any, idx: number) => {
      const source = pattern.source || pattern.from;
      const target = pattern.target || pattern.to;
      const type = pattern.type || pattern.operation || "transform";

      if (source) nodes.add(source);
      if (target) nodes.add(target);

      if (source && target) {
        elements.push({
          data: {
            id: `edge-${idx}`,
            source,
            target,
            label: type,
            type,
          },
        });
      }
    });

    // Add nodes
    nodes.forEach((node) => {
      elements.push({
        data: {
          id: node,
          label: node,
        },
      });
    });

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#50c878",
            label: "data(label)",
            color: "#fff",
            "text-valign": "center",
            "text-halign": "center",
            "font-size": "11px",
            width: 70,
            height: 70,
            "border-width": 2,
            "border-color": "#2d7a4d",
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
            "font-size": "9px",
            color: "#666",
            "text-rotation": "autorotate",
          },
        },
        {
          selector: "edge[type='read']",
          style: {
            "line-color": "#4a90e2",
            "target-arrow-color": "#4a90e2",
          },
        },
        {
          selector: "edge[type='write']",
          style: {
            "line-color": "#e24a4a",
            "target-arrow-color": "#e24a4a",
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
  }, [dataflowData]);

  if (!dataflowData) {
    return <div style={{ padding: 20, color: "#666" }}>No git dataflow data available</div>;
  }

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}
