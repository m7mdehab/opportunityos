"use client"

import { useEffect, useState } from "react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { api, downloadArtifact } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"
import {
  ARTIFACT_TEMPLATES,
  type ArtifactTemplateId,
  type ArtifactValidationFinding,
  type OmittedItem,
} from "@/lib/contract/types"

const TEMPLATE_LABEL: Record<ArtifactTemplateId, string> = {
  classic: "Classic",
  compact: "Compact",
  modern: "Modern",
}

const KIND_LABEL: Record<"cv" | "cover-letter", string> = {
  cv: "Tailored CV",
  "cover-letter": "Cover letter",
}

/** BRIEF-FR-006 D2 — the drawer's artifacts panel: embedded PDF viewer,
 * template switcher, PDF/DOCX download buttons, and a visible rendering of
 * D1's "what was left out and why" data. On a 409 the panel shows the
 * rejected claim text and the reason in plain language, not a bare error
 * — the founder must see *which sentence* could not be supported. That is
 * the difference between the product correctly refusing to put an
 * unsupported claim under their name, and the product simply looking
 * broken. */
export function ArtifactsPanel({ opportunityId }: { opportunityId: string }) {
  const [kind, setKind] = useState<"cv" | "cover-letter">("cv")
  const [template, setTemplate] = useState<ArtifactTemplateId>("classic")

  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  const [omittedItems, setOmittedItems] = useState<OmittedItem[] | null>(null)
  const [findings, setFindings] = useState<ArtifactValidationFinding[] | null>(
    null
  )
  const [metaError, setMetaError] = useState<string | null>(null)
  const [loadingMeta, setLoadingMeta] = useState(false)

  const [downloading, setDownloading] = useState<"pdf" | "docx" | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const previewUrl = api.opportunities.artifactPdfUrl(
    opportunityId,
    kind,
    template
  )

  // React's documented "adjust state when props change" pattern, not an
  // effect: resetting during render avoids the synchronous re-render cascade
  // that `react-hooks/set-state-in-effect` flags, and guarantees the panel
  // never paints one document's findings against another's request.
  const requestKey = `${opportunityId}|${kind}|${template}`
  if (requestKey !== loadedKey) {
    setLoadedKey(requestKey)
    setOmittedItems(null)
    setFindings(null)
    setMetaError(null)
    setLoadingMeta(true)
  }

  useEffect(() => {
    let cancelled = false
    api.opportunities
      .omittedItems(opportunityId, kind, template)
      .then((res) => {
        if (cancelled) return
        setOmittedItems(res.omitted_items)
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 409) {
          const body = err.body as {
            findings?: ArtifactValidationFinding[]
          } | null
          setFindings(body?.findings ?? [])
        } else if (err instanceof ApiError && err.status === 412) {
          setMetaError(
            "No truth pack is loaded, so no tailored document can be generated."
          )
        } else {
          setMetaError("Could not load what was left out for this document.")
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingMeta(false)
      })
    return () => {
      cancelled = true
    }
  }, [opportunityId, kind, template])

  async function handleDownload(format: "pdf" | "docx") {
    setDownloadError(null)
    setDownloading(format)
    try {
      const { blob, filename } = await downloadArtifact(opportunityId, kind, {
        format,
        template,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const body = err.body as {
          findings?: ArtifactValidationFinding[]
        } | null
        setFindings(body?.findings ?? [])
        setDownloadError(
          "Could not generate this document — one or more claims could not be verified. See below."
        )
      } else if (err instanceof ApiError && err.status === 412) {
        setDownloadError(
          "No truth pack is loaded, so no tailored document can be generated."
        )
      } else {
        setDownloadError("Download failed.")
      }
    } finally {
      setDownloading(null)
    }
  }

  return (
    <section aria-labelledby="artifacts-heading" data-testid="artifacts-panel">
      <h3 id="artifacts-heading" className="text-sm font-semibold">
        Tailored documents
      </h3>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <div className="flex gap-1" role="group" aria-label="Document">
          {(["cv", "cover-letter"] as const).map((k) => (
            <Button
              key={k}
              type="button"
              size="sm"
              variant={kind === k ? "default" : "outline"}
              data-testid={`artifact-kind-${k}`}
              onClick={() => setKind(k)}
            >
              {KIND_LABEL[k]}
            </Button>
          ))}
        </div>

        <Select
          value={template}
          onValueChange={(v) => setTemplate(v as ArtifactTemplateId)}
        >
          <SelectTrigger
            className="w-[140px]"
            data-testid="artifact-template-switcher"
            aria-label="Template"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ARTIFACT_TEMPLATES.map((t) => (
              <SelectItem key={t} value={t} data-testid={`artifact-template-option-${t}`}>
                {TEMPLATE_LABEL[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {loadingMeta && findings === null && (
        <p className="mt-2 text-xs text-muted-foreground">
          Checking claims against your truth pack…
        </p>
      )}

      {findings === null ? (
        <div className="mt-3 overflow-hidden rounded-md border border-border">
          {/* `key` forces a fresh plugin instance on template/kind switch --
              some browsers cache an <embed> by element identity even after
              `src` changes. */}
          <embed
            key={`${kind}-${template}`}
            src={previewUrl}
            type="application/pdf"
            data-testid="artifact-pdf-preview"
            className="h-[420px] w-full"
          />
        </div>
      ) : (
        <div
          role="alert"
          data-testid="artifact-validation-rejection"
          className="mt-3 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs"
        >
          <p className="font-medium text-destructive">
            This document could not be generated —{" "}
            {findings.length === 0
              ? "a claim"
              : `${findings.length} claim${findings.length === 1 ? "" : "s"}`}{" "}
            could not be supported by your truth pack.
          </p>
          <ul className="mt-2 space-y-2">
            {findings.map((f, i) => (
              <li key={i} data-testid={`artifact-finding-${i}`}>
                <p className="font-medium">&ldquo;{f.claim}&rdquo;</p>
                <p className="text-muted-foreground">
                  {f.rejection_reasons.join("; ")}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {metaError && (
        <p role="alert" className="mt-2 text-xs text-destructive">
          {metaError}
        </p>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={downloading !== null}
          data-testid="artifact-download-pdf"
          onClick={() => handleDownload("pdf")}
        >
          {downloading === "pdf" ? "Preparing…" : "Download PDF"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={downloading !== null}
          data-testid="artifact-download-docx"
          onClick={() => handleDownload("docx")}
        >
          {downloading === "docx" ? "Preparing…" : "Download DOCX"}
        </Button>
      </div>
      {downloadError && (
        <p role="alert" className="mt-2 text-xs text-destructive">
          {downloadError}
        </p>
      )}

      {omittedItems && omittedItems.length > 0 && (
        <div className="mt-3" data-testid="artifact-omitted-panel">
          <h4 className="text-xs font-semibold text-muted-foreground">
            What was left out and why
          </h4>
          <ul className="mt-1 space-y-1.5 text-xs">
            {omittedItems.map((item, i) => (
              <li key={i} className="rounded-md border border-border p-2">
                <p>{item.text}</p>
                <p className="mt-0.5 text-muted-foreground">{item.reason}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
