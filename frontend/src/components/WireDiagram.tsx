// Wire diagram of the run's decision pipeline, rendered with React Flow.
import { useMemo } from "react";
import ReactFlow, {
  Background,
  type Edge,
  Handle,
  type Node,
  type NodeProps,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import type { DecisionNode } from "../types";
import { Badge } from "./ui";

const STATUS_TONE: Record<
  DecisionNode["status"],
  { tone: "neutral" | "accent" | "good" | "warn" | "bad"; label: string }
> = {
  pending: { tone: "neutral", label: "pending" },
  proposed: { tone: "warn", label: "awaiting approval" },
  approved: { tone: "accent", label: "approved" },
  done: { tone: "good", label: "done" },
  error: { tone: "bad", label: "error" },
};

function DecisionNodeCard({ data }: NodeProps<DecisionNode>) {
  const status = STATUS_TONE[data.status];
  return (
    <div className="w-64 rounded-xl border border-edge bg-panel px-4 py-3 shadow-lg shadow-black/30">
      <Handle type="target" position={Position.Left} className="!bg-edge" />
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold">{data.title}</span>
        <Badge tone={status.tone}>{status.label}</Badge>
      </div>
      {data.detail && (
        <p className="mt-1.5 line-clamp-3 text-[11px] leading-snug text-ink-dim">
          {data.detail}
        </p>
      )}
      <Handle type="source" position={Position.Right} className="!bg-edge" />
    </div>
  );
}

const nodeTypes = { decision: DecisionNodeCard };

export function WireDiagram({ decisions }: { decisions: DecisionNode[] }) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node<DecisionNode>[] = decisions.map((d, i) => ({
      id: `${i}`,
      type: "decision",
      position: { x: i * 300, y: (i % 2) * 24 },
      data: d,
      draggable: true,
    }));
    const edges: Edge[] = decisions.slice(1).map((d, i) => ({
      id: `e${i}`,
      source: `${i}`,
      target: `${i + 1}`,
      animated: d.status === "proposed" || d.status === "pending",
      style: { stroke: "#4f8ef7", strokeWidth: 1.5 },
    }));
    return { nodes, edges };
  }, [decisions]);

  return (
    <div className="h-48 w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: false }}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        panOnDrag
        preventScrolling={false}
      >
        <Background color="#1e293b" gap={20} />
      </ReactFlow>
    </div>
  );
}
