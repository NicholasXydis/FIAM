// The finale's QR code, worked out at build time in vite.config.ts.
declare module "virtual:qr" {
  // One string per row: 1 for a dark module, plus 2 inside an eye.
  const rows: string[];
  export default rows;
  // The favicon's mark for the code's centre, its hole set to the disc.
  export const MARK: string;
}
