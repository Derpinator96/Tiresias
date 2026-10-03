import type { Metadata } from "next";
import { Canvas } from "@/components/playground/canvas";
import { Inspector } from "@/components/playground/inspector";

export const metadata: Metadata = {
  title: "Pipeline playground | Blind Tuner",
  description: "Replay of run_d1b30d38: the eight Blind Tuner stages with the figures from the run record.",
};

export default function Playground() {
  return (
    <Canvas>
      <Inspector />
    </Canvas>
  );
}
