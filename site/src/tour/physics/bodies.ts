import * as THREE from "three";

// Gravity, in units per second squared.
const G = -18;
// The world's up, for finding which face points up.
const UP = new THREE.Vector3(0, 1, 0);
// The world's down, for a face that points down.
const DOWN = new THREE.Vector3(0, -1, 0);
// The three axes of a box before it turns.
const AXES = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)];
// Scratch: one box corner; all scratch is reused, never reallocated.
const corner = new THREE.Vector3();
// Scratch: the lowest corner found this substep.
const low = new THREE.Vector3();
// Scratch: from the centre to the corner that hit.
const lever = new THREE.Vector3();
// Scratch: the axis the box is spinning about.
const spin = new THREE.Vector3();
// Scratch: one box axis turned into world space.
const axis = new THREE.Vector3();
// Scratch: the box axis nearest to straight up or down.
const best = new THREE.Vector3();
// Scratch: the turn that rolls the box onto a face.
const fix = new THREE.Vector3();
// Scratch: one substep's small turn as a quaternion.
const dq = new THREE.Quaternion();

// A box that falls, tumbles and rests, turned by its first corner down.
export class Body {
  velocity = new THREE.Vector3();
  angular = new THREE.Vector3();
  asleep = true;
  // Called at each falling hit with its downward speed.
  onHit?: (impact: number) => void;
  private half: THREE.Vector3;

  // Takes the mesh, its unscaled size and the floor's height.
  constructor(
    public mesh: THREE.Object3D,
    size: THREE.Vector3,
    public floor = 0,
  ) {
    this.half = size.clone().multiplyScalar(0.5);
  }

  // Throws the box with a velocity and a spin, waking it.
  push(velocity: THREE.Vector3, angular: THREE.Vector3) {
    this.velocity.copy(velocity);
    this.angular.copy(angular);
    this.asleep = false;
  }

  // Advances the box in four substeps a frame, then sleeps it once still.
  step(dt: number) {
    if (this.asleep) return;
    const sub = 4;
    const h = dt / sub;
    // Each substep falls, meets the floor and settles.
    for (let s = 0; s < sub; s++) {
      // Falls, then moves and turns by its spin.
      this.velocity.y += G * h;
      this.mesh.position.addScaledVector(this.velocity, h);
      const speed = this.angular.length();
      // Turn only when there is spin enough to measure.
      if (speed > 1e-5) {
        dq.setFromAxisAngle(spin.copy(this.angular).divideScalar(speed), speed * h);
        this.mesh.quaternion.premultiply(dq);
      }
      // Finds the lowest of the eight corners in world space.
      let lowest = Infinity;
      // Each bit of i picks one side of the box on one axis.
      for (let i = 0; i < 8; i++) {
        corner.set(
          i & 1 ? this.half.x : -this.half.x,
          i & 2 ? this.half.y : -this.half.y,
          i & 4 ? this.half.z : -this.half.z,
        );
        corner.multiply(this.mesh.scale).applyQuaternion(this.mesh.quaternion).add(this.mesh.position);
        // Keep the lowest corner seen so far.
        if (corner.y < lowest) {
          lowest = corner.y;
          low.copy(corner);
        }
      }
      // A corner under the floor lifts the box back out.
      if (lowest >= this.floor) continue;
      this.mesh.position.y += this.floor - lowest;
      // A falling hit bounces at 32% and gets spin from the corner that hit.
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
      // Floor friction, then a roll onto the nearest face.
      this.velocity.x *= 1 - 3 * h;
      this.velocity.z *= 1 - 3 * h;
      this.angular.multiplyScalar(1 - 3.2 * h);
      this.settle(h);
    }
    // It sleeps once still and less than 3 above the floor.
    const still = this.velocity.lengthSq() < 0.002 && this.angular.lengthSq() < 0.002;
    if (still && this.mesh.position.y < this.floor + 3) this.asleep = true;
  }

  // On the floor it rolls to its nearest face, not balancing on an edge.
  private settle(h: number) {
    let lean = -1;
    // Find the box axis most nearly straight up or down.
    for (const a of AXES) {
      axis.copy(a).applyQuaternion(this.mesh.quaternion);
      const d = Math.abs(axis.dot(UP));
      // Keep the most upright axis so far.
      if (d > lean) {
        lean = d;
        best.copy(axis);
      }
    }
    fix.crossVectors(best, best.dot(UP) > 0 ? UP : DOWN);
    this.angular.addScaledVector(fix, 90 * h);
  }
}
