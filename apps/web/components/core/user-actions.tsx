"use client";

import { useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

function subscribeTheme(notify: () => void) {
  const observer = new MutationObserver(notify);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}

export function UserActions() {
  const router = useRouter();
  const dark = useSyncExternalStore(subscribeTheme, () => document.documentElement.classList.contains("dark"), () => false);
  const [error, setError] = useState("");
  function theme() {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      /* Private browsing can disable storage. */
    }
  }
  async function logout() {
    try {
      const response = await fetch("/api/auth/logout", {
        method: "POST",
        headers: { "X-DocuHive-CSRF": "1" },
      });
      if (!response.ok && response.status !== 401) {
        setError("Could not sign out. Try again.");
        return;
      }
      router.replace("/login");
      router.refresh();
    } catch {
      setError("Could not sign out. Try again.");
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button type="button" variant="ghost" onClick={theme} aria-pressed={dark}>
        Dark theme
      </Button>
      <Button type="button" variant="secondary" onClick={logout}>
        Sign out
      </Button>
      {error && (
        <span role="alert" className="text-xs text-danger">
          {error}
        </span>
      )}
    </div>
  );
}
