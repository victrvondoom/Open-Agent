"use client";

import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

// Shared geometry singletons to prevent allocation during renders
const sharedBoxGeo = new THREE.BoxGeometry(0.8, 0.8, 0.8);
const sharedEdgesGeo = new THREE.EdgesGeometry(sharedBoxGeo);
const sharedLineMat = new THREE.LineBasicMaterial({ color: "#231f1d" });


function VoxelCube({
  position,
  color,
  speedX = 0.005,
  speedY = 0.008,
}: {
  position: [number, number, number];
  color: string;
  speedX?: number;
  speedY?: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);

  useFrame((_, delta) => {
    if (!meshRef.current) return;
    meshRef.current.rotation.x += delta * 0.25;
    meshRef.current.rotation.y += delta * 0.35;
  });

  return (
    <mesh ref={meshRef} position={position} geometry={sharedBoxGeo}>
      <meshStandardMaterial color={color} roughness={0.35} metalness={0.15} />
      {sharedEdgesGeo && sharedLineMat && (
        <lineSegments geometry={sharedEdgesGeo} material={sharedLineMat} />
      )}
    </mesh>
  );
}

const voxelItems = [
  { position: [-4.2, 1.8, -4] as [number, number, number], color: "#ea580c" },
  { position: [4.5, -1.2, -5] as [number, number, number], color: "#f59e0b" },
  { position: [-2.5, -2.8, -3.5] as [number, number, number], color: "#16a34a" },
  { position: [3.8, 2.5, -6] as [number, number, number], color: "#2563eb" },
];

export function FloatingShapes() {
  return (
    <>
      {voxelItems.map((v, i) => (
        <VoxelCube key={i} position={v.position} color={v.color} />
      ))}
    </>
  );
}

