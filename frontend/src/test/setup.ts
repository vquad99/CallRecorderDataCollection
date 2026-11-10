import { configure } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

// A page gets 5 s to appear instead of 1 s: on a busy machine (CI, a shared server) the first
// render of a lazily loaded page can take longer, which made unrelated tests fail at random.
configure({ asyncUtilTimeout: 5000 });
