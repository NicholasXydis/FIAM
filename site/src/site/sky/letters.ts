// The name the particles write, in the film's serif.
const FACE = '"Instrument Serif"';
const WORDS = ["QUARCC", "Purple"] as const;

// A place inside a letter, and how far across the name it lies.
interface Spot {
  x: number;
  y: number;
  across: number;
}

// Waits for the serif, so letters are sampled in the right face.
export const fontsReady = () =>
  Promise.all([document.fonts.load(`400 120px ${FACE}`), document.fonts.load(`italic 400 120px ${FACE}`)]).catch(
    () => undefined,
  );

// Random points inside "QUARCC Purple", set to fill a box.
export function letters(box: DOMRect, count: number, random: () => number): Spot[] {
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.ceil(box.width));
  canvas.height = Math.max(1, Math.ceil(box.height));
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  // On a tall box the name takes two lines, else one.
  const tall = box.width / box.height < 1.1;
  const widths = (size: number) => {
    ctx.font = `400 ${size}px ${FACE}`;
    const a = ctx.measureText(WORDS[0]).width;
    ctx.font = `italic 400 ${size}px ${FACE}`;
    return { a, b: ctx.measureText(WORDS[1]).width, gap: size * 0.22 };
  };
  let size = tall ? Math.min(box.width * 0.27, box.height * 0.36) : Math.min(box.height * 0.62, box.width * 0.16);
  let m = widths(size);
  size *= Math.min(1, (box.width * 0.92) / (tall ? Math.max(m.a, m.b) : m.a + m.gap + m.b));
  m = widths(size);
  ctx.fillStyle = "#fff";
  const cx = box.width / 2;
  const cy = box.height / 2;
  if (tall) {
    ctx.font = `400 ${size}px ${FACE}`;
    ctx.fillText(WORDS[0], cx - m.a / 2, cy - size * 0.06);
    ctx.font = `italic 400 ${size}px ${FACE}`;
    ctx.fillText(WORDS[1], cx - m.b / 2, cy + size * 0.78);
  } else {
    const left = cx - (m.a + m.gap + m.b) / 2;
    const line = cy + size * 0.33;
    ctx.font = `400 ${size}px ${FACE}`;
    ctx.fillText(WORDS[0], left, line);
    ctx.font = `italic 400 ${size}px ${FACE}`;
    ctx.fillText(WORDS[1], left + m.a + m.gap, line);
  }
  // Every second pixel the letters cover, then random picks among them.
  const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  const filled: number[] = [];
  for (let y = 0; y < canvas.height; y += 2)
    for (let x = 0; x < canvas.width; x += 2) if (pixels[(y * canvas.width + x) * 4 + 3]! > 140) filled.push(x, y);
  if (!filled.length) return [];
  return Array.from({ length: count }, () => {
    const k = Math.floor(random() * (filled.length / 2)) * 2;
    const x = filled[k]!;
    return { x: box.left + x + random() * 2, y: box.top + filled[k + 1]! + random() * 2, across: x / canvas.width };
  });
}
