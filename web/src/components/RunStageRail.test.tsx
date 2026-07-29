import { render, screen } from "@testing-library/react";
import { RunStageRail } from "./RunStageRail";

describe("RunStageRail", () => {
  it("renders every auditable workflow stage", () => {
    render(<RunStageRail current="assessed" />);
    expect(screen.getByText("初始化")).toBeInTheDocument();
    expect(screen.getByText("人工筛选")).toBeInTheDocument();
    expect(screen.getByText("质量评估")).toBeInTheDocument();
    expect(screen.getByText("审计完成")).toBeInTheDocument();
  });
});
