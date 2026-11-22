// A project's Tasks tab: every task of this project, with the same filters and actions as the
// Tasks page (D-117); a project that records one type (D-153) has no recording type to filter by.
import { TasksPage } from "../tasks/TasksPage";
import { useProject } from "./ProjectDetailPage";
import { onlyMode } from "./recordingType";

export function ProjectTasksTab() {
  const { project } = useProject();
  return <TasksPage fixedProjectId={project.id} fixedMode={onlyMode(project)} />;
}
