"use client"

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
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

function sourceDotColor(source: SourceHealth): string {
  if (source.read_policy === "disabled") return "bg-zinc-700"
  if (!source.last_poll) return "bg-zinc-500"
  if (source.last_status === "ok") return "bg-emerald-500"
  if (source.last_status === "parse_empty") return "bg-amber-500"
  return "bg-rose-500"
}

export function HeaderStrip({
  dashboard,
  sources,
  onPollNow,
  polling,
  pollResult,
  onOpenHiddenReasons,
}: {
  dashboard: DashboardResponse | null
  sources: SourceHealth[] | null
  onPollNow: () => void
  polling: boolean
  pollResult: PollNowResponse | null
  /** C4: the HIDDEN number links to the reason -> count audit table. */
  onOpenHiddenReasons: () => void
}) {
  const today = dashboard?.series[0]

  return (
    <header className="border-b border-border bg-card px-4 py-3 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold">OpportunityOS</h1>
          <p className="text-xs text-muted-foreground">
            Today&apos;s numbers{today ? ` â€” ${today.date}` : ""}
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
                    {today ? today[key] : "â€”"}
                  </button>
                </dd>
              </div>
            ) : (
              <div key={key} className="text-center">
                <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  {label}
                </dt>
                <dd data-testid={`stat-${String(key)}`} className="text-base font-semibold tabular-nums">
                  {today ? today[key] : "â€”"}
                </dd>
              </div>
            )
          )}
        </dl>

        <div className="flex min-w-0 max-w-full items-center gap-3">
          <ul
            aria-label="Source health"
            className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto py-1"
          >
            {(sources ?? []).map((s) => (
              <li key={s.source_id}>
                <Tooltip>
                  <TooltipTrigger
                    aria-label={`${s.name}: ${
                      s.read_policy === "disabled"
                        ? "read disabled by policy"
                        : s.last_poll
                          ? `last status ${s.last_status}`
                          : "never polled"
                    }`}
                    className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                  >
                    <span
                      aria-hidden="true"
                      className={cn("inline-block size-2.5 rounded-full", sourceDotColor(s))}
                    />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="font-medium">{s.name}</p>
                    <p>
                      {s.read_policy === "disabled"
                        ? "Read disabled by policy"
                        : s.last_poll
                          ? `Last poll: ${s.last_poll} (${s.last_status}, ${s.last_record_count ?? 0} records)`
                          : "Never polled"}
                    </p>
                  </TooltipContent>
                </Tooltip>
              </li>
            ))}
          </ul>

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
                  : "Nothing new to queue â€” sources are already queued, cooling down, or not due."}
              </p>
            )}
          </div>

          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
