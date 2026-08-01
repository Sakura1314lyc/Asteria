import type { Project } from "../api/types";

const stageOrder = [
  "initialized",
  "planned",
  "searched",
  "screened",
  "extracted",
  "assessed",
  "written",
  "completed"
];

const channels = [
  { key: "plan", label: "方案", threshold: "planned" },
  { key: "search", label: "检索", threshold: "searched" },
  { key: "screen", label: "筛选", threshold: "screened" },
  { key: "evidence", label: "证据", threshold: "extracted" },
  { key: "report", label: "报告", threshold: "written" }
] as const;

function reached(project: Project, threshold: string) {
  const latest = project.runs?.[0];
  if (threshold === "written" && (project.reports?.length ?? 0) > 0) return true;
  return (
    stageOrder.indexOf(latest?.stage ?? "") >= stageOrder.indexOf(threshold) ||
    latest?.status === "completed"
  );
}

function currentChannel(project: Project) {
  const index = channels.findIndex((channel) => !reached(project, channel.threshold));
  return index === -1 ? channels.length - 1 : index;
}

export function EvidenceSignal({ projects }: { projects: Project[] }) {
  const total = projects.length;
  const values = channels.map((channel) => {
    const completed = projects.filter((project) =>
      reached(project, channel.threshold)
    ).length;
    return total ? Math.round((completed / total) * 100) : 0;
  });
  const activeChannels = new Set(
    projects
      .filter((project) =>
        ["queued", "running", "waiting_for_screening"].includes(
          project.runs?.[0]?.status ?? ""
        )
      )
      .map(currentChannel)
  );
  const points = values
    .map((value, index) => `${24 + index * 103},${88 - value * 0.56}`)
    .join(" ");
  const areaPoints = `${points} 436,98 24,98`;
  const completion = values.length
    ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length)
    : 0;
  const summary = channels
    .map((channel, index) => `${channel.label}${values[index]}%`)
    .join("，");

  return (
    <figure
      className="evidence-signal"
      aria-label={`项目证据信号：${summary}`}
    >
      <figcaption>
        <span>
          <i aria-hidden="true" /> Evidence constellation
        </span>
        <small>{total} 个项目 / 当前快照</small>
      </figcaption>
      <div className="evidence-signal__body">
        <div className="evidence-signal__readout" aria-hidden="true">
          <span>链路完成度</span>
          <strong>{String(completion).padStart(2, "0")}</strong>
          <small>percent</small>
        </div>
        <div className="evidence-signal__plot">
          <svg viewBox="0 0 460 106" role="img" aria-hidden="true">
            <defs>
              <linearGradient id="signal-stroke" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0" stopColor="#6f9cff" />
                <stop offset="0.52" stopColor="#5bd9d0" />
                <stop offset="1" stopColor="#f0b968" />
              </linearGradient>
              <linearGradient id="signal-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#5bd9d0" stopOpacity="0.22" />
                <stop offset="1" stopColor="#6f9cff" stopOpacity="0" />
              </linearGradient>
            </defs>
            {[32, 60, 88].map((y) => (
              <line
                className="evidence-signal__guide"
                x1="24"
                x2="436"
                y1={y}
                y2={y}
                key={y}
              />
            ))}
            <polygon className="evidence-signal__area" points={areaPoints} />
            <polyline className="evidence-signal__trace" points={points} />
            {values.map((value, index) => (
              <g
                className={activeChannels.has(index) ? "is-active" : ""}
                key={channels[index].key}
              >
                <circle
                  className="evidence-signal__orbit"
                  cx={24 + index * 103}
                  cy={88 - value * 0.56}
                  r={11 + (index % 2) * 3}
                />
                <circle
                  className="evidence-signal__halo"
                  cx={24 + index * 103}
                  cy={88 - value * 0.56}
                  r="8"
                />
                <circle
                  className="evidence-signal__point"
                  cx={24 + index * 103}
                  cy={88 - value * 0.56}
                  r="3.5"
                  style={{ animationDelay: `${260 + index * 85}ms` }}
                />
              </g>
            ))}
            <line
              className="evidence-signal__scan"
              x1="0"
              x2="0"
              y1="18"
              y2="98"
            />
          </svg>
          <div className="evidence-signal__legend" aria-hidden="true">
            {channels.map((channel, index) => (
              <span key={channel.key}>
                <strong>{String(values[index]).padStart(3, "0")}%</strong>
                <small>{channel.label}</small>
              </span>
            ))}
          </div>
        </div>
      </div>
    </figure>
  );
}
