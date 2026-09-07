"use client"

import { useEffect, useState } from "react"
import { ExternalLink, CheckCircle2, Circle, Sparkles, BookOpen, GraduationCap, ShieldCheck, Clock, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { api } from "@/lib/api/client"
import type {
  TutoringPlatform,
  TutoringProfileMaterialResponse,
  TutoringStatus,
} from "@/lib/contract/types"

const STATUS_CONFIG: Record<
  TutoringStatus,
  { label: string; badgeClass: string; desc: string }
> = {
  not_started: {
    label: "Not started",
    badgeClass: "bg-muted text-muted-foreground border-muted-foreground/30",
    desc: "Application not yet initiated",
  },
  preparing_profile: {
    label: "Preparing profile",
    badgeClass: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30",
    desc: "Drafting bio, selecting subjects & media",
  },
  ready_to_apply: {
    label: "Ready to apply",
    badgeClass: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30",
    desc: "Readiness checklist complete; open portal",
  },
  applied: {
    label: "Applied",
    badgeClass: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/30",
    desc: "Application submitted; awaiting platform review",
  },
  approved: {
    label: "Approved / profile live",
    badgeClass: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
    desc: "Profile active to receive student bookings",
  },
  rejected_unavailable: {
    label: "Rejected / unavailable",
    badgeClass: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30",
    desc: "Application declined or region paused",
  },
}

export function TutoringSurface() {
  const [platforms, setPlatforms] = useState<TutoringPlatform[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [profileMaterialOpen, setProfileMaterialOpen] = useState(false)
  const [profileMaterial, setProfileMaterial] =
    useState<TutoringProfileMaterialResponse | null>(null)
  const [materialLoading, setMaterialLoading] = useState(false)

  const loadPlatforms = async () => {
    try {
      setLoading(true)
      setError(null)
      const res = await api.tutoring.platforms()
      setPlatforms(res.platforms)
    } catch {
      setError("Failed to load tutoring platforms. Please check API status.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadPlatforms()
  }, [])

  const handleStatusChange = async (
    platformId: string,
    newStatus: TutoringStatus
  ) => {
    try {
      const updated = await api.tutoring.updatePlatform(platformId, {
        status: newStatus,
      })
      setPlatforms((prev) =>
        prev.map((p) => (p.id === platformId ? updated : p))
      )
    } catch {
      // ignore
    }
  }

  const handleChecklistToggle = async (
    platformId: string,
    item: string,
    currentValue: boolean
  ) => {
    const platform = platforms.find((p) => p.id === platformId)
    if (!platform) return

    const nextChecklist = {
      ...platform.checklist_state,
      [item]: !currentValue,
    }

    // Auto-advance status to ready_to_apply if all complete and currently preparing
    const allChecked = platform.readiness_checklist.every(
      (req) => nextChecklist[req]
    )
    let nextStatus = platform.status
    if (allChecked && platform.status === "preparing_profile") {
      nextStatus = "ready_to_apply"
    } else if (
      !allChecked &&
      platform.status === "not_started" &&
      !currentValue
    ) {
      nextStatus = "preparing_profile"
    }

    try {
      const updated = await api.tutoring.updatePlatform(platformId, {
        checklist: nextChecklist,
        status: nextStatus,
      })
      setPlatforms((prev) =>
        prev.map((p) => (p.id === platformId ? updated : p))
      )
    } catch {
      // ignore
    }
  }

  const openProfileMaterial = async () => {
    setProfileMaterialOpen(true)
    if (!profileMaterial) {
      try {
        setMaterialLoading(true)
        const mat = await api.tutoring.profileMaterial()
        setProfileMaterial(mat)
      } catch {
        // ignore
      } finally {
        setMaterialLoading(false)
      }
    }
  }

  // Summary counts
  const totalPlatforms = platforms.length
  const preparingCount = platforms.filter(
    (p) => p.status === "preparing_profile"
  ).length
  const readyCount = platforms.filter(
    (p) => p.status === "ready_to_apply"
  ).length
  const appliedCount = platforms.filter((p) => p.status === "applied").length
  const approvedCount = platforms.filter((p) => p.status === "approved").length

  const totalChecklistItems = platforms.reduce(
    (acc, p) => acc + p.readiness_checklist.length,
    0
  )
  const completedChecklistItems = platforms.reduce(
    (acc, p) =>
      acc + Object.values(p.checklist_state).filter(Boolean).length,
    0
  )

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-sm text-muted-foreground animate-pulse">
          Loading online tutoring platform lane...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-8 text-center">
        <AlertCircle className="mx-auto size-8 text-destructive mb-2" />
        <p className="text-sm text-destructive">{error}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={loadPlatforms}
          className="mt-4"
        >
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Lane Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center gap-2">
            <GraduationCap className="size-6 text-primary" />
            <h2 className="text-2xl font-bold tracking-tight">
              Online Tutoring & Technical Mentorship
            </h2>
            <Badge variant="outline" className="text-xs bg-primary/5 text-primary border-primary/20">
              Founder Acquisition Lane
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            First-class acquisition workflow for verified technical tutoring and 1-on-1 coaching.
            These platforms operate through direct applicant registration and credentials verification.
            Nothing here is scraped or simulated.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={openProfileMaterial}
            className="flex items-center gap-2 border-primary/30 text-primary hover:bg-primary/5"
          >
            <ShieldCheck className="size-4" />
            Truth-Locked Profile Bio & Skills
          </Button>
        </div>
      </div>

      {/* KPI / Pipeline Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="rounded-lg border border-border bg-card p-3 text-center">
          <div className="text-xs font-medium text-muted-foreground uppercase">
            Platforms
          </div>
          <div className="text-2xl font-bold tabular-nums mt-1">
            {totalPlatforms}
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">Catalogued</div>
        </div>

        <div className="rounded-lg border border-border bg-card p-3 text-center">
          <div className="text-xs font-medium text-muted-foreground uppercase">
            Preparing
          </div>
          <div className="text-2xl font-bold text-blue-600 dark:text-blue-400 tabular-nums mt-1">
            {preparingCount}
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">In draft</div>
        </div>

        <div className="rounded-lg border border-border bg-card p-3 text-center">
          <div className="text-xs font-medium text-muted-foreground uppercase">
            Ready to Apply
          </div>
          <div className="text-2xl font-bold text-amber-600 dark:text-amber-400 tabular-nums mt-1">
            {readyCount}
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">Requirements met</div>
        </div>

        <div className="rounded-lg border border-border bg-card p-3 text-center">
          <div className="text-xs font-medium text-muted-foreground uppercase">
            Applied
          </div>
          <div className="text-2xl font-bold text-purple-600 dark:text-purple-400 tabular-nums mt-1">
            {appliedCount}
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">In review</div>
        </div>

        <div className="rounded-lg border border-border bg-card p-3 text-center">
          <div className="text-xs font-medium text-muted-foreground uppercase">
            Live / Active
          </div>
          <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 tabular-nums mt-1">
            {approvedCount}
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">Ready for bookings</div>
        </div>

        <div className="rounded-lg border border-border bg-card p-3 text-center">
          <div className="text-xs font-medium text-muted-foreground uppercase">
            Readiness
          </div>
          <div className="text-2xl font-bold tabular-nums mt-1">
            {completedChecklistItems}/{totalChecklistItems}
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            {totalChecklistItems > 0
              ? `${Math.round((completedChecklistItems / totalChecklistItems) * 100)}% complete`
              : "—"}
          </div>
        </div>
      </div>

      {/* Platforms Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {platforms.map((platform) => {
          const statusMeta = STATUS_CONFIG[platform.status]
          const completedCount = Object.values(platform.checklist_state).filter(
            Boolean
          ).length
          const totalCount = platform.readiness_checklist.length
          const progressPercent =
            totalCount > 0 ? (completedCount / totalCount) * 100 : 0

          return (
            <div
              key={platform.id}
              data-testid={`tutoring-platform-${platform.id}`}
              className="rounded-xl border border-border bg-card p-5 flex flex-col justify-between shadow-xs hover:border-primary/40 transition-colors"
            >
              <div className="space-y-4">
                {/* Platform Name & Status Header */}
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-lg font-semibold text-foreground flex items-center gap-1.5">
                      {platform.name}
                    </h3>
                    <Badge
                      variant="outline"
                      className="mt-1 text-[11px] font-normal text-muted-foreground bg-muted/50"
                    >
                      Platform Application
                    </Badge>
                  </div>

                  <select
                    value={platform.status}
                    onChange={(e) =>
                      handleStatusChange(
                        platform.id,
                        e.target.value as TutoringStatus
                      )
                    }
                    className={`text-xs font-semibold rounded-md border px-2.5 py-1 outline-none transition-colors ${statusMeta.badgeClass}`}
                  >
                    <option value="not_started">Not started</option>
                    <option value="preparing_profile">Preparing profile</option>
                    <option value="ready_to_apply">Ready to apply</option>
                    <option value="applied">Applied</option>
                    <option value="approved">Approved / profile live</option>
                    <option value="rejected_unavailable">
                      Rejected / unavailable
                    </option>
                  </select>
                </div>

                {/* Policy Posture */}
                <p className="text-xs text-muted-foreground/90 bg-muted/30 p-2.5 rounded-md border border-border/50 leading-relaxed">
                  {platform.policy_posture}
                </p>

                {/* Next Action Callout */}
                <div className="rounded-md border border-primary/20 bg-primary/5 p-2.5">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-primary">
                    Next Action
                  </div>
                  <div className="text-xs font-medium text-foreground mt-0.5 flex items-center gap-1.5">
                    <Clock className="size-3 text-primary shrink-0" />
                    {platform.next_action}
                  </div>
                </div>

                {/* Readiness Checklist */}
                <div className="space-y-2 pt-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-muted-foreground uppercase text-[11px]">
                      Readiness Requirements
                    </span>
                    <span className="text-muted-foreground tabular-nums font-medium">
                      {completedCount} of {totalCount}
                    </span>
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                    <div
                      className="bg-primary h-1.5 rounded-full transition-all duration-300"
                      style={{ width: `${progressPercent}%` }}
                    />
                  </div>

                  <ul className="space-y-1.5 mt-2">
                    {platform.readiness_checklist.map((item) => {
                      const isChecked = Boolean(platform.checklist_state[item])
                      return (
                        <li key={item}>
                          <button
                            type="button"
                            onClick={() =>
                              handleChecklistToggle(platform.id, item, isChecked)
                            }
                            className="w-full flex items-start gap-2 text-left text-xs py-1 px-1.5 rounded hover:bg-muted/50 transition-colors group"
                          >
                            {isChecked ? (
                              <CheckCircle2 className="size-4 text-emerald-500 shrink-0 mt-0.5" />
                            ) : (
                              <Circle className="size-4 text-muted-foreground/60 shrink-0 mt-0.5 group-hover:text-primary" />
                            )}
                            <span
                              className={
                                isChecked
                                  ? "text-foreground line-through opacity-70"
                                  : "text-foreground"
                              }
                            >
                              {item}
                            </span>
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              </div>

              {/* Bottom Actions */}
              <div className="pt-5 border-t border-border mt-4 flex items-center justify-between gap-2">
                <a
                  href={platform.canonical_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
                >
                  <ExternalLink className="size-3.5" />
                  Open Application Portal
                </a>

                {platform.status === "ready_to_apply" && (
                  <Button
                    size="sm"
                    variant="default"
                    className="text-xs h-7 px-2.5"
                    onClick={() => handleStatusChange(platform.id, "applied")}
                  >
                    Mark Applied
                  </Button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Truth-Locked Profile Material Dialog */}
      <Dialog
        open={profileMaterialOpen}
        onOpenChange={setProfileMaterialOpen}
      >
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="size-5 text-emerald-500" />
              Truth-Locked Tutoring Profile & Bio Material
            </DialogTitle>
            <DialogDescription>
              Authoritative evidence-backed statements from the Founder Truth Graph.
              Use these verified claims directly for platform applications and bio descriptions.
            </DialogDescription>
          </DialogHeader>

          {materialLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground animate-pulse">
              Extracting verified profile material from Truth Graph...
            </div>
          ) : profileMaterial ? (
            <div className="space-y-5 pt-2 text-sm">
              {/* Approved Summaries / Bio */}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                  <BookOpen className="size-3.5 text-primary" />
                  Approved Bio & Summary
                </h4>
                {profileMaterial.approved_summaries.length > 0 ? (
                  <div className="space-y-2">
                    {profileMaterial.approved_summaries.map((s, idx) => (
                      <p
                        key={idx}
                        className="bg-muted/40 p-3 rounded-md border border-border/60 text-foreground leading-relaxed"
                      >
                        {s}
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground italic">
                    No approved summaries configured in career profile.
                  </p>
                )}
              </div>

              {/* Verified Subjects & Skills */}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                  <Sparkles className="size-3.5 text-primary" />
                  Verified Tutoring Subjects & Technical Skills
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {profileMaterial.tutoring_skills.map((s) => (
                    <Badge
                      key={s.name}
                      variant="outline"
                      className="text-xs bg-card py-1 px-2 border-border flex items-center gap-1"
                    >
                      <span className="font-medium">{s.name}</span>
                      <span className="text-[10px] text-muted-foreground">
                        ({s.proficiency})
                      </span>
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Languages */}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                  Delivery Languages
                </h4>
                <div className="flex gap-2">
                  {profileMaterial.languages.map((l) => (
                    <Badge key={l.language} variant="secondary" className="text-xs">
                      {l.language}: {l.proficiency}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Provenance Evidence IDs */}
              <div className="border-t border-border pt-3">
                <div className="text-[11px] text-muted-foreground">
                  <span className="font-semibold text-foreground">
                    Evidence Citations:
                  </span>{" "}
                  {profileMaterial.evidence_ids.length} verified truth graph records
                  ({profileMaterial.evidence_ids.slice(0, 10).join(", ")}
                  {profileMaterial.evidence_ids.length > 10 ? ", ..." : ""})
                </div>
              </div>
            </div>
          ) : (
            <div className="py-4 text-sm text-destructive">
              Unable to load truth pack material. Ensure pack is loaded.
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
