import { useOutletContext } from "react-router-dom";
import type { Project } from "../api/types";

export function useProjectContext() {
  return useOutletContext<{ project: Project }>();
}
