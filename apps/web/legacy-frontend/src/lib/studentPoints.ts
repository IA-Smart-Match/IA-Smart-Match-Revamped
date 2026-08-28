import type { StudentProfile } from "./api";

/** Total redeemable balance: streak bonus + attendance bonus (demo formula). */
export function getStudentTotalPoints(profile: Pick<StudentProfile, "attendance_streak" | "events_attended">): number {
  return profile.attendance_streak * 100 + profile.events_attended * 25;
}
