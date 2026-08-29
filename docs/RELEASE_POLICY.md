# Release policy

## Default completion contract

When the owner and development assistant agree that a code change is complete,
the default outcome is a usable public release, not an unpublished branch.

Completion means:

1. run the repository's local tests, lint checks, metadata checks, and privacy scan;
2. update the changelog and the integration version when required;
3. publish the accepted commits to `main`;
4. create the matching version tag and GitHub release;
5. verify the public release and report whether Home Assistant can be upgraded.

Work remains only on a feature branch or pull request when the owner explicitly
labels it as draft, experimental, review-only, or asks for publication to be held.

## Release safety

- Never publish with failing local validation.
- Keep the manifest version and release tag aligned.
- Do not disable legacy Home Assistant automations merely because a replacement
  integration release is available; cutover has separate acceptance gates.
- Prefer a small number of validated publication events over repeated remote CI
  runs during iteration.
- Confirm the release exists before telling the owner that an upgrade is ready.
