import { CheckCircle2, XCircle, CircleHelp } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ConstraintOutcome } from "@/lib/contract/types"

/**
 * Renders a hard-constraint outcome. `UNKNOWN` must never be visually
 * confusable with `FAIL`: it gets its own icon (a question mark, not an X),
 * its own label ("Could not determine", not "Failed"), and its own colour
 * (amber, not red) — never colour alone.
 */
export function ConstraintOutcomeBadge({
  outcome,
  className,
}: {
  outcome: ConstraintOutcome
  className?: string
}) {
  const config = {
    PASS: {
      Icon: CheckCircle2,
      label: "Passed",
      classes: "border-emerald-500/30 bg-emerald-950/40 text-emerald-300 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-300",
    },
    FAIL: {
      Icon: XCircle,
      label: "Failed",
      classes: "border-red-500/30 bg-red-950/40 text-red-300 dark:border-red-500/30 dark:bg-red-950/40 dark:text-red-300",
    },
    UNKNOWN: {
      Icon: CircleHelp,
      label: "Could not determine",
      classes: "border-amber-500/30 bg-amber-950/40 text-amber-300 dark:border-amber-500/30 dark:bg-amber-950/40 dark:text-amber-300",
    },
  }[outcome]

  const { Icon, label, classes } = config

  return (
    <span
      data-outcome={outcome}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        classes,
        className
      )}
    >
      <Icon aria-hidden="true" className="size-3.5" />
      {label}
    </span>
  )
}
