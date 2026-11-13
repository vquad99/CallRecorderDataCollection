// Decorative illustrations (hidden from screen readers). Drawn with theme colours so they follow
// light and dark mode.

/** Sign-in panel: two voices as a field of dots, larger where the waves peak. One path, so the
 * page stays light however many dots there are. */
function waveDots(): string {
  let d = "";
  for (let col = 0; col < 56; col += 1) {
    for (let row = 0; row < 28; row += 1) {
      const x = col / 55;
      const y = row / 27;
      const a = 0.5 + 0.3 * Math.sin(x * 9) * Math.cos(x * 3.1);
      const b = 0.5 - 0.32 * Math.sin(x * 7 + 1.4) * Math.cos(x * 2.3);
      const near = Math.min(Math.abs(y - a), Math.abs(y - b));
      const edge = Math.sqrt(Math.sin(Math.PI * x) * Math.sin(Math.PI * y));
      const strength = Math.max(0, 1 - near * 2.6) * edge;
      if (strength < 0.1) continue;
      const r = (0.5 + strength * 2.4).toFixed(1);
      const cx = (12 + col * 9.2).toFixed(1);
      const cy = (10 + row * 9.8).toFixed(1);
      d += `M${cx} ${cy}m-${r} 0a${r} ${r} 0 1 0 ${Number(r) * 2} 0a${r} ${r} 0 1 0 -${Number(r) * 2} 0`;
    }
  }
  return d;
}
const WAVE_DOTS = waveDots();

export function LoginArt() {
  return (
    <svg className="art art--login" viewBox="0 0 528 284" aria-hidden="true" focusable="false">
      <path d={WAVE_DOTS} />
    </svg>
  );
}

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
