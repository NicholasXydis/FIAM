import { Agents } from "./agents";
import { Capacity } from "./capacity";
import { Costs } from "./costs";
import { Crowd } from "./crowd";
import { Edge } from "./edge";
import { Finale } from "./finale";
import { Honesty } from "./honesty";
import { Idea } from "./idea";
import { Intro } from "./intro";
import { Neutral } from "./neutral";
import { Race } from "./race";
import { September } from "./september";
import type { Scene, World } from "./scene";
import { Universe } from "./universe";

export const scenes = (w: World): Scene[] => [
  new Intro(w),
  new Universe(w),
  new Idea(w),
  new Race(w),
  new Neutral(w),
  new Costs(w),
  new Edge(w),
  new Capacity(w),
  new Crowd(w),
  new Agents(w),
  new September(w),
  new Honesty(w),
  new Finale(w),
];
