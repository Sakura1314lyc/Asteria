import { useQuery } from "@tanstack/react-query";
import { Outlet, useParams } from "react-router";
import { api } from "../api/client";
import { ProjectHeader, ProjectNav } from "../components/ProjectNav";
import { ErrorState, LoadingState } from "../components/Ui";

export function ProjectLayout() {
  const { projectId = "" } = useParams();
  const query = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
    enabled: Boolean(projectId),
    refetchInterval: (state) => {
      const project = state.state.data;
      return project?.runs?.some((run) =>
        ["queued", "running"].includes(run.status)
      )
        ? 2500
        : false;
    }
  });

  if (query.isLoading) return <LoadingState label="正在打开研究项目" />;
  if (query.isError || !query.data) {
    return <ErrorState error={query.error} retry={() => query.refetch()} />;
  }
  return (
    <div className="project-page">
      <ProjectHeader project={query.data} />
      <ProjectNav projectId={projectId} />
      <div className="project-workspace">
        <Outlet context={{ project: query.data }} />
      </div>
    </div>
  );
}
