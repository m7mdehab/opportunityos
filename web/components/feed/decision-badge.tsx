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
          classes: "border-emerald-500/30 bg-emerald-950/40 text-emerald-300 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-300",
        }
      : decision === "ineligible"
        ? {
            Icon: XCircle,
            label: "Ineligible",
            classes: "border-red-500/30 bg-red-950/40 text-red-300 dark:border-red-500/30 dark:bg-red-950/40 dark:text-red-300",
          }
        : decision === "uncertain"
          ? {
              Icon: CircleHelp,
              label: "Uncertain",
              classes: "border-amber-500/30 bg-amber-950/40 text-amber-300 dark:border-amber-500/30 dark:bg-amber-950/40 dark:text-amber-300",
            }
          : {
              Icon: Clock,
              label: "Not yet evaluated",
              classes: "border-border bg-muted/60 text-muted-foreground",
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
