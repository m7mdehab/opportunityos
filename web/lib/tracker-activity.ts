export const TRACKER_ACTIVITY_CHANGED_EVENT = "opportunityos:tracker-activity-changed"

export function notifyTrackerActivityChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(TRACKER_ACTIVITY_CHANGED_EVENT))
  }
}
