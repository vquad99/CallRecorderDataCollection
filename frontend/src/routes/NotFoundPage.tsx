import { Link } from "react-router";

import { EmptyState } from "../components/StateViews";

export function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      message="The address does not match any page."
      action={<Link to="/">Go to system status</Link>}
    />
  );
}
