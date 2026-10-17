import * as THREE from "three";

const G = -18;
const UP = new THREE.Vector3(0, 1, 0);
const DOWN = new THREE.Vector3(0, -1, 0);
const AXES = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)];
const corner = new THREE.Vector3();
const low = new THREE.Vector3();
const lever = new THREE.Vector3();
const spin = new THREE.Vector3();
const axis = new THREE.Vector3();
const best = new THREE.Vector3();
const fix = new THREE.Vector3();
const dq = new THREE.Quaternion();

// A box that falls, tumbles and comes to rest on the floor: gravity, restitution, friction and a
// torque from whichever corner hits first.
export class Body {
  velocity = new THREE.Vector3();
  angular = new THREE.Vector3();
  asleep = true;
  onHit?: (impact: number) => void;
  private half: THREE.Vector3;

  constructor(
    public mesh: THREE.Object3D,
    size: THREE.Vector3,
    public floor = 0,
  ) {
    this.half = size.clone().multiplyScalar(0.5);
  }

  push(velocity: THREE.Vector3, angular: THREE.Vector3) {
    this.velocity.copy(velocity);
    this.angular.copy(angular);
    this.asleep = false;
  }

  step(dt: number) {
    if (this.asleep) return;
    const sub = 4;
    const h = dt / sub;
    for (let s = 0; s < sub; s++) {
      this.velocity.y += G * h;
      this.mesh.position.addScaledVector(this.velocity, h);
      const speed = this.angular.length();
      if (speed > 1e-5) {
        dq.setFromAxisAngle(spin.copy(this.angular).divideScalar(speed), speed * h);
        this.mesh.quaternion.premultiply(dq);
      }
      let lowest = Infinity;
      for (let i = 0; i < 8; i++) {
        corner.set(
          i & 1 ? this.half.x : -this.half.x,
          i & 2 ? this.half.y : -this.half.y,
          i & 4 ? this.half.z : -this.half.z,
        );
        corner.multiply(this.mesh.scale).applyQuaternion(this.mesh.quaternion).add(this.mesh.position);
        if (corner.y < lowest) {
          lowest = corner.y;
          low.copy(corner);
        }
      }
      if (lowest >= this.floor) continue;
      this.mesh.position.y += this.floor - lowest;
      if (this.velocity.y < 0) {
        lever.copy(low).sub(this.mesh.position);
        const impact = -this.velocity.y;
        this.onHit?.(impact);
        this.velocity.y = impact * 0.32;
        this.velocity.x *= 0.82;
        this.velocity.z *= 0.82;
        this.angular.x += -lever.z * impact * 0.35;
        this.angular.z += lever.x * impact * 0.35;
        this.angular.multiplyScalar(0.7);
      }
      this.velocity.x *= 1 - 3 * h;
      this.velocity.z *= 1 - 3 * h;
      this.angular.multiplyScalar(1 - 3.2 * h);
      this.settle(h);
    }
    const still = this.velocity.lengthSq() < 0.002 && this.angular.lengthSq() < 0.002;
    if (still && this.mesh.position.y < this.floor + 3) this.asleep = true;
  }

  // On the floor, a box rolls onto its nearest face instead of balancing on an edge.
  private settle(h: number) {
    let lean = -1;
    for (const a of AXES) {
      axis.copy(a).applyQuaternion(this.mesh.quaternion);
      const d = Math.abs(axis.dot(UP));
      if (d > lean) {
        lean = d;
        best.copy(axis);
      }
    }
    fix.crossVectors(best, best.dot(UP) > 0 ? UP : DOWN);
    this.angular.addScaledVector(fix, 90 * h);
  }
}
