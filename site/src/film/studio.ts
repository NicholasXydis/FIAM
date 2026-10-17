import * as THREE from "three";
import { mix } from "./ease";

const PEARL = new THREE.Color(0xeceaf1);
const DUSK = new THREE.Color(0x0d0a1a);
export const NIGHT = new THREE.Color(0x03040b);

// A seamless photographer's sweep: a floor that curves up into a wall, so there is no horizon.
function sweep() {
  const profile: [number, number][] = [];
  for (let i = 0; i <= 24; i++) profile.push([60 - i * 2.9, 0]);
  for (let i = 1; i <= 32; i++) {
    const a = (i / 32) * (Math.PI / 2);
    profile.push([-10 - 16 * Math.sin(a), 16 - 16 * Math.cos(a)]);
  }
  profile.push([-26, 90]);
  const pos: number[] = [];
  const index: number[] = [];
  profile.forEach(([z, y], i) => {
    pos.push(-120, y, z, 120, y, z);
    if (i) index.push(2 * i - 2, 2 * i - 1, 2 * i, 2 * i - 1, 2 * i + 1, 2 * i);
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(index);
  g.computeVertexNormals();
  return g;
}

// A soft dark pool under an object, where the floor meets it.
export function contact(radius: number, strength = 0.5) {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grad.addColorStop(0, `rgba(20,16,30,${strength})`);
  grad.addColorStop(0.45, `rgba(20,16,30,${strength * 0.35})`);
  grad.addColorStop(1, "rgba(20,16,30,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  const m = new THREE.Mesh(
    new THREE.PlaneGeometry(radius * 2, radius * 2),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }),
  );
  m.rotation.x = -Math.PI / 2;
  m.position.y = 0.004;
  m.renderOrder = -1;
  return m;
}

// The bright room the product shots live in: the sweep, a soft key light with real shadows, a sky
// fill, and fog in the same colour so the far floor melts into the wall.
export class Studio {
  group = new THREE.Group();
  key: THREE.DirectionalLight;
  fill: THREE.HemisphereLight;
  rim: THREE.DirectionalLight;
  private floor: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>;
  private color = new THREE.Color();
  private fog = new THREE.Fog(PEARL, 30, 110);

  constructor(env: THREE.Texture) {
    this.floor = new THREE.Mesh(
      sweep(),
      new THREE.MeshStandardMaterial({ color: PEARL, roughness: 0.94, envMap: env, envMapIntensity: 0.3 }),
    );
    this.floor.receiveShadow = true;
    this.key = new THREE.DirectionalLight(0xfffaf2, 2.4);
    this.key.position.set(-7, 16, 9);
    this.key.castShadow = true;
    this.key.shadow.mapSize.set(2048, 2048);
    this.key.shadow.radius = 14;
    this.key.shadow.blurSamples = 24;
    this.key.shadow.bias = -0.0004;
    const cam = this.key.shadow.camera;
    cam.left = cam.bottom = -9;
    cam.right = cam.top = 9;
    cam.near = 1;
    cam.far = 50;
    this.fill = new THREE.HemisphereLight(0xffffff, 0xd9d4e6, 0.5);
    this.rim = new THREE.DirectionalLight(0xdcd2ff, 0.8);
    this.rim.position.set(8, 6, -10);
    this.group.add(this.floor, this.key, this.key.target, this.fill, this.rim);
  }

  // Day is 1 for the bright room and 0 for the violet dusk the agents work in; night then sinks the
  // whole room into the dark the future is shown against.
  light(scene: THREE.Scene, day: number, jitter = [0, 0], night = 0) {
    this.color.copy(DUSK).lerp(PEARL, day).lerp(NIGHT, night);
    this.fog.near = mix(30, 400, night);
    this.fog.far = mix(110, 1500, night);
    this.floor.material.depthWrite = night === 0;
    this.floor.material.color.copy(this.color);
    this.fog.color.copy(this.color);
    scene.fog = this.fog;
    scene.background = this.color;
    this.key.intensity = mix(0.25, 2.4, day);
    this.key.position.set(-7 + jitter[0], 16, 9 + jitter[1]);
    this.fill.intensity = mix(0.08, 0.5, day);
    this.rim.intensity = mix(1.6, 0.8, day);
    this.floor.material.envMapIntensity = mix(0.05, 0.3, day);
    scene.environmentIntensity = mix(0.22, 1, day);
  }
}
