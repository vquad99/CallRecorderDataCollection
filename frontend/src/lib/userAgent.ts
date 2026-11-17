// A browser's user-agent text in plain words: "Edge on Windows". Only the common browsers and
// systems are named; anything else is "Unknown browser".

const BROWSERS: [RegExp, string][] = [
  [/Edg(e|A|iOS)?\//, "Edge"],
  [/OPR\/|Opera/, "Opera"],
  [/SamsungBrowser\//, "Samsung Internet"],
  [/Firefox\/|FxiOS\//, "Firefox"],
  [/Chrome\/|CriOS\//, "Chrome"],
  [/Safari\//, "Safari"],
];

const SYSTEMS: [RegExp, string][] = [
  [/Windows/, "Windows"],
  [/Android/, "Android"],
  [/iPhone|iPad|iPod/, "iPhone or iPad"],
  [/Mac OS X|Macintosh/, "Mac"],
  [/CrOS/, "Chromebook"],
  [/Linux/, "Linux"],
];

export function describeUserAgent(ua: string | null | undefined): string {
  if (!ua) return "Unknown browser";
  const browser = BROWSERS.find(([pattern]) => pattern.test(ua))?.[1];
  const system = SYSTEMS.find(([pattern]) => pattern.test(ua))?.[1];
  if (!browser && !system) return "Unknown browser";
  if (!system) return browser ?? "Unknown browser";
  return `${browser ?? "A browser"} on ${system}`;
}
