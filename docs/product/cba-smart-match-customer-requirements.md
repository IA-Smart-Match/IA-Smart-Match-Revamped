# CBA Smart Match — Consolidated Customer Requirements

**Last updated:** 2026-09-04  
**Purpose:** Single source of truth for implementation agents.  
**Authority rule:** When requirements conflict, use the most recent customer instruction unless explicitly marked unresolved.

---

## 1. Product Direction

The application is being repurposed from an **IA West / Insights Association chapter workflow** to a **Cal Poly Pomona College of Business Administration (CBA) career-readiness speaker/event matching platform**.

Core functionality should remain largely unchanged. The main changes are:

- terminology and role names;
- CBA-oriented workflow framing;
- speaker/event data fields;
- matching logic;
- removal of chapter-membership concepts;
- optional CPP branding changes.

### Current scope

The system matches:

1. events already entered into the application; and
2. speakers/contacts already entered into the application.

The application must **not** search for new speakers on the internet or scrape external data sources in this phase.

---

## 2. Final User Roles

| Old Role | New Role | Responsibilities |
|---|---|---|
| Member | **Student** | Browse events, register, add events to calendar, submit speaker feedback/ratings |
| Event Organizer / Volunteer | **Event Host** | Faculty, staff, or student clubs requesting a speaker for a class, workshop, or club event |
| Chapter Admin | **Speaker Connector** | CBACH, Alumni Relations, and faculty who maintain contact lists, receive requests, run matching, send invitations, and track responses |
| Speaker | **Speaker** | Alumni, employers, and industry guests who receive invitations and view upcoming engagements |

---

## 3. Login and Role Handling

### Required behavior

- Use **one standard login flow**.
- Do **not** ask the user to choose a portal or role at login.
- User roles are assigned in the backend.
- After authentication, permissions and dashboard content are determined from the user's assigned role.

### Explicitly rejected behavior

- Separate role login pages.
- "Choose your portal" flow.

---

## 4. Terminology Changes

Use the following terminology consistently throughout UI copy, headings, labels, navigation, documentation, fixtures, and seed/demo data where applicable.

| Old Term | New Term |
|---|---|
| Member | **Student** |
| Event Organizer | **Event Host** |
| Volunteer | **Event Host** when referring to the event-requesting role |
| Chapter Admin | **Speaker Connector** |
| Speaker | **Speaker** |
| IA West | **CBA** or **College** |
| Insights Association | **CBA** or **College** |
| Chapter | **CBA** or **College** |
| Chapter Admin Dashboard | **Connector Dashboard** |
| Member Portal | **Student Portal** |
| Chapter membership | **Remove** |
| Membership dues | **Remove** |
| Volunteer opportunity | **Speaker Request** |
| Rewards / points | **Keep** |
| Purple theme | **Replace with CPP green/gold only if quick; otherwise defer** |

### Naming consistency

Preferred short in-app institutional name: **CBA**.

Avoid mixing multiple short names unless context requires it.

Examples:

- CBA Events
- CBA Speaker Network
- CBA Speaker Request
- CBA Student Portal

---

## 5. Matching Algorithm — Current Final Specification

### Final default weights

| Factor | Weight |
|---|---:|
| **Industry** | **30%** |
| **Role** | **25%** |
| **Topic** | **15%** |
| **Proximity** | **30%** |
| **Total** | **100%** |

### Superseded weight configurations

Do **not** use these as final defaults:

- Topic 70% / Proximity 30%
- Industry 40% / Topic 30% / Proximity 30%

### Configuration requirement

Do **not** scatter or duplicate hard-coded weight values throughout the matching implementation.

Store the weights in one configurable location so a **Speaker Connector** can adjust them later.

A basic settings mechanism is sufficient. A complex administration UI is not required.
It is encouraged to design an intuitive UI/system that Speaker Connector can change without being too technical.

---

## 6. Matching Result Behavior

The system should:

1. Receive a Speaker Request from an Event Host.
2. Compare it against speakers already stored in the application.
3. Score candidates using Industry, Role, Topic, and Proximity.
4. Rank candidates internally.
5. Return a shortlist of approximately **2–3 speaker candidates**.
6. Allow a Speaker Connector to review the shortlist.
7. Allow the Speaker Connector to send invitations, including batch invitations where supported.
8. Track speaker responses/acceptances.
9. Hand the confirmed speaker back to the Event Host/event initiator.

### Overall match percentage

Earlier customer direction explicitly said **no ranked percentage**.

Current interpretation:

- rank candidates internally;
- present candidates in ranked order;
- do **not** emphasize an overall percentage such as "87% Match" unless later approved; (calculation values shown in backend only for logging purpose)
- factor-level details may still be shown where useful;
- Topic must expose a fit score and one-sentence explanation because this was explicitly requested later.

---

## 7. Industry Classification

Use the 20 NAICS sector groups supplied by the customer.

| Code | Sector |
|---|---|
| 11 | Agriculture, Forestry, Fishing and Hunting |
| 21 | Mining, Quarrying, and Oil and Gas Extraction |
| 22 | Utilities |
| 23 | Construction |
| 31-33 | Manufacturing |
| 42 | Wholesale Trade |
| 44-45 | Retail Trade |
| 48-49 | Transportation and Warehousing |
| 51 | Information |
| 52 | Finance and Insurance |
| 53 | Real Estate and Rental and Leasing |
| 54 | Professional, Scientific, and Technical Services |
| 55 | Management of Companies and Enterprises |
| 56 | Administrative and Support and Waste Management and Remediation Services |
| 61 | Educational Services |
| 62 | Health Care and Social Assistance |
| 71 | Arts, Entertainment, and Recreation |
| 72 | Accommodation and Food Services |
| 81 | Other Services (except Public Administration) |
| 92 | Public Administration |

### Speaker-side industry behavior

Each speaker should have **one primary industry sector**.

Initial classification can be inferred from:

- company name;
- current position/title.

A **Speaker Connector must be able to manually correct the assigned industry**.

### Event-side industry behavior

A Speaker Request may target **multiple industries**.

Do not restrict an event request to one industry.

---

## 8. Role Classification

Use these ten CBA-aligned role categories:

1. **Accounting**
2. **Finance**
3. **Marketing**
4. **Management & Strategy**
5. **Human Resources**
6. **Operations & Supply Chain**
7. **Information Systems & Analytics**
8. **International Business**
9. **Entrepreneurship / Founder**
10. **Sales & Business Development**

### Speaker-side role behavior

Each speaker should normally have **one primary role category**.

The initial role may be inferred from the speaker's title/position.

A **Speaker Connector must be able to manually correct the assigned role**.

### Event-side role behavior

A Speaker Request may target **multiple role categories**.

Do not restrict an event request to one role.

---

## 9. Topic Matching

Topic contributes **15%** to the default match score.

### Required behavior

Use AI/semantic comparison between:

- the event description; and
- available speaker topic information, such as prior talks, areas of interest, expertise, or related profile text.

Return:

1. a simple Topic fit score; and
2. **one sentence explaining the reasoning**.

### Missing topic data

If a speaker has no useful topic information:

- do **not** score the speaker as zero;
- assign a **neutral/middle score** instead.

This prevents thin records from being unfairly penalized.

---

## 10. Proximity Matching

Proximity contributes **30%** to the default match score for physical events.

Distance should be measured in **miles from the CPP campus**.

City or ZIP code is sufficient for this phase.

### Distance bands

| Distance | Scoring Behavior |
|---|---|
| **0–25 miles** | Full/high proximity score |
| **25–75 miles** | Partial/medium proximity score |
| **75+ miles** | Low proximity score |

Exact numeric sub-scores inside each band were not specified and may remain implementation-defined/configurable.

---

## 11. Virtual Events

For virtual events:

- ignore Proximity entirely;
- redistribute its 30% weight across Industry, Role, and Topic.

### Unresolved detail

The customer did **not** specify the exact redistribution formula.

A proportional redistribution would yield approximately:

| Factor | Proportional Virtual Weight |
|---|---:|
| Industry | 42.86% |
| Role | 35.71% |
| Topic | 21.43% |

Treat proportional redistribution as an implementation interpretation, not a customer-confirmed rule.

---

## 12. Event Host Capabilities

Event Hosts should be able to:

- create a new event / Speaker Request;
- enter event details;
- select one or more industries;
- select one or more roles;
- enter event topic/description;
- specify event location;
- specify physical vs. virtual;
- submit the Speaker Request.

Event Hosts are not responsible for maintaining the central speaker/contact database.

---

## 13. Speaker Connector Capabilities

Speaker Connectors should be able to:

- view incoming Speaker Requests;
- view and manage speaker/contact records;
- manually add new speaker contacts;
- correct automatically assigned Industry;
- correct automatically assigned Role;
- run matching;
- review ranked candidate shortlists;
- view Topic-fit reasoning;
- send speaker invitations;
- batch-invite candidates where supported;
- track invitation responses/acceptances;
- manage matching weights;
- view student feedback/ratings.

This replaces most functionality previously associated with the Chapter Admin role.

---

## 14. Speaker Capabilities

Speakers should be able to view:

- invitations;
- accepted engagements;
- upcoming events.

The role name **Speaker** remains unchanged.

---

## 15. Student Capabilities

Students should be able to:

- browse events;
- register for events;
- add events to their calendar;
- attend events;
- provide feedback/ratings on speakers.

### Events page requirement

Keep the **month calendar at the bottom of the Events page**.

---

## 16. Student Speaker Feedback

Add a student feedback/ratings mechanism for speakers.

Speaker Connectors/admin users must be able to view the feedback.

The exact rating scale, form fields, and aggregation behavior were **not specified**.

Do not over-design this requirement without further direction.

---

## 17. Dashboard

The previously approved **discovery feed** remains in scope.

The customer approved the concept of:

- red actions;
- yellow actions;
- green actions.

Do not redesign this functionality solely because the target customer shifted from IA West to CBA.

Rename:

- **Chapter Admin Dashboard** → **Connector Dashboard**.

---

## 18. Speaker / Contact Data Schema

The customer expects source data to be scattered across multiple people and systems. There is currently no single authoritative export.

Expected source columns:

| Field |
|---|
| Name |
| Company Name |
| Current Position |
| Contact Email |
| Alumni (Y/N) |
| Graduation Year |
| Major |
| Willingness to Partner with CPP (Y/N) |
| Past Engagement (free text) |

### Additional fields required by matching

The application will also need fields such as:

- primary Industry sector;
- primary Role category;
- Topic/interests/expertise text;
- city and/or ZIP code;
- optional prior talk information.

Some of these may be derived initially and then corrected manually by a Speaker Connector.

---

## 19. Contact Import / Classification Flow

Suggested workflow:

```text
Contact record imported or manually created
        ↓
Company + current position/title analyzed
        ↓
Initial Industry classification assigned
        ↓
Initial Role classification assigned
        ↓
Speaker Connector reviews/corrects classifications
        ↓
Speaker becomes available for matching
```

Human correction is required because classification may involve judgment calls.

---

## 20. Explicit Scope Boundaries

The following are **out of scope for the current phase**:

- finding new speakers on the internet;
- scraping LinkedIn;
- scraping other external sources;
- automatic discovery of new events from external systems;
- cold outreach to unknown speakers;
- building a full external CRM/contact-acquisition system;
- chapter membership functionality;
- membership dues functionality;
- large redesign work solely for branding.

The lists of events and speakers grow **manually inside the system**.

Matching occurs only between records already in the system.

---

## 21. Branding

Preferred future branding:

- CPP green and gold.

Priority rule:

- change colors only if quick;
- do not let branding delay functional delivery.

The old purple theme is on hold and should not be treated as the desired final branding.

---

## 22. Existing Functionality to Preserve

The customer repeatedly stated that the CBA transition should not trigger an unnecessary rebuild.

Preserve working behavior unless a newer requirement explicitly changes it.

Keep:

- current application architecture;
- event browsing;
- registration;
- calendar functionality;
- role-based permissions;
- speaker invitation workflow;
- discovery-feed direction;
- core matching architecture where reusable.

---

## 23. Target End-to-End Workflow

```text
EVENT HOST
Faculty / Staff / Student Club
        │
        ▼
Creates Speaker Request
- event description
- one or more industries
- one or more roles
- location or virtual flag
        │
        ▼
MATCHING ENGINE
Industry     30%
Role         25%
Topic        15%
Proximity    30%
        │
        ▼
2–3 ranked speaker candidates
        │
        ▼
SPEAKER CONNECTOR
CBACH / Alumni Relations / Faculty
- reviews matches
- reviews Topic-fit explanation
- sends invitations
- tracks responses
        │
        ▼
SPEAKER
Accepts / declines
        │
        ▼
EVENT HOST
Receives confirmed speaker
        │
        ▼
EVENT
        │
        ▼
STUDENTS
Browse → Register → Calendar → Attend → Rate Speaker
```

---

## 24. Requirement Conflict Resolution History

Use this table to avoid implementing obsolete requirements.

| Requirement | Earlier Version | Current Version |
|---|---|---|
| Target organization | IA West | **CPP CBA** |
| Member role | Member | **Student** |
| Event requester role | Event Organizer / Volunteer | **Event Host** |
| Admin role | Chapter Admin | **Speaker Connector** |
| Matching factors | Topic + Proximity | **Industry + Role + Topic + Proximity** |
| Initial weights | Topic 70 / Proximity 30 | Superseded |
| Intermediate weights | Industry 40 / Topic 30 / Proximity 30 | Superseded |
| Final default weights | — | **Industry 30 / Role 25 / Topic 15 / Proximity 30** |
| Industry taxonomy | Unspecified | **20 NAICS sector groups** |
| Role taxonomy | Unspecified | **10 CBA-aligned roles** |
| Speaker classifications | Unspecified | **1 primary Industry + 1 primary Role** |
| Event classifications | Unspecified | **Multiple Industries + multiple Roles allowed** |
| Topic scoring | Generic relevance | **AI semantic fit + score + one-sentence explanation** |
| Missing Topic data | Unspecified | **Neutral/middle score** |
| Proximity | Generic | **Miles from CPP; 0–25 / 25–75 / 75+ bands** |
| Virtual events | Unspecified | **Ignore Proximity and redistribute its weight** |
| External speaker discovery | Ambiguous | **Explicitly out of scope** |
| Add events | Existing list emphasized | **Event Host can manually add event** |
| Add contacts | Existing list emphasized | **Speaker Connector can manually add contact** |
| Match display | 2–3 candidates, no ranked percentage | **Rank internally; return 2–3; avoid overall percentage emphasis** |

---

## 25. Implementation Priority

### P0 — Required

- [ ] Replace IA West terminology with CBA terminology.
- [ ] Rename Member → Student.
- [ ] Rename Event Organizer / Volunteer → Event Host.
- [ ] Rename Chapter Admin → Speaker Connector.
- [ ] Rename Chapter Admin Dashboard → Connector Dashboard.
- [ ] Rename Member Portal → Student Portal.
- [ ] Rename Volunteer Opportunity → Speaker Request.
- [ ] Remove membership / dues references.
- [ ] Keep one standard login.
- [ ] Assign roles from backend.
- [ ] Add Industry matching dimension.
- [ ] Add Role matching dimension.
- [ ] Set default weights to 30 / 25 / 15 / 30.
- [ ] Centralize matching weights in configurable settings.
- [ ] Add all 20 NAICS industry options.
- [ ] Add all 10 role categories.
- [ ] Speaker supports one primary Industry.
- [ ] Speaker supports one primary Role.
- [ ] Speaker Connector can correct Industry assignment.
- [ ] Speaker Connector can correct Role assignment.
- [ ] Event supports multiple Industries.
- [ ] Event supports multiple Roles.
- [ ] Add AI Topic comparison.
- [ ] Return one-sentence Topic reasoning.
- [ ] Use neutral Topic score when information is missing.
- [ ] Add distance scoring in miles.
- [ ] Implement 0–25 / 25–75 / 75+ distance bands.
- [ ] Ignore Proximity for virtual events.
- [ ] Return approximately 2–3 speaker candidates.
- [ ] Event Host can add a new event.
- [ ] Speaker Connector can add a new contact.
- [ ] Do not add external scraping/discovery.
- [ ] Add student speaker feedback/ratings.
- [ ] Keep month calendar at bottom of Events page.

### P1 — Workflow / usability

- [ ] Support Connector batch invitation workflow.
- [ ] Track invitation responses.
- [ ] Support confirmed-speaker handoff to Event Host.
- [ ] Support contact import/classification workflow.
- [ ] Allow Speaker Connector to modify matching weights.

### P2 — Lower priority

- [ ] CPP green/gold branding.
- [ ] Rewards/points refinements.
- [ ] Possible future career-readiness wording for rewards.

---

## 26. Known Unresolved Items

Do not silently invent permanent behavior for these items.

1. **Virtual-event weight redistribution**  
   Customer said to redistribute Proximity weight across the other three factors but did not specify the formula.

2. **Exact numeric proximity band scores**  
   Bands are specified, but exact values within each band are not.

3. **Student feedback schema**  
   Customer requested feedback/ratings but did not define rating scale or fields.

4. **Exact overall match UI**  
   Candidates should be ranked, but earlier direction said not to display a ranked percentage. Avoid a prominent overall match percentage unless later approved.

---

## 27. Delivery / Stakeholder Context

Non-functional context affecting priority:

- Original click-through functional-app target: **Friday, September 4, 2026**.
- Associate Dean is interested in a demo.
- Dean was invited as well.
- Demo availability was being collected for **September 8–11, 2026**.
- Friday at **11:00 AM** was proposed but not confirmed in the provided email.

Priority should remain:

```text
Functional correctness
        ↓
Terminology consistency
        ↓
Matching implementation
        ↓
Workflow completeness
        ↓
Optional branding/polish
```

---

## 28. Agent Implementation Rule

Before modifying behavior:

1. Compare the requested change against this document.
2. Preserve existing working functionality unless this document explicitly supersedes it.
3. Treat the **2026-09-04 matching requirements** as authoritative over earlier matching formulas.
4. Avoid expanding scope into external discovery, scraping, or unrelated redesign.
5. Flag unresolved requirements rather than inventing permanent product decisions.
