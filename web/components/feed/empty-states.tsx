import { Button } from "@/components/ui/button"
import { AlertTriangle, Inbox, FileWarning, TimerReset } from "lucide-react"

function EmptyStateShell({
  icon: Icon,
  title,
  children,
  tone = "default",
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>
  title: string
  children: React.ReactNode
  tone?: "default" | "warning"
}) {
  return (
    <div
      role="status"
      className={
        "mx-auto flex max-w-lg flex-col items-center gap-3 rounded-lg border p-8 text-center " +
        (tone === "warning"
          ? "border-amber-500/30 bg-amber-950/40 text-foreground"
          : "border-border bg-card text-foreground")
      }
    >
      <Icon
        aria-hidden="true"
        className={
          "size-8 " +
          (tone === "warning" ? "text-amber-400" : "text-muted-foreground")
        }
      />
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="text-sm text-muted-foreground">{children}</div>
    </div>
  )
}

export function NoTruthPackState({ path }: { path: string }) {
  return (
    <div
      role="status"
      data-testid="truth-pack-warning"
      className="mb-4 flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-950/40 p-4"
    >
      <FileWarning aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-amber-400" />
      <div>
        <h2 className="text-sm font-semibold text-foreground">Founder profile not loaded</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          You can browse the live opportunity feed, but qualification, fit scores, and tailored
          artifacts stay disabled until a validated private truth pack is loaded at{" "}
          <code className="rounded bg-muted px-1">{path}</code>.
        </p>
      </div>
    </div>
  )
}

export function InvalidTruthPackState({
  findings,
}: {
  findings: string[]
}) {
  return (
    <div
      role="alert"
      data-testid="truth-pack-warning"
      className="mb-4 flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-950/40 p-4"
    >
      <AlertTriangle aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-amber-400" />
      <div>
        <h2 className="text-sm font-semibold text-foreground">Founder profile needs attention</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          The live feed remains available, but evaluation and tailored artifacts stay disabled
          until these validation findings are fixed:
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-left text-sm text-muted-foreground">
          {findings.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export function NoOpportunitiesYetState({ onPollNow }: { onPollNow: () => void }) {
  return (
    <EmptyStateShell icon={Inbox} title="No opportunities yet">
      <p>
        Your sources have polled, but nothing has been discovered or has
        passed evaluation yet. New results usually appear within a few
        minutes of a poll.
      </p>
      <Button className="mt-3" onClick={onPollNow}>
        Poll now
      </Button>
    </EmptyStateShell>
  )
}

export function WorkerIdleState({ onPollNow }: { onPollNow: () => void }) {
  return (
    <EmptyStateShell icon={TimerReset} title="Worker hasn't run yet">
      <p>
        None of your sources have been polled yet, so there is nothing to
        show. Click Poll now to fetch opportunities immediately, or wait for
        the next scheduled run.
      </p>
      <Button className="mt-3" onClick={onPollNow}>
        Poll now
      </Button>
    </EmptyStateShell>
  )
}

export function NoFilterMatchesState({ onClear }: { onClear: () => void }) {
  return (
    <EmptyStateShell icon={Inbox} title="No opportunities match these filters">
      <p>Try widening your filters or clearing the search.</p>
      <Button variant="outline" className="mt-3" onClick={onClear}>
        Clear filters
      </Button>
    </EmptyStateShell>
  )
}
