"use client"

import { useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"

type ImportResult = {
  status: string
  pack_id: string
  production_pdfs_replaced: number
  editable_docx_stored: number
  system_files_stored: number
  assets: Array<{ filename: string; object_path: string; sha256: string; size: number }>
  archive: { object_path: string; sha256: string; size: number }
}

export default function CvSystemPage() {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function importPack() {
    if (!file) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const response = await fetch("/api/cv-pack-import", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/zip",
          "X-OpportunityOS-CSRF": "1",
        },
        body: file,
      })
      const payload = (await response.json().catch(() => null)) as ImportResult | { detail?: string } | null
      if (!response.ok) {
        throw new Error(payload && "detail" in payload ? payload.detail ?? "Import failed" : "Import failed")
      }
      setResult(payload as ImportResult)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl p-6 sm:p-10">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Authoritative CV pack</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Founder-only importer for the current OpportunityOS CV portfolio.
          </p>
        </div>
        <Link href="/" className="text-sm underline underline-offset-4">Back to opportunities</Link>
      </div>

      <section className="mt-8 rounded-lg border border-border p-5">
        <h2 className="font-semibold">Import a final pack</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          This replaces the six production CV PDFs at their stable website paths, stores the six editable DOCX masters for future LLM-assisted tailoring, and stores ATS_AUDIT, OpportunityOS_CV_Registry, README_CV_SYSTEM, and the exact source ZIP privately.
        </p>
        <p className="mt-2 text-sm font-medium">
          The ZIP is fully validated and checksummed before production PDF selection hashes are changed.
        </p>

        <label className="mt-5 block text-sm font-medium" htmlFor="cv-pack-file">
          OpportunityOS CV pack ZIP
        </label>
        <input
          id="cv-pack-file"
          className="mt-2 block w-full rounded-md border border-border p-2 text-sm"
          type="file"
          accept=".zip,application/zip"
          disabled={busy}
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null)
            setResult(null)
            setError(null)
          }}
        />

        <Button className="mt-4" type="button" disabled={!file || busy} onClick={importPack}>
          {busy ? "Importing and verifying…" : "Import authoritative pack"}
        </Button>

        {error && <p role="alert" className="mt-4 text-sm text-destructive">{error}</p>}

        {result && (
          <div className="mt-5 rounded-md border border-emerald-700/40 bg-emerald-950/10 p-4 text-sm" data-testid="cv-pack-import-success">
            <p className="font-semibold">Pack {result.pack_id} imported and verified.</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
              <li>{result.production_pdfs_replaced} production PDFs replaced.</li>
              <li>{result.editable_docx_stored} editable DOCX masters stored.</li>
              <li>{result.system_files_stored} system/package files stored.</li>
              <li>Website selection checksums updated after byte-for-byte storage verification.</li>
            </ul>
          </div>
        )}
      </section>
    </main>
  )
}
