// A project's Tasks tab: every task of this project, with the same filters and actions as the
// Tasks page (D-117).
import { TasksPage } from "../tasks/TasksPage";
import { useProject } from "./ProjectDetailPage";

export function ProjectTasksTab() {
  const { project } = useProject();
  return <TasksPage fixedProjectId={project.id} />;
}
