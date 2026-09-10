"use client"

import { useEffect, useSyncExternalStore } from "react"
import { Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback)
  return () => window.removeEventListener("storage", callback)
}

function getSnapshot(): "midnight" | "light" {
  try {
    return localStorage.getItem("opos_theme") === "light" ? "light" : "midnight"
  } catch {
    return "midnight"
  }
}

function getServerSnapshot(): "midnight" | "light" {
  return "midnight"
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)

  useEffect(() => {
    if (theme === "light") {
      document.documentElement.classList.remove("dark")
      document.documentElement.classList.add("light")
      document.documentElement.style.colorScheme = "light"
    } else {
      document.documentElement.classList.remove("light")
      document.documentElement.classList.add("dark")
      document.documentElement.style.colorScheme = "dark"
    }
  }, [theme])

  const toggle = () => {
    try {
      const next = theme === "midnight" ? "light" : "midnight"
      localStorage.setItem("opos_theme", next)
      window.dispatchEvent(new Event("storage"))
    } catch {
      // ignore
    }
  }

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={toggle}
      title={theme === "midnight" ? "Switch to Light mode" : "Switch to Midnight mode"}
      aria-label={theme === "midnight" ? "Switch to Light mode" : "Switch to Midnight mode"}
      className="text-muted-foreground hover:text-foreground"
    >
      {theme === "midnight" ? (
        <Moon className="size-4" aria-hidden="true" />
      ) : (
        <Sun className="size-4" aria-hidden="true" />
      )}
    </Button>
  )
}
