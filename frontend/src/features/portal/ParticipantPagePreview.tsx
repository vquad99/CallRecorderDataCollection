// A participant's own page as they see it, for a Super Admin (D-100): no link needed, read-only.
import { Link, useParams } from "react-router";

import { getParticipantPage } from "../../api/portal";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useResource } from "../../hooks/useResource";
import { ParticipantView } from "./PortalPage";
import "./portal.css";

export function ParticipantPagePreview() {
  const { projectId = "", participantId = "" } = useParams();
  const { state, reload } = useResource(
    () => getParticipantPage(projectId, participantId),
    [projectId, participantId],
  );
  return (
    <section className="stack portal__main portal__main--inside">
      <p className="notice notice--info" role="status">
        The participant&apos;s own page, as they see it. Read-only: the consent buttons are hidden.{" "}
        <Link to={`/projects/${projectId}/participants`}>Back to participants</Link>
      </p>
      {state.status === "loading" ? <LoadingState label="Loading the participant's page" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <ParticipantView view={state.data} token={null} onChange={() => undefined} />
      ) : null}
    </section>
  );
}
