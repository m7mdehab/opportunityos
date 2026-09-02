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
          ? "border-amber-600/30 bg-amber-50 dark:bg-amber-950"
          : "border-border bg-card")
      }
    >
      <Icon
        aria-hidden="true"
        className={
          "size-8 " +
          (tone === "warning" ? "text-amber-700 dark:text-amber-300" : "text-muted-foreground")
        }
      />
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="text-sm text-muted-foreground">{children}</div>
    </div>
  )
}

export function NoTruthPackState({ path }: { path: string }) {
  return (
    <EmptyStateShell icon={FileWarning} title="No truth pack loaded" tone="warning">
      <p>
        The founder truth pack was not found at <code className="rounded bg-muted px-1">{path}</code>.
        Nothing can be evaluated or tailored until one is loaded.
      </p>
      <p className="mt-2 font-medium text-foreground">What to do next:</p>
      <ol className="mt-1 list-decimal space-y-1 pl-5 text-left">
        <li>
          Copy <code className="rounded bg-muted px-1">docs/templates/truth_pack.template.yaml</code> to{" "}
          <code className="rounded bg-muted px-1">private/truth_pack.yaml</code>.
        </li>
        <li>Fill in your details and evidence.</li>
        <li>
          Run <code className="rounded bg-muted px-1">python scripts/truth_check.py</code> until it exits 0.
        </li>
        <li>Come back and reload.</li>
      </ol>
    </EmptyStateShell>
  )
}

export function InvalidTruthPackState({
  findings,
}: {
  findings: string[]
}) {
  return (
    <EmptyStateShell icon={AlertTriangle} title="Truth pack is invalid" tone="warning">
      <p>
        A truth pack was found but did not pass validation. Nothing can be
        evaluated until these are fixed:
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-left">
        {findings.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      <p className="mt-2 font-medium text-foreground">What to do next:</p>
      <p className="mt-1">
        Edit <code className="rounded bg-muted px-1">private/truth_pack.yaml</code>, then run{" "}
        <code className="rounded bg-muted px-1">python scripts/truth_check.py</code> until it exits 0, then reload.
      </p>
    </EmptyStateShell>
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
