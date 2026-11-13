// Decorative illustrations (hidden from screen readers). Drawn with theme colours so they follow
// light and dark mode.

/** Empty lists: an open tray with a waveform. */
export function EmptyArt() {
  return (
    <svg className="art art--empty" viewBox="0 0 160 110" aria-hidden="true" focusable="false">
      <ellipse cx="80" cy="96" rx="58" ry="8" className="art__shadow" />
      <path
        d="M28 52 L48 22 H112 L132 52 V82 a8 8 0 0 1 -8 8 H36 a8 8 0 0 1 -8 -8 Z"
        className="art__card"
      />
      <path
        d="M28 52 H58 a6 6 0 0 1 6 6 a16 16 0 0 0 32 0 a6 6 0 0 1 6 -6 H132"
        className="art__fold"
      />
      {[10, 20, 30, 16, 24, 12].map((h, i) => (
        <rect
          key={i}
          x={55 + i * 9}
          y={34 - h / 2}
          width="4.5"
          height={h}
          rx="2.25"
          className="art__a"
        />
      ))}
    </svg>
  );
}
