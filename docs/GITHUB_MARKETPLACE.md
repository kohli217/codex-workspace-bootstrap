# GitHub Marketplace listing

This document is the maintainer source of truth for publishing the free **CWB Preflight** GitHub App in GitHub Marketplace.

The direct public installation remains available independently of Marketplace.

## Listing identity

- **Listing name:** CWB Preflight
- **App:** https://github.com/apps/cwb-preflight
- **Primary category:** Code quality
- **Secondary category:** Code review
- **Supported languages:** leave empty; CWB is repository/tooling-oriented rather than language-specific

### Very short description

> Preflight checks for AI coding instructions and repository readiness

### Introductory description

> CWB Preflight checks public repositories before AI coding agents act, catching conflicting instructions, invalid package scripts, risky tracked environment files, and repository-readiness gaps on pushes and pull requests.

### Detailed description

### Catch instruction drift

CWB compares repository guidance used by Codex, Claude Code, Gemini CLI, Copilot, Cursor, Cline, Continue, and related tools so conflicting package-manager or validation instructions are visible before an agent follows them.

### Validate commands against repository evidence

Documented npm, pnpm, Yarn, and Bun validation commands are checked against package manifests, workspace targets, directory routing, and monorepo evidence without executing commands from the repository.

### Run automatically in GitHub

Install the App on selected public repositories. Supported pushes and pull-request updates trigger an exact-revision preflight and publish a CWB Preflight Check Run on the inspected commit.

### Free and public-repository-only

The hosted App is free and intentionally supports public repositories only. Private-repository events are rejected before they enter the public Actions worker.

## Required URLs

- **Customer support URL:** https://github.com/kohli217/codex-workspace-bootstrap/blob/main/SUPPORT.md
- **Privacy policy URL:** https://github.com/kohli217/codex-workspace-bootstrap/blob/main/PRIVACY.md
- **Documentation URL:** https://github.com/kohli217/codex-workspace-bootstrap/blob/main/docs/GITHUB_APP.md
- **Company/project URL:** https://github.com/kohli217/codex-workspace-bootstrap
- **Status URL:** omit for now; there is no dedicated status page

The GitHub App itself uses its Setup URL rather than a Marketplace Installation URL.

## Free pricing plan

- **Plan name:** Free
- **Pricing model:** Free
- **Available for:** Personal accounts and organizations
- **Short description:** Free preflight checks for selected public repositories

Suggested plan bullets:

- Automatic checks on supported pushes and pull requests
- AI instruction-integrity and repository-readiness checks
- Monorepo-aware package-script validation
- Public repositories only, with no paid tier

No paid service is offered outside GitHub Marketplace.

## App settings required before submission

After the Marketplace-enabled Worker is deployed, configure the public GitHub App:

- **Setup URL:** `https://<current-worker>.workers.dev/marketplace/setup`
- add an OAuth **Callback URL:** `https://<current-worker>.workers.dev/marketplace/oauth/callback`
- leave **Request user authorization (OAuth) during installation** disabled; the Setup URL explicitly starts the OAuth web flow
- keep the existing repository permissions unchanged:
  - Checks: read/write
  - Contents: read-only
  - Pull requests: read-only
- keep normal App webhook subscriptions unchanged:
  - Push
  - Pull request

The OAuth callback exchanges the temporary code, calls GitHub's authenticated-user endpoint to verify identity, revokes the single user access token, and does not persist that token.

## Marketplace webhook

The Marketplace listing has a separate webhook configuration.

- **Payload URL:** `https://<current-worker>.workers.dev/webhooks/marketplace`
- **Content type:** `application/json`
- **Secret:** use the value generated locally by `deploy.ps1 -EnableMarketplace`
- **Active:** enabled

The endpoint accepts GitHub's `marketplace_purchase` lifecycle events. CWB stores only numeric account ID plus minimal plan state. On cancellation, CWB persists the inactive state first, then requests removal of the matching CWB Preflight installation with an App JWT. This makes scan suppression fail-closed if GitHub's uninstall API is temporarily unavailable. Cancellation records expire within 30 days.

## Contact information

GitHub's draft-listing UI requires publisher contact information. Use an email address controlled by the maintainer that can receive GitHub Marketplace onboarding messages.

Do not put a private credential, GitHub token, or Cloudflare secret in any contact field.

## Marketplace images

GitHub requires Marketplace listing imagery.

### Logo

- custom square image;
- at least 200 × 200 px;
- transparent background preferred;
- no text in the logo.

### Feature-card background

- exactly 965 × 482 px;
- use a pattern/texture rather than small text;
- select a high-contrast app-name text color in the Marketplace editor.

### Product screenshots

Use real GitHub UI, not synthetic product claims.

Prepare at least these two screenshots at the same dimensions, each at least 1200 px wide:

1. a completed **CWB Preflight** Check Run showing READY or a clear finding;
2. the pull-request or commit Checks view showing CWB Preflight attached to the exact revision.

Crop the browser chrome; include only the page content.

## Draft and review sequence

1. Deploy Marketplace endpoints with `deploy.ps1 -EnableMarketplace`.
2. Configure Setup URL and OAuth callback URL in the CWB Preflight GitHub App.
3. Open https://github.com/marketplace/new and create the draft listing for CWB Preflight.
4. Enter the listing copy and required URLs from this document.
5. Create the **Free** plan using the values above.
6. Configure the Marketplace webhook with the printed Worker URL and locally generated secret.
7. Upload the logo, feature card, and real product screenshots.
8. Complete the publisher contact information.
9. Exercise the draft Marketplace purchase/onboarding flow and confirm the OAuth callback plus Marketplace webhook delivery succeed.
10. Read and accept the GitHub Marketplace Developer Agreement.
11. Submit the listing for GitHub review.

The final draft creation, contact email entry, secret entry, Developer Agreement acceptance, and **Submit for review** are owner-only GitHub UI actions and must not be automated with shared credentials.
