# The `AI_Hackathon_CPP` Flutter prototype as a pilot mobile base

**Status:** assessment only. No source file changes in either repository. Mobile
was **deferred** by the 12 September 2026 stakeholder session; this document
exists so that when it is undeferred, the question "do we start from that
prototype" has a recorded answer rather than a fresh argument.

**Subject:** `BrooklynD23/AI_Hackathon_CPP`, `mobile_app/` — a Flutter application
named `insight_quest_mobile`, class `BroncoBoostApp`, assessed at commit `678a4d7`.

**Parent brief:**
[`2026-09-12-student-centric-prioritization-brief.md`](2026-09-12-student-centric-prioritization-brief.md).

---

## 1. What the prototype actually is

Read from `mobile_app/lib/main.dart` (797 lines, the entire application) and
`mobile_app/pubspec.yaml`.

| | |
|---|---|
| Framework | Flutter, Dart SDK `>=3.3.0 <4.0.0` |
| Platforms scaffolded | Android, iOS (deployment target 15.0), macOS, Linux, Windows, web |
| Dependencies, in full | `flutter`, `cupertino_icons`, `firebase_core`, `firebase_auth` |
| **HTTP client** | **None.** There is no `http`, no `dio`, no generated client, and no network call to anything but Firebase Auth |
| Auth | Firebase email/password — sign in, register, password reset, sign out, with mapped error copy |
| Screens | `AuthScreen`, then a four-tab shell: Home, Events, Cities, Profile |
| Data | `SimpleRepository.stateFor(account)` — a **pure function of a hash of the Firebase uid** returning three hard-coded events, four hard-coded cities, and a level/XP number derived from the uid's code units |
| Tests | One, asserting that the app class is non-null |
| State management | `setState` in a `StatefulWidget`. No architecture beyond that |

The README describes a considerably larger product than the code implements —
XP, avatar progression, city unlocks, geofencing, badges, streaks. **None of it
exists.** What exists is a working Firebase login in front of a static mock.

That is not a criticism of the prototype. A shell with real auth and a
convincing mock is a perfectly good hackathon artifact, and it is exactly the
kind of thing worth reusing *as a shell*. It is a criticism of reading its README
as a status report, which is the same habit this repository's own README opens by
warning against.

## 2. The three findings that decide the question

### 2.1 The identity planes are incompatible, and this is the important one

SmartMatch resolves a caller from a **verified bearer token** to a
`user_account` row by `external_subject`, which is globally unique (ADR-0008).
`GET /v1/me` reports that account. Every route is deny-by-default against it,
and the token verifier ships as `FixtureTokenVerifier` with the JWKS path
scaffolded but no live issuer configured — the eight A1b worksheet fields are
still outstanding, and any live issuer is *refused* rather than guessed
(`docs/plans/open-questions/a1b-live-idp-deferred.md`).

For the pilot specifically, `docs/decisions/pilot-login-decision-2026-09-04.md`
removed institutional sign-in as the only path and put **database-backed
credentials, one login per role**, in its place — owner-authorized, pilot-scoped,
production SSO explicitly deferred.

The prototype authenticates against **Firebase**, with a `google-services.json`
and a `GoogleService-Info.plist` committed to the repository. A Firebase uid is
not an `external_subject` this platform knows, and a Firebase ID token is not a
token `build_token_verifier` will accept. There is no configuration that bridges
them; accepting Firebase tokens would mean SmartMatch trusting a second issuer
that no A1b worksheet field names, which is precisely the acceptance the deferral
is structured to prevent.

**Consequence:** the prototype's single most complete feature — its auth flow —
is the one piece that **cannot** carry over. It has to be replaced with whatever
the pilot login decision produces.

### 2.2 There is no client layer to keep, because there is no client

`SimpleRepository` is not an abstraction over a data source that could be
repointed. It is a hash function returning literals. Every screen reads
`SimpleState` fields directly.

So "port the prototype to our API" is not a port. It is: keep the widget tree and
the visual identity, delete the repository, and write a real client against the
routes that already exist —
`GET /v1/units/{unit_id}/student/events`, `.../student/agenda`,
`POST|DELETE .../student/events/{event_id}/registration`,
`GET /v1/units/{unit_id}/rewards`, `POST /v1/units/{unit_id}/redemptions`,
`GET /v1/me`. That is most of a student app's surface, and it is real today.

### 2.3 Its product model is a different product

Cities, travel, geofencing, avatar stages and XP are a gamified travel app. This
platform's engagement model is `attendance_record → point_ledger_entry →
reward_item → redemption`, where a point is a *recorded fact* with an append-only
history and a balance is a fold, never a stored number and never a browser
formula (ADR-0013).

"XP" and "points" look like the same idea and are not. The prototype's XP is
computed client-side from a uid hash — structurally the same defect ADR-0013 was
written against, where the legacy frontend computed
`attendance_streak * 100 + events_attended * 25` in the browser.

**Consequence:** the avatar/XP/cities layer is not a feature to port. It is, at
most, a *visual treatment* that could sit on top of a real ledger balance later.
Anything that computes a number on the device is out.

## 3. Recommendation

**Reuse the prototype as a UI shell and a platform scaffold. Do not reuse its
auth, its data layer, or its product model.**

Concretely, what carries and what does not:

| Piece | Verdict |
|---|---|
| Flutter project scaffold — Android, iOS, signing config, launcher icons, CI-able build | **Keep.** Real, tedious, already done |
| Screen structure and visual identity (tab shell, cards, the asset pack) | **Keep.** This is the actual value |
| `AuthScreen`'s form, validation and error copy | **Keep the widgets, replace the backend** |
| `firebase_auth` / `firebase_core` / `google-services.json` | **Remove**, per §2.1 |
| `SimpleRepository`, `SimpleState`, `EventItem`, `CityUnlock` | **Delete.** Replace with a typed client over `/v1` |
| XP, levels, avatar stages | **Do not port.** A balance is a server fold |
| Cities / travel / geofencing | **Out of scope.** Different product |
| The Chrome extension in the same repository | **Out of scope here.** It has the same Firebase coupling and the same static event list |

## 4. Whether Flutter is the right choice at all

Worth deciding once rather than by inheritance.

| Option | For | Against |
|---|---|---|
| **Flutter**, from this prototype | A working iOS + Android scaffold exists today; one codebase; good offline story for a scanner | A third language and toolchain in a repository that is Python + TypeScript. No Dart expertise is recorded anywhere in either repository |
| **React Native / Expo** | Shares TypeScript with `apps/web/legacy-frontend`; component and type reuse; Expo removes most of the store toolchain | Discards the prototype entirely |
| **A PWA** — installable, from the existing web frontend | Cheapest by a wide margin; no store review; one deployment; the existing frontend already renders QR codes client-side with `qrcode` | Web push on iOS requires the user to add the app to the Home Screen, and camera and background behaviour are weaker than native |

**Recommendation for a *pilot*: the PWA, and keep the prototype in reserve.**

The reasoning is the reminders track, not the client. The parent brief's Track D
puts reminders on the existing outbox with **in-app first, email second, push
last**, because push needs a client, a credential and a store presence that the
session just deferred. A PWA delivers the student surface with no store, no second
toolchain and no third language, and it is the only option that can ship while
mobile is still deferred.

If and when a native app is authorized — which is OQ-SC-08, "does the pilot mobile
app ship to a store or to a small named cohort" — this prototype is a genuinely
useful starting point for the shell, on the terms in §3.

## 5. What has to be decided before any of this starts

| Id | Question | Owner |
|---|---|---|
| OQ-SC-08 | Store distribution, or a named cohort? | Danny |
| — | Which identity plane a mobile client authenticates against, given that the pilot login is database-backed credentials and A1b is deferred | Danny + whoever owns the pilot login |
| OQ-SC-03 | On what basis may SmartMatch contact a student — the prerequisite for any push notification at all | Ann + records |
| — | Whether the `google-services.json` and `GoogleService-Info.plist` committed to `AI_Hackathon_CPP` need rotating if that project is retired | Whoever owns that Firebase project |

That last row is housekeeping in the other team's repository rather than a
decision for this one, but it should not go unrecorded: those files are committed
to a repository whose Firebase project would become orphaned if the prototype is
retired.
