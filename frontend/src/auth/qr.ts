// A QR code for a short text (the link an authenticator app reads, D-106), made here so no
// library is needed. Model 2, byte mode, error correction level M, versions 1 to 40, the mask
// chosen by the standard's penalty rules (ISO/IEC 18004). Checked in qr.test.ts against codes
// made by an independent generator, and read back with an independent decoder.

// Error correction level M: codewords of correction per block, and the number of blocks, by
// version (index 0 is unused).
const ECC_PER_BLOCK = [
  -1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28,
  28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28,
];
const BLOCKS = [
  -1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25,
  26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49,
];
const FORMAT_BITS_M = 0; // the two bits that say "level M" in the format information

export interface Qr {
  version: number;
  mask: number;
  size: number;
  /** modules[y][x]: true for a dark module. No quiet zone. */
  modules: boolean[][];
}

/** Modules that carry data or error correction in a code of this version. */
function rawModules(version: number): number {
  let result = (16 * version + 128) * version + 64;
  if (version >= 2) {
    const align = Math.floor(version / 7) + 2;
    result -= (25 * align - 10) * align - 55;
    if (version >= 7) result -= 36;
  }
  return result;
}

const dataCodewords = (version: number) =>
  Math.floor(rawModules(version) / 8) - (ECC_PER_BLOCK[version] ?? 0) * (BLOCKS[version] ?? 0);

/** Multiplication in the field the error correction works in (GF(2^8), polynomial 0x11D). */
function multiply(x: number, y: number): number {
  let z = 0;
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d);
    z ^= ((y >>> i) & 1) * x;
  }
  return z & 0xff;
}

function divisor(degree: number): number[] {
  const result = new Array<number>(degree).fill(0);
  result[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < degree; j++) {
      result[j] = multiply(result[j] ?? 0, root);
      if (j + 1 < degree) result[j] = (result[j] ?? 0) ^ (result[j + 1] ?? 0);
    }
    root = multiply(root, 2);
  }
  return result;
}

function remainder(data: number[], div: number[]): number[] {
  const result = div.map(() => 0);
  for (const byte of data) {
    const factor = byte ^ (result.shift() ?? 0);
    result.push(0);
    div.forEach((coefficient, i) => {
      result[i] = (result[i] ?? 0) ^ multiply(coefficient, factor);
    });
  }
  return result;
}

/** The data codewords for this text: mode, length, bytes, terminator and padding. */
function encode(bytes: Uint8Array, version: number): number[] {
  const bits: number[] = [];
  const push = (value: number, length: number) => {
    for (let i = length - 1; i >= 0; i--) bits.push((value >>> i) & 1);
  };
  push(0b0100, 4); // byte mode
  push(bytes.length, version <= 9 ? 8 : 16);
  bytes.forEach((b) => push(b, 8));
  const capacity = dataCodewords(version) * 8;
  push(0, Math.min(4, capacity - bits.length));
  push(0, (8 - (bits.length % 8)) % 8);
  for (let pad = 0xec; bits.length < capacity; pad ^= 0xec ^ 0x11) push(pad, 8);
  const codewords: number[] = [];
  for (let i = 0; i < bits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j++) byte = (byte << 1) | (bits[i + j] ?? 0);
    codewords.push(byte);
  }
  return codewords;
}

/** Splits the data into blocks, adds each block's error correction, and interleaves them. */
function withCorrection(data: number[], version: number): number[] {
  const blocks = BLOCKS[version] ?? 1;
  const eccLength = ECC_PER_BLOCK[version] ?? 0;
  const raw = Math.floor(rawModules(version) / 8);
  const shortBlocks = blocks - (raw % blocks);
  const shortLength = Math.floor(raw / blocks);
  const div = divisor(eccLength);
  const parts: number[][] = [];
  for (let i = 0, k = 0; i < blocks; i++) {
    const chunk = data.slice(k, k + shortLength - eccLength + (i < shortBlocks ? 0 : 1));
    k += chunk.length;
    const ecc = remainder(chunk, div);
    if (i < shortBlocks) chunk.push(0); // a place holder, skipped below
    parts.push(chunk.concat(ecc));
  }
  const result: number[] = [];
  for (let i = 0; i < (parts[0]?.length ?? 0); i++) {
    parts.forEach((block, j) => {
      if (i !== shortLength - eccLength || j >= shortBlocks) result.push(block[i] ?? 0);
    });
  }
  return result;
}

function alignmentPositions(version: number, size: number): number[] {
  if (version === 1) return [];
  const count = Math.floor(version / 7) + 2;
  const step =
    version === 32 ? 26 : Math.floor((version * 4 + count * 2 + 1) / (count * 2 - 2)) * 2;
  const result = [6];
  for (let pos = size - 7; result.length < count; pos -= step) result.splice(1, 0, pos);
  return result;
}

const MASKS: ((x: number, y: number) => boolean)[] = [
  (x, y) => (x + y) % 2 === 0,
  (_x, y) => y % 2 === 0,
  (x) => x % 3 === 0,
  (x, y) => (x + y) % 3 === 0,
  (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0,
  (x, y) => ((x * y) % 2) + ((x * y) % 3) === 0,
  (x, y) => (((x * y) % 2) + ((x * y) % 3)) % 2 === 0,
  (x, y) => (((x + y) % 2) + ((x * y) % 3)) % 2 === 0,
];

/** The QR code of a text. Throws when the text is too long for any version (about 2 300 bytes). */
export function qrCode(text: string): Qr {
  const bytes = new TextEncoder().encode(text);
  let version = 1;
  while (
    version <= 40 &&
    4 + (version <= 9 ? 8 : 16) + bytes.length * 8 > dataCodewords(version) * 8
  )
    version++;
  if (version > 40) throw new Error("The text is too long for a QR code");
  const size = version * 4 + 17;
  const modules = Array.from({ length: size }, () => new Array<boolean>(size).fill(false));
  const fixed = Array.from({ length: size }, () => new Array<boolean>(size).fill(false));
  const at = (x: number, y: number) => modules[y]?.[x] ?? false;
  const set = (x: number, y: number, dark: boolean) => {
    const row = modules[y];
    const fixedRow = fixed[y];
    if (!row || !fixedRow || x < 0 || x >= size) return;
    row[x] = dark;
    fixedRow[x] = true;
  };

  // Timing patterns, the three finder patterns with their separators, alignment patterns.
  for (let i = 0; i < size; i++) {
    set(6, i, i % 2 === 0);
    set(i, 6, i % 2 === 0);
  }
  for (const [cx, cy] of [
    [3, 3],
    [size - 4, 3],
    [3, size - 4],
  ] as const) {
    for (let dy = -4; dy <= 4; dy++) {
      for (let dx = -4; dx <= 4; dx++) {
        const distance = Math.max(Math.abs(dx), Math.abs(dy));
        const x = cx + dx;
        const y = cy + dy;
        if (x >= 0 && x < size && y >= 0 && y < size) set(x, y, distance !== 2 && distance !== 4);
      }
    }
  }
  const align = alignmentPositions(version, size);
  align.forEach((cx, i) => {
    align.forEach((cy, j) => {
      const last = align.length - 1;
      if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) return;
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          set(cx + dx, cy + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
        }
      }
    });
  });

  const drawFormat = (mask: number) => {
    const data = (FORMAT_BITS_M << 3) | mask;
    let rem = data;
    for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
    const bits = ((data << 10) | rem) ^ 0x5412;
    const bit = (i: number) => ((bits >>> i) & 1) !== 0;
    for (let i = 0; i <= 5; i++) set(8, i, bit(i));
    set(8, 7, bit(6));
    set(8, 8, bit(7));
    set(7, 8, bit(8));
    for (let i = 9; i < 15; i++) set(14 - i, 8, bit(i));
    for (let i = 0; i < 8; i++) set(size - 1 - i, 8, bit(i));
    for (let i = 8; i < 15; i++) set(8, size - 15 + i, bit(i));
    set(8, size - 8, true); // always dark
  };
  drawFormat(0); // reserves the places; the real bits follow the choice of mask
  if (version >= 7) {
    let rem = version;
    for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
    const bits = (version << 12) | rem;
    for (let i = 0; i < 18; i++) {
      const dark = ((bits >>> i) & 1) !== 0;
      const a = size - 11 + (i % 3);
      const b = Math.floor(i / 3);
      set(a, b, dark);
      set(b, a, dark);
    }
  }

  // The codewords, in the zigzag from the bottom right.
  const codewords = withCorrection(encode(bytes, version), version);
  let index = 0;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vertical = 0; vertical < size; vertical++) {
      for (let j = 0; j < 2; j++) {
        const x = right - j;
        const upward = ((right + 1) & 2) === 0;
        const y = upward ? size - 1 - vertical : vertical;
        const row = modules[y];
        if (row && !fixed[y]?.[x] && index < codewords.length * 8) {
          row[x] = (((codewords[index >>> 3] ?? 0) >>> (7 - (index & 7))) & 1) !== 0;
          index++;
        }
      }
    }
  }

  const applyMask = (mask: number) => {
    const invert = MASKS[mask];
    if (!invert) return;
    for (let y = 0; y < size; y++) {
      const row = modules[y];
      if (!row) continue;
      for (let x = 0; x < size; x++) {
        if (!fixed[y]?.[x] && invert(x, y)) row[x] = !row[x];
      }
    }
  };

  // The standard's four penalty rules; the mask with the lowest total is used.
  const penalty = (): number => {
    let result = 0;
    const addHistory = (run: number, history: number[]) => {
      if (history[0] === 0) run += size;
      history.pop();
      history.unshift(run);
    };
    const finderLike = (h: number[]): number => {
      const n = h[1] ?? 0;
      const core = n > 0 && h[2] === n && h[3] === n * 3 && h[4] === n && h[5] === n;
      return (
        (core && (h[0] ?? 0) >= n * 4 && (h[6] ?? 0) >= n ? 1 : 0) +
        (core && (h[6] ?? 0) >= n * 4 && (h[0] ?? 0) >= n ? 1 : 0)
      );
    };
    const lines = (cell: (a: number, b: number) => boolean) => {
      for (let a = 0; a < size; a++) {
        let colour = false;
        let run = 0;
        const history = [0, 0, 0, 0, 0, 0, 0];
        for (let b = 0; b < size; b++) {
          if (cell(a, b) === colour) {
            run++;
            if (run === 5) result += 3;
            else if (run > 5) result++;
          } else {
            addHistory(run, history);
            if (!colour) result += finderLike(history) * 40;
            colour = cell(a, b);
            run = 1;
          }
        }
        if (colour) {
          addHistory(run, history);
          run = 0;
        }
        addHistory(run + size, history);
        result += finderLike(history) * 40;
      }
    };
    lines((y, x) => at(x, y));
    lines((x, y) => at(x, y));
    let dark = 0;
    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        const colour = at(x, y);
        if (colour) dark++;
        if (
          x < size - 1 &&
          y < size - 1 &&
          colour === at(x + 1, y) &&
          colour === at(x, y + 1) &&
          colour === at(x + 1, y + 1)
        )
          result += 3;
      }
    }
    const total = size * size;
    result += (Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1) * 10;
    return result;
  };

  let best = 0;
  let lowest = Infinity;
  for (let mask = 0; mask < 8; mask++) {
    applyMask(mask);
    drawFormat(mask);
    const score = penalty();
    if (score < lowest) {
      best = mask;
      lowest = score;
    }
    applyMask(mask); // the same mask again takes it off
  }
  applyMask(best);
  drawFormat(best);
  return { version, mask: best, size, modules };
}

/** The dark modules as one SVG path, in a square of size + 2 * quiet units. */
export function qrPath(qr: Qr, quiet = 4): string {
  let path = "";
  qr.modules.forEach((row, y) => {
    row.forEach((dark, x) => {
      if (dark) path += `M${x + quiet} ${y + quiet}h1v1h-1z`;
    });
  });
  return path;
}
