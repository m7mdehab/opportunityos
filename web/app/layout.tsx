import type { Metadata } from "next"
import "./globals.css"
import { TooltipProvider } from "@/components/ui/tooltip"
import { MockProvider } from "@/components/mock-provider"

export const metadata: Metadata = {
  title: "OpportunityOS — Founder Alpha",
  description: "Founder-facing opportunity feed for OpportunityOS.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <TooltipProvider>
          <MockProvider>{children}</MockProvider>
        </TooltipProvider>
      </body>
    </html>
  )
}
