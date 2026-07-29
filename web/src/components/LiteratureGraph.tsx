import { useMemo, useState } from "react";
import type { LiteratureGraph as GraphData } from "../api/types";

const colors = ["#387763", "#4d72ca", "#db785d", "#7f69ad", "#b18b2f"];

export function LiteratureGraph({
  graph,
  selected,
  onSelect
}: {
  graph: GraphData;
  selected?: string;
  onSelect: (id: string) => void;
}) {
  const [hovered, setHovered] = useState<string>();
  const layout = useMemo(() => {
    const width = 900;
    const height = 590;
    const centerX = width / 2;
    const centerY = height / 2;
    return graph.nodes.map((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(graph.nodes.length, 1) - 1.2;
      const ring = 155 + (index % 3) * 54;
      return {
        ...node,
        x: centerX + Math.cos(angle) * ring,
        y: centerY + Math.sin(angle) * ring,
        radius: Math.max(24, Math.min(48, 24 + Math.log2(node.citations + 1) * 4)),
        color: colors[index % colors.length]
      };
    });
  }, [graph.nodes]);
  const positions = Object.fromEntries(layout.map((node) => [node.id, node]));

  return (
    <svg
      className="literature-graph"
      viewBox="0 0 900 590"
      role="img"
      aria-label="文献关系图"
    >
      <defs>
        <filter id="node-shadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="6" stdDeviation="6" floodOpacity=".12" />
        </filter>
      </defs>
      <rect width="900" height="590" fill="#fbfcfd" />
      {graph.edges.map((edge, index) => {
        const source = positions[edge.source];
        const target = positions[edge.target];
        if (!source || !target) return null;
        return (
          <line
            key={`${edge.source}-${edge.target}-${index}`}
            x1={source.x}
            y1={source.y}
            x2={target.x}
            y2={target.y}
            stroke="#9db0a7"
            strokeOpacity=".6"
            strokeWidth={Math.max(1, (edge.weight ?? 0.5) * 3)}
          />
        );
      })}
      {layout.map((node) => {
        const active = selected === node.id || hovered === node.id;
        return (
          <g
            key={node.id}
            transform={`translate(${node.x} ${node.y})`}
            className={active ? "is-active" : ""}
            onMouseEnter={() => setHovered(node.id)}
            onMouseLeave={() => setHovered(undefined)}
            onClick={() => onSelect(node.id)}
            role="button"
            tabIndex={0}
          >
            <circle
              r={node.radius + (active ? 7 : 0)}
              fill={node.color}
              fillOpacity={active ? 1 : 0.88}
              filter="url(#node-shadow)"
            />
            <circle
              r={node.radius - 7}
              fill="none"
              stroke="white"
              strokeOpacity=".28"
            />
            <text
              textAnchor="middle"
              dominantBaseline="central"
              fill="white"
              fontSize="13"
              fontWeight="700"
            >
              {node.id}
            </text>
            {active && (
              <g transform={`translate(0 ${node.radius + 24})`}>
                <rect
                  x="-126"
                  y="-11"
                  width="252"
                  height="30"
                  rx="7"
                  fill="#152621"
                />
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  y="4"
                  fill="white"
                  fontSize="11"
                >
                  {shorten(node.title, 38)}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function shorten(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}
