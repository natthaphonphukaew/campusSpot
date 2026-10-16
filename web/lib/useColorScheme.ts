"use client";

import { useSyncExternalStore } from "react";
import type { Scheme } from "./scale";

const QUERY = "(prefers-color-scheme: dark)";

function subscribe(onChange: () => void) {
  const mq = window.matchMedia(QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

/** โหมดสว่าง/มืดของเครื่องผู้ใช้ เปลี่ยนตามทันทีเมื่อผู้ใช้สลับโหมด */
export function useColorScheme(): Scheme {
  return useSyncExternalStore(
    subscribe,
    () => (window.matchMedia(QUERY).matches ? "dark" : "light"),
    () => "light",
  );
}
