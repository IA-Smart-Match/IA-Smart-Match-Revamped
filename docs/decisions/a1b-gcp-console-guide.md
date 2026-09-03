# A1b Part 1 — GCP Identity Platform console guide

**Owner / provisioner:** Danny Tran (@dangt) — named 2026-09-03.
**Worksheet:** `docs/decisions/a1b-idp-configuration-worksheet.md`
**Status:** Tenant procured; Part 1 fields outstanding.

Complete these steps in Google Cloud Console, then transcribe values into the worksheet (no invented URLs).

---

## Task checklist

- [ ] Confirm GCP project ID for dev/test Identity Platform tenant
- [ ] Enable Identity Platform API (if not already)
- [ ] Create or locate OAuth 2.0 client (Web application) for SmartMatch dev
- [ ] Register redirect URI(s) for local dev (`http://localhost:5173/...` or compose URL)
- [ ] Copy issuer, JWKS URI, client ID, audience into worksheet §1.2–1.3
- [ ] Record PKCE yes/no and scopes (`openid`, `email`, `profile` minimum)
- [ ] Sign worksheet §1.4 approval block
- [ ] Commit worksheet; notify engineering for JWKS verifier (feature flag)

---

## Where to find each field

### Tenant / directory identifier

1. [Google Cloud Console](https://console.cloud.google.com/) → select your **dev/test project**.
2. **Identity Platform** → **Settings** (or **Tenants** if multi-tenant).
3. Record **Project ID** and any **Tenant ID** shown for the dev tenant.

### Issuer (`iss`) and JWKS URI

For Google Identity Platform / Firebase Auth style OIDC:

1. Identity Platform → **Settings** → note the **Issuer** URL (often `https://securetoken.google.com/<project-id>` for Firebase-compatible tokens, or your tenant-specific issuer).
2. JWKS URI is typically `<issuer>/.well-known/jwks.json` or from the OIDC discovery document:
   - Open `https://<issuer>/.well-known/openid-configuration` in a browser (from a machine with access).
   - Copy `jwks_uri` and `issuer` exactly.

**Environment variables consumed by code:** `SMARTMATCH_JWKS_ISSUER`, `SMARTMATCH_JWKS_AUDIENCE`, `SMARTMATCH_JWKS_URI`.

### Audience (`aud`)

Usually the **Firebase project ID** or OAuth client audience string Google documents for your token type. Match what appears in tokens from a test login.

### Client ID and redirect URIs (card A2)

1. **APIs & Services** → **Credentials** → **OAuth 2.0 Client IDs**.
2. Create **Web client** (or use existing dev client).
3. **Authorized JavaScript origins:** `http://localhost:5173`, `http://localhost:8080` (adjust to compose ports).
4. **Authorized redirect URIs:** match your legacy frontend OIDC callback path (e.g. `http://localhost:5173/auth/callback`).
5. Record **Client ID**; confirm **PKCE** for public SPA client (recommended: yes).

### Scopes

Minimum pilot: `openid email profile`. Add institutional claims only if IdP provides them.

### Signing algorithms

Default shipped verifier: **RS256** only (`SMARTMATCH_JWKS_ALGORITHMS`). Confirm tenant uses RS256.

### Session / refresh / logout

Record institutional policy in worksheet §1.3:

- Refresh tokens: yes/no for dev client
- Session lifetime: console session settings or app policy
- Logout: end-session endpoint from discovery document if used

---

## After transcription

1. Fill every OUTSTANDING cell in `a1b-idp-configuration-worksheet.md`.
2. Set owner approval §1.4: Danny Tran, date, admin console URL.
3. Commit with message referencing P2 / V7.
4. Engineering may implement live JWKS verifier behind `SMARTMATCH_JWKS_ENABLED` (or equivalent feature flag) — no production deploy required.

---

## Do not

- Commit service account keys, client secrets (if confidential client), or `.env` files.
- Invent issuer/JWKS values — worksheet rule stands.
