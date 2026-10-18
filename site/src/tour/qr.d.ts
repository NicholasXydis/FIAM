// The finale's QR code, worked out at build time in vite.config.ts.
declare module "virtual:qr" {
  // One string per row: 1 for a dark module, plus 2 inside an eye.
  const rows: string[];
  export default rows;
}
