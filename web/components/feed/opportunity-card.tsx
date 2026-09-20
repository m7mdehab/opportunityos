"use client"

import { forwardRef } from "react"
import { Badge } from "@/components/ui/badge"
import { DecisionBadge } from "@/components/feed/decision-badge"
import { filterTitle } from "@/components/feed/filter-labels"
import { AlertTriangle, EyeOff, Tag, Globe } from "lucide-react"
import { cn } from "@/lib/utils"
import { employerDomain, postedAge } from "@/lib/format/posted-age"
import type { OpportunityListItem } from "@/lib/contract/types"

const ACTION_STATE_LABEL: Record<string, string> = {
  submitted: "Applied",
  dismissed: "Dismissed",
  snoozed: "Snoozed",
}

const FEEDBACK_LABEL: Record<string, string> = {
  good_match: "Good match",
  bad_match: "Bad match",
  eligibility_wrong: "Not eligible",
  seniority_wrong: "Seniority mismatch",
  irrelevant_role: "Wrong track",
  source_quality_issue: "Source issue",
  duplicate_issue: "Duplicate",
  review_required: "Review required",
}

/** BRIEF-FR-006 C5: the founder's original complaint was "no card said
 * whether the job was remote, hybrid, or on-site" — `work_mode` is always
 * present on `OpportunityListItem` (never `undefined`), and `"unspecified"`
 * is a real, honest value (47.8% of real postings carry no work-mode
 * signal at all), rendered as "not stated" rather than hidden or blank. */
const WORK_MODE_LABEL: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "On-site",
  unspecified: "Work mode not stated",
}

function workModeLabel(workMode: string): string {
  return WORK_MODE_LABEL[workMode] ?? workMode
}

/** `[city, country]` joined, `null` when neither is known — never a bare
 * comma or an invented placeholder. */
function locationLabel(o: { location_city: string | null; location_country: string | null }): string | null {
  const parts = [o.location_city, o.location_country].filter((p): p is string => Boolean(p))
  return parts.length > 0 ? parts.join(", ") : null
}

/** `ref` is exposed so `page.tsx`'s `j`/`k` keyboard navigation can move
 * real DOM focus onto a card (required behaviour #4: "focus is visible and
 * managed" — an actual `HTMLButtonElement.focus()` call, not a CSS-only
 * highlight that leaves the browser's own focus elsewhere). */
export const OpportunityCard = forwardRef<
  HTMLButtonElement,
  {
    opportunity: OpportunityListItem
    onOpen: () => void
    /** Keyboard-navigation cursor (`j`/`k` in `page.tsx`), independent of
     * whether the drawer is open. Purely a visual/focus-management concern
     * — never sent to the API. */
    keyboardFocused?: boolean
  }
>(function OpportunityCard({ opportunity, onOpen, keyboardFocused = false }, ref) {
  const o = opportunity
  const isHidden = o.hidden_by.length > 0
  const domain = employerDomain(o.source_url)
  const age = postedAge(o.posted_date)
  const location = locationLabel(o)

  return (
    <li className="h-full">
      <article className="flex h-full flex-col rounded-lg border border-border bg-card">
      <button
        ref={ref}
        type="button"
        onClick={onOpen}
        aria-haspopup="dialog"
        aria-current={keyboardFocused ? "true" : undefined}
        data-testid={`opportunity-card-${o.id}`}
        data-hidden={isHidden}
        data-keyboard-focused={keyboardFocused}
        className={cn(
          "flex min-h-0 flex-1 w-full flex-col gap-2 p-4 text-left transition-colors",
          "hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:border-ring",
          // A row only ever appears here via the founder's own "Show
          // hidden" control (see page.tsx) — it must never blend in with
          // an ordinary visible card, so it gets a dashed border and a
          // muted fill in addition to the badge below (never colour or
          // border alone).
          isHidden
            ? "border-dashed border-amber-500/40 bg-amber-950/20 dark:bg-amber-950/20"
            : "border-transparent",
          // The keyboard cursor also gets its own ring even when the
          // browser's native focus-visible heuristic doesn't apply (e.g.
          // Playwright's programmatic `.focus()` in some browser/OS
          // combinations) — belt and suspenders for "focus is visible".
          keyboardFocused && "ring-2 ring-ring/60 border-ring"
        )}
      >
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2">
          <div className="min-w-0">
            <h2 title={o.title} className="line-clamp-2 text-sm font-semibold leading-5 text-foreground">
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
          <Badge
            variant="outline"
            data-testid={`work-mode-${o.id}`}
            className={cn(
              "gap-1",
              o.work_mode === "unspecified" && "text-muted-foreground"
            )}
          >
            <Globe aria-hidden="true" className="size-3" />
            {workModeLabel(o.work_mode)}
          </Badge>
          {location && (
            <Badge variant="outline" data-testid={`location-${o.id}`}>
              {location}
            </Badge>
          )}
          {o.family_size !== null && o.family_size > 1 && (
            <Badge variant="outline" data-testid={`family-size-${o.id}`}>
              — {o.family_size} locations
            </Badge>
          )}
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
            <Badge variant="outline">
              {FEEDBACK_LABEL[o.feedback_label] ?? o.feedback_label.replaceAll("_", " ")}
            </Badge>
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

        <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground">
          {age && <span data-testid={`posted-age-${o.id}`}>{age}</span>}
          {o.deadline && <span>Deadline: {o.deadline}</span>}
          {domain && (
            <span className="inline-flex items-center gap-1">
              <Globe aria-hidden="true" className="size-3" />
              {domain}
            </span>
          )}
        </div>
      </button>
      <footer className="flex items-center justify-between gap-2 border-t border-border/70 px-4 py-2 text-[11px] text-muted-foreground">
        <span className="truncate">{domain ?? "Original source"}</span>
        <a
          data-testid={`quick-apply-${o.id}`}
          href={o.source_url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Quick apply to ${o.title} at ${o.organization}`}
          className="shrink-0 font-medium text-primary underline underline-offset-4 hover:text-primary/80"
        >
          Quick apply ↗
        </a>
      </footer>
      </article>
    </li>
  )
})
