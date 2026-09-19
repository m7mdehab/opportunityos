"use client"

import { useState, type FormEvent } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.auth.login(password, email)
      router.push("/")
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        const body = err.body as { retry_after_seconds?: number } | null
        const seconds = body?.retry_after_seconds
        setError(
          seconds
            ? `Too many attempts. Try again in ${seconds} seconds.`
            : "Too many attempts. Try again shortly."
        )
      } else if (err instanceof ApiError && err.status === 401) {
        setError("Incorrect password.")
      } else {
        setError("Could not sign in. Check your account configuration and try again.")
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <h1 className="text-xl font-semibold">OpportunityOS</h1>
          <p className="text-sm text-muted-foreground">
            Founder alpha — sign in with your configured Founder account.
          </p>
        </div>

        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-lg border border-border bg-card p-6"
          noValidate
        >
          <div className="space-y-1.5">
            <Label htmlFor="email">Founder email</Label>
            <Input id="email" name="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              autoFocus
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "login-error" : undefined}
            />
          </div>

          {error && (
            <p
              id="login-error"
              role="alert"
              className="text-sm text-destructive"
            >
              {error}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </div>
    </main>
  )
}
