"use client"

import { forwardRef } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { filterTitle } from "@/components/feed/filter-labels"
import { AlertTriangle, EyeOff, Globe } from "lucide-react"
import { cn } from "@/lib/utils"
import { employerDomain, postedAge } from "@/lib/format/posted-age"
import type { OpportunityListItem } from "@/lib/contract/types"

const ACTION_STATE_LABEL: Record<string, string> = {
  submitted: "Applied",
  applied: "Applied",
  saved: "Saved",
  rejected_by_founder: "Rejected",
  dismissed: "Dismissed",
  snoozed: "Snoozed",
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
    selected?: boolean
    onSelectedChange?: (selected: boolean) => void
    onTriageAction?: (action: "save" | "mark_applied" | "reject") => void
    triagePending?: boolean
    triageError?: string | null
  }
>(function OpportunityCard({
  opportunity,
  onOpen,
  keyboardFocused = false,
  selected = false,
  onSelectedChange,
  onTriageAction,
  triagePending = false,
  triageError = null,
}, ref) {
  const o = opportunity
  const isHidden = o.hidden_by.length > 0
  const domain = employerDomain(o.source_url)
  const age = postedAge(o.posted_date)
  const location = locationLabel(o)
  const canTriage =
    o.track === "employment" &&
    (o.action_state === null || o.action_state === "to_review") &&
    onTriageAction !== undefined

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
            <p className="truncate text-xs text-muted-foreground">{o.organization}</p>
          </div>
          <span className="shrink-0 rounded-full border border-border px-2 py-1 text-[11px] text-muted-foreground">
            {o.founder_geo_state === "eligible" ? "Eligible" : o.founder_geo_state === "likely_eligible" ? "Likely eligible" : o.founder_geo_state === "ineligible" ? "Not eligible" : "Eligibility review"}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {o.title_family && <Badge variant="outline">{o.title_family.replaceAll("_", " ")}</Badge>}
          {o.seniority_level !== "unspecified" && <Badge variant="outline">{o.seniority_level.replaceAll("_", " ")}</Badge>}
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
            <Badge variant="outline">{o.feedback_label.replaceAll("_", " ")}</Badge>
          )}
        </div>

        {(o.recommendation_reasons?.length || o.top_reasons.length) > 0 && (
          <div>
            <p className="text-[11px] font-medium text-foreground">Why it fits</p>
          <ul className="space-y-0.5 text-xs text-muted-foreground">
            {(o.recommendation_reasons?.length ? o.recommendation_reasons : o.top_reasons).slice(0, 3).map((r, i) => (
              <li key={i} className="truncate">
                • {r}
              </li>
            ))}
          </ul>
          </div>
        )}

        <p className="text-[11px] text-muted-foreground">
          {o.application_access === "direct_free" ? "Direct application" : o.application_access === "free_intermediary" ? "Free application route" : o.application_access === "free_account_required" ? "Account required" : o.application_access === "premium_or_gated" ? "Gated application" : o.application_access === "manual_only" ? "Manual application" : "Application access not verified"}
        </p>

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
        <div className="flex min-w-0 items-center gap-2">
          {onSelectedChange && (
            <label className="flex cursor-pointer items-center gap-1.5 whitespace-nowrap">
              <input
                aria-label={`Select ${o.title}`}
                type="checkbox"
                checked={selected}
                onChange={(event) => onSelectedChange(event.target.checked)}
                className="size-4 accent-primary"
              />
              Select
            </label>
          )}
          <span className="truncate">{domain ?? "Original source"}</span>
        </div>
        <a
          data-testid={`quick-apply-${o.id}`}
          href={o.source_url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Quick apply to ${o.title} at ${o.organization}`}
          className="shrink-0 font-medium text-primary underline underline-offset-4 hover:text-primary/80"
        >
          Apply ↗
        </a>
      </footer>
      <div
        role={canTriage ? "group" : undefined}
        aria-label={canTriage ? `Review actions for ${o.title}` : undefined}
        className="flex min-h-9 flex-wrap items-center gap-2 border-t border-border/70 px-4 py-1"
      >
        {canTriage && (
          <>
            <Button type="button" size="sm" variant="outline" data-testid={`quick-save-${o.id}`} disabled={triagePending} onClick={() => onTriageAction("save")}>Save</Button>
            <Button type="button" size="sm" variant="outline" data-testid={`quick-mark-applied-${o.id}`} disabled={triagePending} onClick={() => onTriageAction("mark_applied")}>Mark Applied</Button>
            <Button type="button" size="sm" variant="destructive" data-testid={`quick-reject-${o.id}`} disabled={triagePending} onClick={() => onTriageAction("reject")}>Not for me</Button>
            {triagePending && <span role="status" className="text-xs text-muted-foreground">Updating…</span>}
            {triageError && <span role="alert" className="text-xs text-destructive">{triageError}</span>}
          </>
        )}
      </div>
      </article>
    </li>
  )
})
