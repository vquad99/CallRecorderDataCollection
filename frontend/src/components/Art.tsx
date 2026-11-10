// Decorative illustrations (hidden from screen readers). Drawn with theme colours so they follow
// light and dark mode.

/** Sign-in panel: a product preview - two speakers' waveforms, a QC result and a progress card. */
export function LoginArt() {
  const a = [10, 22, 34, 18, 44, 60, 38, 24, 14, 30, 48, 26, 12, 20, 36, 16];
  const b = [8, 16, 12, 28, 20, 40, 56, 30, 18, 42, 22, 14, 34, 50, 24, 10];
  return (
    <svg className="art art--login" viewBox="0 0 520 400" aria-hidden="true" focusable="false">
      <rect x="20" y="28" width="360" height="210" rx="14" className="art__card" />
      <circle cx="52" cy="62" r="16" className="art__a" />
      <rect x="78" y="50" width="96" height="9" rx="4.5" className="art__line" />
      <rect x="78" y="66" width="60" height="7" rx="3.5" className="art__line art__line--soft" />
      <rect x="298" y="50" width="62" height="22" rx="11" className="art__chip" />
      <circle cx="312" cy="61" r="4" className="art__dot" />
      {a.map((h, i) => (
        <rect
          key={`a${i}`}
          x={44 + i * 20}
          y={128 - h / 2}
          width="9"
          height={h}
          rx="4.5"
          className="art__a"
        />
      ))}
      {b.map((h, i) => (
        <rect
          key={`b${i}`}
          x={44 + i * 20}
          y={196 - h / 2}
          width="9"
          height={h}
          rx="4.5"
          className="art__b"
        />
      ))}
      <rect
        x="250"
        y="206"
        width="250"
        height="150"
        rx="14"
        className="art__card art__card--raised"
      />
      <rect x="272" y="228" width="90" height="9" rx="4.5" className="art__line" />
      <path d="M272 318 L310 296 L346 304 L384 270 L424 280 L478 246" className="art__trend" />
      <path
        d="M272 318 L310 296 L346 304 L384 270 L424 280 L478 246 L478 336 L272 336 Z"
        className="art__area"
      />
      <rect
        x="40"
        y="270"
        width="180"
        height="86"
        rx="14"
        className="art__card art__card--raised"
      />
      <circle cx="78" cy="313" r="22" className="art__ring" />
      <path d="M78 291 a22 22 0 1 1 -19 11" className="art__ring-fill" />
      <rect x="114" y="298" width="84" height="9" rx="4.5" className="art__line" />
      <rect x="114" y="316" width="54" height="7" rx="3.5" className="art__line art__line--soft" />
      <circle cx="438" cy="96" r="34" className="art__badge" />
      <path d="M423 96 l11 11 l20 -22" className="art__tick" />
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
