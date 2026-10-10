# Static Security and Privacy Review

Date: 2026-10-10  
Release reviewed: 0.2.0-beta.12

## Scope

The review covered the integration source, tests, scripts, documentation,
GitHub Actions, current tracked files, and Git history. It focused on committed
secrets, personal or journey data exposure, credential handling, diagnostic and
log output, provider requests, release controls, and obvious reliability flaws.

## Findings fixed

1. **Saved credentials were returned as options-form defaults.** Provider
   credentials are no longer sent back to the browser. Leaving a field blank
   preserves the saved value on the Home Assistant side.
2. **Downloaded diagnostics contained journey-identifying data.** Diagnostics
   now retain operational classifications and counts while excluding entity and
   config-entry identifiers, station and service details, exact evidence times,
   journey fingerprints, and request fingerprints.
3. **The current public tree contained installation-specific route examples.**
   Those examples, station shortcuts, coordinates, and route codes were replaced
   with neutral data. The privacy scanner now checks for their reintroduction as
   well as common API-token, private-key, and installation-identifier formats.
4. **Release publication was not gated by validation.** A tag now creates a
   release only after the full tests, lint, privacy scan, Hassfest, HACS checks,
   and tag/version match succeed. Pull requests to `main` also run validation.
5. **A route-specific station lookup limited safe public use.** Station identity
   now comes from an explicit calendar CRS code or provider resolution instead
   of a built-in map tied to one installation.
6. **Beta tags were published as stable GitHub releases.** Tags containing a
   prerelease suffix are now explicitly published as prereleases so public
   update metadata accurately represents their support level.

No committed API keys, passwords, access tokens, private keys, personal email
addresses, Home Assistant remote URLs, or concrete person/calendar entity IDs
were found in the current tree. Token and private-key patterns were also absent
from Git history.

## Residual privacy considerations

- Older Git commits and tags still contain the former route examples. Removing
  them would require a destructive public-history rewrite, so this review does
  not alter history.
- Home Assistant config entries continue to hold provider credentials, and
  private Home Assistant storage retains bounded journey evidence needed for
  arrival matching and the Delay Repay review. Protect the Home Assistant host,
  backups, and diagnostic downloads accordingly.
- Live provider features necessarily send the requested stations and travel
  time to the selected rail provider. Google route timing sends its configured
  origin and station destination to Google when that optional feature is used.
- Home Assistant entity states expose active journey information to users and
  integrations that already have access to the Home Assistant instance. This is
  functional local output, not public telemetry.

## Verification

- 169 tests passed on Python 3.14.2 with Home Assistant 2026.8.0.
- Ruff, Bandit, the repository privacy scan, compilation, dependency consistency,
  JSON parsing, workflow YAML parsing, and whitespace checks passed.
- The diagnostics and credential changes have focused regression tests.
