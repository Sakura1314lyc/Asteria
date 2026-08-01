import { useOutletContext } from "react-router";
import type { Project } from "../api/types";

export function useProjectContext() {
  return useOutletContext<{ project: Project }>();
}
