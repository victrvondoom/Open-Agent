"use client";

import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ParticleField } from "./ParticleField";
import { FloatingShapes } from "./FloatingShapes";

export function SceneBackground() {
  return (
    <div className="fixed inset-0 -z-10 pointer-events-none">
      <ErrorBoundary>
        <Canvas
          camera={{ position: [0, 0, 12], fov: 50, near: 0.1, far: 40 }}
          gl={{
            antialias: false,
            alpha: true,
            powerPreference: "low-power",
            stencil: false,
            depth: true,
          }}
          dpr={1}
        >
          <ambientLight intensity={0.9} color="#fffcf5" />
          <directionalLight position={[10, 14, 8]} intensity={1.0} color="#fff9ed" />
          <Suspense fallback={null}>
            <ParticleField />
            <FloatingShapes />
          </Suspense>
        </Canvas>
      </ErrorBoundary>
    </div>
  );
}

