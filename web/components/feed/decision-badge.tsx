import { CheckCircle2, XCircle, CircleHelp, Clock } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Decision } from "@/lib/contract/types"

export function DecisionBadge({
  decision,
  className,
}: {
  decision: Decision
  className?: string
}) {
  const config =
    decision === "qualified"
      ? {
          Icon: CheckCircle2,
          label: "Qualified",
          classes: "border-emerald-600/30 bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
        }
      : decision === "ineligible"
        ? {
            Icon: XCircle,
            label: "Ineligible",
            classes: "border-red-600/30 bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-300",
          }
        : decision === "uncertain"
          ? {
              Icon: CircleHelp,
              label: "Uncertain",
              classes: "border-amber-600/30 bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
            }
          : {
              Icon: Clock,
              label: "Not yet evaluated",
              classes: "border-border bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
            }

  const { Icon, label, classes } = config

  return (
    <span
      data-decision={decision ?? "null"}
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
