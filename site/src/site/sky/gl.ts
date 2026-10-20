// Each point is a soft round dot; seven floats: x, y, r, g, b, a, size.
export const FLOATS = 7;

// Places a point in pixels, sized for the screen's pixel ratio.
const VERTEX = /* glsl */ `#version 300 es
in vec2 aPos;
in vec4 aCol;
in float aSize;
uniform vec2 uRes;
uniform float uDpr;
out vec4 vCol;
void main() {
  vec2 c = aPos / uRes * 2.0 - 1.0;
  gl_Position = vec4(c.x, -c.y, 0.0, 1.0);
  gl_PointSize = aSize * uDpr;
  vCol = aCol;
}`;

// A gaussian falloff, so overlapping points add up to a glow.
const FRAGMENT = /* glsl */ `#version 300 es
precision mediump float;
in vec4 vCol;
out vec4 o;
void main() {
  vec2 p = gl_PointCoord - 0.5;
  float a = exp(-dot(p, p) * 18.0) * vCol.a;
  o = vec4(vCol.rgb * a, a);
}`;

// Draws a buffer of points, added together; null without WebGL2.
export function points(canvas: HTMLCanvasElement) {
  const gl = canvas.getContext("webgl2", { premultipliedAlpha: true, alpha: true, antialias: false });
  if (!gl) return null;
  const program = gl.createProgram();
  for (const [type, source] of [
    [gl.VERTEX_SHADER, VERTEX],
    [gl.FRAGMENT_SHADER, FRAGMENT],
  ] as const) {
    const shader = gl.createShader(type)!;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    gl.attachShader(program, shader);
  }
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
  gl.useProgram(program);
  const res = gl.getUniformLocation(program, "uRes");
  const ratio = gl.getUniformLocation(program, "uDpr");
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  // Position, colour and size, read from each run of seven floats.
  for (const [name, size, offset] of [
    ["aPos", 2, 0],
    ["aCol", 4, 8],
    ["aSize", 1, 24],
  ] as const) {
    const at = gl.getAttribLocation(program, name);
    gl.enableVertexAttribArray(at);
    gl.vertexAttribPointer(at, size, gl.FLOAT, false, FLOATS * 4, offset);
  }
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE);
  return {
    // Matches the canvas to the screen in device pixels.
    resize(w: number, h: number, dpr: number) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(res, w, h);
      gl.uniform1f(ratio, dpr);
    },
    // Clears and draws every point in the buffer.
    draw(data: Float32Array) {
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.POINTS, 0, data.length / FLOATS);
    },
  };
}
