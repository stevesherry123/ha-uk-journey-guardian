# Roadmap

This is a high-level direction, not a delivery promise or evidence of real-world
acceptance. Consult the installed release's README and changelog for supported
behaviour, and [feature comparison](docs/FEATURE_COMPARISON.md) for capability limits.

## Priorities

- Strengthen trustworthy live-rail evidence, retained monitoring and restart-safe
  notifications within provider budgets.
- Validate direct, return and split/interchange journeys against representative
  provider evidence and real travel before relying on them operationally.
- Improve early-termination recognition and bounded disruption recovery without
  inferring cancellation or railway arrival from GPS proximity alone.
- Make notification preferences, harmless previews/test delivery and dedicated
  adapters clearer while retaining explicit opt-in and independent fallback alarms.
- Improve privacy-safe explanation, post-journey evidence and onboarding without
  representing screening results as compensation eligibility or claim submission.
- Assess optional destination/local-transit and provider-neutral flight modules
  separately from the supported UK rail path.

Keep user intent, provider acquisition, state modelling, decisions and request
budgeting separate. Do not remove legacy workflows until the applicable cutover
checks and observation succeed. See [reliability](docs/RELIABILITY.md),
[isolated rehearsal](docs/COMMUTE_REHEARSAL.md) and
[release policy](docs/RELEASE_POLICY.md).

Detailed working plans and owner-specific agreements are maintained separately
from the public product docs. Suggestions and reproducible bugs belong in GitHub
Issues; code/test instructions and ADRs remain public for contributors.
