# Release policy

Changes are developed and validated before release. A merge or documentation edit
alone is not a published update, and a version increase alone does not install
anything in Home Assistant. Release notes identify the accepted release scope.

## Release safety

- Run the required tests, lint, metadata/privacy checks and platform validation.
- Keep integration metadata, tag and package versions aligned for a release.
- Mark prerelease tags/releases correctly; do not advertise beta work as stable.
- Publish only the intended, validated commit and verify its release assets.
- Do not move existing published tags or replace their contents.
- Documentation-only maintenance may be merged without a new version or release.
- Publishing an integration does not approve live installation or legacy cutover.
  Keep independent alarms and legacy workflows until their acceptance gates pass.

See [release packaging](RELEASE_PACKAGING.md) for HACS archive layout and download
statistics, and [reliability and acceptance](RELIABILITY.md) for remaining evidence
boundaries. Owner-specific development agreements are not public contributor rules.
