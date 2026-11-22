import { Link } from "react-router";

import { EmptyState } from "../components/StateViews";

export function NotFoundPage() {
  return (
    <EmptyState
      level="h1"
      title="Page not found"
      message="The address does not match any page."
      action={<Link to="/projects">Go to projects</Link>}
    />
  );
}
