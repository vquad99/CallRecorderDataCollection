// The QR generator makes the codes an independent generator makes (D-107).
// Requirements: AUTH-008
//
// How the expected values were made (docs/evidence/phase10/qr_2026-11-14.txt): each text below
// was encoded here and by the Python library `qrcode` (byte mode, level M, the same mask) and
// the two were equal module for module, for versions 1 to 40; OpenCV's decoder read every code
// back. The fingerprints are of those checked codes, so a change that alters a single module
// fails here.
import { describe, expect, it } from "vitest";

import { qrCode, qrPath } from "./qr";

const LINK =
  "otpauth://totp/Conversation%20Collection:demo.super-admin%40example.org?secret=AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH&issuer=Conversation%20Collection&digits=6&period=30";

/** Dark modules, and a number that depends on where each of them is. */
function fingerprint(modules: boolean[][]): [number, number] {
  let dark = 0;
  let hash = 0;
  modules.forEach((row, y) => {
    row.forEach((cell, x) => {
      if (!cell) return;
      dark++;
      hash = (hash * 31 + (y * modules.length + x)) % 1_000_000_007;
    });
  });
  return [dark, hash];
}

const CHECKED: [string, string, number, number, number, number][] = [
  ["one letter", "A", 1, 4, 240, 793781403],
  ["a short text", "HELLO WORLD", 1, 4, 232, 482235554],
  ["a web address", "https://dubdesk.live/", 2, 1, 318, 410940487],
  ["an authenticator link", LINK, 9, 2, 1376, 152908525],
  [
    "a link with a long account name",
    LINK.replace("demo.super-admin", "a.very.long.name.of.a.person.who.manages.projects.here"),
    10,
    2,
    1624,
    963906077,
  ],
  ["300 letters (a 16-bit length, eight blocks)", "x".repeat(300), 13, 0, 2436, 508033198],
  ["text in another script", "नमस्ते दुनिया, यह एक परीक्षण है। ".repeat(8), 21, 1, 5225, 112643319],
];

describe("QR code", () => {
  it.each(CHECKED)("of %s is the checked code", (_name, text, version, mask, dark, hash) => {
    const qr = qrCode(text);
    expect([qr.version, qr.mask, qr.size]).toEqual([version, mask, version * 4 + 17]);
    expect(fingerprint(qr.modules)).toEqual([dark, hash]);
  });

  it("has the three corner squares a scanner looks for, and none in the fourth corner", () => {
    const { modules, size } = qrCode(LINK);
    const square = (cx: number, cy: number) =>
      [-3, -2, -1, 0, 1, 2, 3]
        .map((dy) =>
          [-3, -2, -1, 0, 1, 2, 3].map((dx) => (modules[cy + dy]?.[cx + dx] ? "#" : ".")).join(""),
        )
        .join("/");
    const finder = "#######/#.....#/#.###.#/#.###.#/#.###.#/#.....#/#######";
    expect(square(3, 3)).toBe(finder);
    expect(square(size - 4, 3)).toBe(finder);
    expect(square(3, size - 4)).toBe(finder);
    expect(square(size - 4, size - 4)).not.toBe(finder);
  });

  it("is drawn as one path with a quiet border, one square per dark module", () => {
    const qr = qrCode("HELLO WORLD");
    const path = qrPath(qr);
    expect(path.match(/M/g)?.length).toBe(232);
    expect(path.startsWith("M4 4h1v1h-1z")).toBe(true); // the top-left module, four units in
    expect(qrPath(qr, 0).startsWith("M0 0h1v1h-1z")).toBe(true);
  });

  it("refuses a text too long for any code", () => {
    expect(qrCode("v".repeat(2300)).version).toBe(40);
    expect(() => qrCode("v".repeat(2400))).toThrow("too long");
  });
});
