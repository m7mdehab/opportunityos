"use client"

import { cn } from "@/lib/utils"

/**
 * A minimal accessible on/off switch (native `role="switch"` button, no
 * external primitive needed). Matches the sizing/focus idiom of the other
 * `components/ui/*` primitives (see `checkbox.tsx`) rather than pulling in
 * a new dependency for one control.
 */
function Switch({
  checked,
  onCheckedChange,
  disabled,
  id,
  className,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledBy,
}: {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  disabled?: boolean
  id?: string
  className?: string
  "aria-label"?: string
  "aria-labelledby"?: string
}) {
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledBy}
      data-slot="switch"
      data-state={checked ? "checked" : "unchecked"}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border border-transparent bg-input shadow-xs transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary dark:bg-input/60 dark:data-[state=checked]:bg-primary",
        className
      )}
    >
      <span
        data-slot="switch-thumb"
        aria-hidden="true"
        className={cn(
          "pointer-events-none block size-4 rounded-full bg-background shadow-sm transition-transform data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0.5"
        )}
        data-state={checked ? "checked" : "unchecked"}
      />
    </button>
  )
}

export { Switch }
