// One line on the project's Participants page for the people who recruit (D-153): how many more
// speakers the targets still need, with a link to the Progress page's "Still needed" tables (by
// age band and gender, and by district). Nothing is shown while it loads, without a speakers
// target, or if the progress cannot be read (the page works without it).
import { Link } from "react-router";

import { getProgress } from "../../api/progress";
import { useResource } from "../../hooks/useResource";

export function StillNeededLine({ projectId }: { projectId: string }) {
  const { state } = useResource(() => getProgress(projectId), [projectId]);
  if (state.status !== "loaded") return null;
  const speakers = state.data.still_needed.speakers;
  const needed = speakers.total.total.still_needed;
  if (needed === null) return null;
  const link = <Link to={`/projects/${projectId}/progress`}>see Progress</Link>;
  return (
    <p className="notice notice--info">
      {needed > 0 ? (
        <>
          <strong>
            Still needed: {needed} speaker{needed === 1 ? "" : "s"}
          </strong>{" "}
          to recruit for the target of {speakers.target}. Which ages, genders and districts: {link}.
        </>
      ) : (
        <>
          <strong>No more speakers needed</strong>: the people done and registered cover the target
          of {speakers.target} ({link}).
        </>
      )}
    </p>
  );
}
