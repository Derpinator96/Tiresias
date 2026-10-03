import type { Metadata } from "next";
import { Canvas } from "@/components/playground/canvas";
import { Inspector } from "@/components/playground/inspector";

export const metadata: Metadata = {
  title: "Pipeline playground | Tiresias",
  description: "The eight Tiresias stages with one run's figures: the asked question's bundle, or the run record.",
};

export default function Playground() {
  return (
    <Canvas>
      <Inspector />
    </Canvas>
  );
}
