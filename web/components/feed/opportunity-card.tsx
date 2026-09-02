"use client"

import { Badge } from "@/components/ui/badge"
import { DecisionBadge } from "@/components/feed/decision-badge"
import { filterTitle } from "@/components/feed/filter-labels"
import { AlertTriangle, EyeOff, Tag } from "lucide-react"
import { cn } from "@/lib/utils"
import type { OpportunityListItem } from "@/lib/contract/types"

const ACTION_STATE_LABEL: Record<string, string> = {
  submitted: "Applied",
  dismissed: "Dismissed",
  snoozed: "Snoozed",
}

export function OpportunityCard({
  opportunity,
  onOpen,
}: {
  opportunity: OpportunityListItem
  onOpen: () => void
}) {
  const o = opportunity
  const isHidden = o.hidden_by.length > 0

  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        aria-haspopup="dialog"
        data-testid={`opportunity-card-${o.id}`}
        data-hidden={isHidden}
        className={cn(
          "flex w-full flex-col gap-2 rounded-lg border p-4 text-left transition-colors",
          "hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:border-ring",
          // A row only ever appears here via the founder's own "Show
          // hidden" control (see page.tsx) — it must never blend in with
          // an ordinary visible card, so it gets a dashed border and a
          // muted fill in addition to the badge below (never colour or
          // border alone).
          isHidden
            ? "border-dashed border-amber-600/40 bg-amber-50/40 dark:bg-amber-950/20"
            : "border-border bg-card"
        )}
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-foreground">
              {o.title}
            </h2>
            <p className="truncate text-xs text-muted-foreground">
              {o.organization} · {o.source_id}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <span className="block text-lg font-semibold tabular-nums">
              {o.fit_score === null ? "—" : Math.round(o.fit_score)}
            </span>
            <span className="text-[11px] text-muted-foreground">fit score</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <DecisionBadge decision={o.decision} />
          <Badge variant="outline">{o.track}</Badge>
          {isHidden && (
            <Badge
              data-testid={`hidden-badge-${o.id}`}
              variant="outline"
              className="gap-1 border-amber-600/40 bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-200"
            >
              <EyeOff aria-hidden="true" className="size-3" />
              Hidden by {o.hidden_by.map(filterTitle).join(", ")}
            </Badge>
          )}
          {o.is_stale && (
            <Badge
              variant="outline"
              className="gap-1 border-amber-600/30 bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
            >
              <AlertTriangle aria-hidden="true" className="size-3" />
              Stale
            </Badge>
          )}
          {o.action_state && (
            <Badge variant="secondary">
              {ACTION_STATE_LABEL[o.action_state] ?? o.action_state}
            </Badge>
          )}
          {o.feedback_label && (
            <Badge variant="outline">{o.feedback_label.replaceAll("_", " ")}</Badge>
          )}
        </div>

        {o.flagged_by.length > 0 && (
          <div
            aria-label="Ranked or labelled by"
            className="flex flex-wrap items-center gap-1.5"
          >
            {o.flagged_by.map((filterId) => (
              <Badge
                key={filterId}
                data-testid={`flag-chip-${o.id}-${filterId}`}
                variant="outline"
                className="gap-1 text-muted-foreground"
              >
                <Tag aria-hidden="true" className="size-3" />
                {filterTitle(filterId)}
              </Badge>
            ))}
          </div>
        )}

        {o.top_reasons.length > 0 && (
          <ul className="space-y-0.5 text-xs text-muted-foreground">
            {o.top_reasons.slice(0, 3).map((r, i) => (
              <li key={i} className="truncate">
                • {r}
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap gap-x-4 text-[11px] text-muted-foreground">
          {o.deadline && <span>Deadline: {o.deadline}</span>}
          {o.posted_date && <span>Posted: {o.posted_date}</span>}
        </div>
      </button>
    </li>
  )
}
