import { useQuery } from "@tanstack/react-query";
import { Network, Quote } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import { LiteratureGraph } from "../components/LiteratureGraph";
import { EmptyState, ErrorState, LoadingState, SectionTitle } from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";

export function MapPage() {
  const { project } = useProjectContext();
  const completed = project.runs?.find((run) => run.status === "completed");
  const [selected, setSelected] = useState<string>();
  const graph = useQuery({
    queryKey: ["graph", completed?.id],
    queryFn: () => api.getGraph(completed?.id ?? ""),
    enabled: Boolean(completed)
  });

  if (!completed) {
    return (
      <EmptyState
        title="图谱会在证据评估后出现"
        detail="完成一次运行后，可以在这里联动查看文献节点与关系。"
        icon={<Network size={23} />}
      />
    );
  }
  if (graph.isLoading) return <LoadingState label="正在构建文献图谱视图" />;
  if (graph.isError || !graph.data) {
    return <ErrorState error={graph.error} retry={() => graph.refetch()} />;
  }
  const node =
    graph.data.nodes.find((item) => item.id === selected) ?? graph.data.nodes[0];

  return (
    <div className="map-page">
      <SectionTitle
        title="从图谱回到具体论文"
        detail={graph.data.meta.meaning}
      />
      <div className="map-workspace">
        <div className="map-canvas">
          <div className="map-legend">
            <span>{graph.data.meta.node_count} nodes</span>
            <span>{graph.data.meta.edge_count} edges</span>
            <small>节点大小按引用量近似</small>
          </div>
          <LiteratureGraph
            graph={graph.data}
            selected={node?.id}
            onSelect={setSelected}
          />
        </div>
        {node && (
          <aside className="map-inspector">
            <span className="paper-code">{node.id}</span>
            <h2>{node.title}</h2>
            <p>{node.authors.join(", ") || "作者未知"}</p>
            <dl>
              <div>
                <dt>年份</dt>
                <dd>{node.year ?? "—"}</dd>
              </div>
              <div>
                <dt>引用量</dt>
                <dd>{node.citations}</dd>
              </div>
              <div>
                <dt>相关性分数</dt>
                <dd>{node.score.toFixed(3)}</dd>
              </div>
            </dl>
            <div className="map-inspector__venue">
              <Quote size={15} />
              {node.venue || "Venue 未知"}
            </div>
            <p className="evidence-boundary">
              当前边表示词汇相似或共同作者时，不应解读为真实引用关系。
            </p>
          </aside>
        )}
      </div>
    </div>
  );
}
