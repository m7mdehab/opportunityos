"use client"

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import type { DashboardResponse, SourceHealth, PollNowResponse } from "@/lib/contract/types"
import { RefreshCw } from "lucide-react"

import { ThemeToggle } from "@/components/theme-toggle"

const STATS: Array<{ key: keyof DashboardResponse["series"][number]; label: string }> = [
  { key: "fetched", label: "Fetched" },
  { key: "unique_new", label: "New" },
  { key: "qualified", label: "Qualified" },
  { key: "high_fit", label: "High fit" },
  { key: "opened", label: "Opened" },
  { key: "labelled", label: "Labelled" },
  { key: "applied", label: "Applied" },
  // D3: how many rows a `hide`-mode filter removed from view today, so the
  // dashboard states a number in the same place it states every other
  // count rather than leaving it implicit in the feed.
  { key: "hidden_by_filters", label: "Hidden" },
]

function sourceSummary(sources: SourceHealth[] | null) {
  const summary = { healthy: 0, empty: 0, attention: 0, neverPolled: 0, disabled: 0 }
  for (const source of sources ?? []) {
    if (source.read_policy === "disabled") summary.disabled += 1
    else if (!source.last_poll) summary.neverPolled += 1
    else if (source.last_status === "ok") summary.healthy += 1
    else if (source.last_status === "parse_empty") summary.empty += 1
    else summary.attention += 1
  }
  return summary
}

export function HeaderStrip({
  dashboard,
  sources,
  onPollNow,
  polling,
  pollResult = null,
  onOpenHiddenReasons,
  metricPeriod,
  metricDate,
  onMetricPeriodChange,
  onMetricDateChange,
}: {
  dashboard: DashboardResponse | null
  sources: SourceHealth[] | null
  onPollNow: () => void
  polling: boolean
  pollResult?: PollNowResponse | null
  metricPeriod: "today" | "yesterday" | "date" | "all_time"
  metricDate: string
  onMetricPeriodChange: (period: "today" | "yesterday" | "date" | "all_time") => void
  onMetricDateChange: (date: string) => void
  /** C4: the HIDDEN number links to the reason -> count audit table. */
  onOpenHiddenReasons: () => void
}) {
  const today = dashboard?.series[0]
  const health = sourceSummary(sources)

  return (
    <header className="border-b border-border bg-card px-4 py-3 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold">OpportunityOS</h1>
          <p className="text-xs text-muted-foreground">
            {metricPeriod === "all_time"
              ? "All time"
              : metricPeriod === "yesterday"
                ? "Yesterday"
                : metricPeriod === "date"
                  ? `Specific date${today ? ` — ${today.date}` : ""}`
                  : `Today${today ? ` — ${today.date}` : ""}`}
          </p>
        </div>

        <dl
          aria-label="Today's dashboard numbers"
          className="flex flex-wrap gap-x-5 gap-y-2"
        >
          {STATS.map(({ key, label }) =>
            key === "hidden_by_filters" ? (
              <div key={key} className="text-center">
                <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  {label}
                </dt>
                <dd>
                  <button
                    type="button"
                    data-testid={`stat-${String(key)}`}
                    onClick={onOpenHiddenReasons}
                    className="rounded text-base font-semibold tabular-nums underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/50"
                  >
                    {today ? today[key] : "—"}
                  </button>
                </dd>
              </div>
            ) : (
              <div key={key} className="text-center">
                <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  {label}
                </dt>
                <dd data-testid={`stat-${String(key)}`} className="text-base font-semibold tabular-nums">
                  {today ? today[key] : "—"}
                </dd>
              </div>
            )
          )}
        </dl>

        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <label htmlFor="metric-period" className="sr-only">Metric period</label>
          <select
            id="metric-period"
            data-testid="metric-period"
            value={metricPeriod}
            onChange={(event) => onMetricPeriodChange(event.target.value as typeof metricPeriod)}
            className="h-9 rounded-lg border border-input bg-card px-2 text-xs"
          >
            <option value="today">Today</option>
            <option value="yesterday">Yesterday</option>
            <option value="date">Specific date</option>
            <option value="all_time">All time</option>
          </select>
          {metricPeriod === "date" && (
            <input
              aria-label="Metrics specific date"
              data-testid="metric-specific-date"
              type="date"
              value={metricDate}
              onChange={(event) => onMetricDateChange(event.target.value)}
              className="h-9 rounded-lg border border-input bg-card px-2 text-xs"
            />
          )}
        </div>

        <div className="flex min-w-0 max-w-full items-center gap-3">
          <div aria-label="Source health" data-testid="source-health-summary" className="grid grid-cols-5 gap-2 text-center text-[10px] leading-tight">
            {([
              ["healthy", "Healthy", health.healthy],
              ["empty", "Empty", health.empty],
              ["attention", "Attention", health.attention],
              ["never-polled", "Never polled", health.neverPolled],
              ["disabled", "Disabled", health.disabled],
            ] as const).map(([key, label, count]) => (
              <div key={key} data-testid={`source-health-${key}`}>
                <span className="block font-semibold tabular-nums">{count}</span>
                <span className="text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>

          <div className="flex flex-col items-end gap-1">
            <Tooltip>
              <TooltipTrigger
                type="button"
                onClick={onPollNow}
                disabled={polling}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm font-medium shadow-xs transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-50"
              >
                <RefreshCw
                  aria-hidden="true"
                  className={cn("size-3.5", polling && "animate-spin")}
                />
                {polling ? "Polling…" : "Poll now"}
              </TooltipTrigger>
              <TooltipContent>Queues currently due sources; cooldown and cadence still apply. Workers process them in the background.</TooltipContent>
            </Tooltip>
            {pollResult && (
              <p role="status" data-testid="poll-result" className="max-w-xs text-right text-[11px] text-muted-foreground">
                {pollResult.enqueued.length > 0
                  ? `Queued ${pollResult.enqueued.length} due source${pollResult.enqueued.length === 1 ? "" : "s"}. Workers are processing them in the background.`
                  : "Nothing new to queue — sources are already queued, cooling down, or not due."}
              </p>
            )}
          </div>

          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
