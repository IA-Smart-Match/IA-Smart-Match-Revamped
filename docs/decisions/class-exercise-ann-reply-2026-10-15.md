# Class exercise: Ann Wang's reply of 2026-10-15 (past-event cap, the 8 pre-registered, non-responders)

**Status:** Ruling recorded. Docs only; code follows in a separate PR. Her words are final; where earlier docs conflict, the earlier docs change.
**Decided by:** Dr. Fan (Ann) Wang, reply to the team's Teams message of 2026-10-15 (six questions, each with a default "A" if skipped).
**Supersedes:** the past-event points of Step B (+5 for 1-2, +10 for 3+) in [`class-exercise-results-rule-2026-10-10.md`](class-exercise-results-rule-2026-10-10.md) and [`class-exercise-current-rule.md`](class-exercise-current-rule.md); OQ-CE-25 "for certain" default (a).
**Open questions:** OQ-CE-19, 22, 25, 29 closed; OQ-CE-28 half closed. See the [register](../plans/open-questions/class-exercise-open-questions.md).

## Her reply, verbatim

> A on which events count: any past event is fine. But the lift is too big. Please make it smaller with a cap: +5 percentage points per past event, up to +15 (so the highest chance is about 20%, not 40%). I also agree that profile updates during the exercise should not count as past events. Please rerun the 5,000-run check after the change and send the new Northline and Harbor numbers. 2. B: the 8 pre-registered students should attend 65% of the time, like everyone else. If any team score or results screen uses attendance instead of sign-ups, please let me know. If it shows attendance, the ~3 fewer attendees is fine. I'll use it in the debrief to show the gap between signing up and showing up. 3. A. I believe if the students are annoyed, they will ignore everything, mass email included. This helps keep the cost of a "required" request clear for the debrief.

## What we asked her (Teams, 2026-10-15)

1. Any past event counts, not only related ones. Points add to the 5% start (we wrote the example "5% + 35 = 40%"; the +35 was the interest bonus). Topics added when students update their profile during the exercise do not count. A) That's right B) Change.
2. Do the 8 already signed up always attend (A), or attend 65% of the time (B)?
3. Do students who stop responding after "required" notice nothing (A), or still notice the mass email 20% of the time (B)?
4. Debrief sentence: keep it on the results screen (A), or say it only in her debrief (B)?
5. Chart caption "Mass email alone beside your CBACH emails on top of it.": keep (A) or remove (B)?
6. Two reason lines per name: fix after Thursday (A) or before (B)?

## Rulings

| Q | Ruling | Detail |
|---|---|---|
| 1 | DECIDED: A, amended | Any past event counts (confirms owner ruling 2026-10-12). Refresh/profile-update topics never count. Past-event bonus is now **+5 per past event, capped at +15** (was +5 for 1-2, +10 for 3+). Interest +35, goal +15, same major +5 unchanged. Theoretical max is **75** (was 70). |
| 2 | DECIDED: B | The 8 pre-registered attend at the 65% show-up rate. Seats = 60 − attending-of-8 − attendees. |
| 3 | DECIDED: A | Students who stop responding after "required" notice nothing, mass email included. Reason: annoyed students ignore everything; it keeps the cost of "required" clear for the debrief. |
| 4 | Default stands, no reply 2026-10-15 | The debrief sentence stays on the results screen. |
| 5 | Default stands, no reply 2026-10-15 | The chart caption stays. |
| 6 | Default stands, no reply 2026-10-15 | The two-reason-lines fix comes after Oct 16. |

### Q2: which screens use attendance (she asked)

- The lift line ("Mass email alone: N sign-ups ...") uses **sign-ups**.
- The seats sentence and the round-one recap use **attendance**.
- She accepts about 3 fewer attendees and will use the sign-up vs show-up gap in her debrief.

## Open follow-up (not a decision)

Q1 "about 20%, not 40%": this likely comes from our example "5% + 35 = 40%", which used the interest bonus. Under her per-event rule the past-event part alone tops out at 5% + 15 = 20%. Whether she meant an overall cap near 20% is **to be confirmed with her**. The code implements the literal per-event rule.

## Check numbers after the 2026-10-15 change: pending rerun

She asked for the 5,000-run check to be rerun after the change, with new Northline and Harbor numbers sent to her. Not yet run; no numbers here. The 1,000-seed table in the 2026-10-10 record and the current-rule page is superseded by this change.

## Next step

Code PR for the +5-per-event cap (max 75) and the 8 attending at 65%; then rerun the 5,000-run check and send her the numbers.
