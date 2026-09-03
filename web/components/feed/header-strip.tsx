"use client"

import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import type { DashboardResponse, SourceHealth } from "@/lib/contract/types"
import { RefreshCw } from "lucide-react"

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
  if (source.read_policy === "disabled") return "bg-gray-300 dark:bg-gray-700"
  if (!source.last_poll) return "bg-gray-400"
  if (source.last_status === "ok") return "bg-emerald-500"
  if (source.last_status === "parse_empty") return "bg-amber-500"
  return "bg-red-500"
}

export function HeaderStrip({
  dashboard,
  sources,
  onPollNow,
  polling,
  onOpenHiddenReasons,
}: {
  dashboard: DashboardResponse | null
  sources: SourceHealth[] | null
  onPollNow: () => void
  polling: boolean
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
            Today&apos;s numbers{today ? ` — ${today.date}` : ""}
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

        <div className="flex items-center gap-3">
          <ul aria-label="Source health" className="flex items-center gap-1.5">
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

          <Button onClick={onPollNow} disabled={polling} size="sm">
            <RefreshCw
              aria-hidden="true"
              className={cn("size-3.5", polling && "animate-spin")}
            />
            {polling ? "Polling…" : "Poll now"}
          </Button>
        </div>
      </div>
    </header>
  )
}
