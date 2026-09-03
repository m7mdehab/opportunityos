"use client"

/**
 * E23 UI half — "Check manually": every `manual_only` source, each a plain
 * link the founder clicks. The app never fetches any of these itself (see
 * `lib/data/manual-sources.ts`'s scope note on why this data is a static
 * transcription rather than an API call).
 */
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { ExternalLink } from "lucide-react"
import { MANUAL_SOURCES, type ManualSourceCategory } from "@/lib/data/manual-sources"

const CATEGORY_LABEL: Record<ManualSourceCategory, string> = {
  aggregator: "Aggregators & communities",
  regional: "Regional & Arabic-language",
  freelance: "Freelance",
}

const CATEGORIES: ManualSourceCategory[] = ["aggregator", "regional", "freelance"]

export function ManualSourcesPanel({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto sm:max-w-md"
        aria-describedby={undefined}
      >
        <SheetHeader>
          <SheetTitle>Check manually</SheetTitle>
          <SheetDescription>
            Sources no adapter reads automatically (blocked by robots.txt,
            terms, or a credential gate). Each link opens that source with
            your default search prefilled — nothing here is fetched by the
            app.
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-4 px-4 pb-4">
          {CATEGORIES.map((category) => {
            const sources = MANUAL_SOURCES.filter((s) => s.category === category)
            if (sources.length === 0) return null
            return (
              <section key={category} aria-labelledby={`manual-sources-${category}`}>
                <h3
                  id={`manual-sources-${category}`}
                  className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  {CATEGORY_LABEL[category]} ({sources.length})
                </h3>
                <ul className="mt-2 space-y-1.5">
                  {sources.map((s) => (
                    <li
                      key={s.sourceId}
                      data-testid={`manual-source-${s.sourceId}`}
                      className="rounded-md border border-border p-2"
                    >
                      <a
                        href={s.deepLink}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="flex items-center gap-1.5 text-sm font-medium text-primary underline-offset-2 hover:underline"
                      >
                        <ExternalLink aria-hidden="true" className="size-3.5 shrink-0" />
                        {s.name}
                      </a>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {s.policyNote}
                      </p>
                    </li>
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
      </SheetContent>
    </Sheet>
  )
}
