# HACS release packages

From v0.2.10, release workflows attach `journey_guardian.zip`. The HACS manifest
selects that asset with `zip_release` and `filename`; existing users update in
place without removing the integration or changing configuration.

The ZIP contains tracked integration runtime files only, rooted at `manifest.json`
and `__init__.py` so HACS can extract directly into its existing integration
directory. Tests check layout, required files, version alignment, reproducibility,
and exclusion of caches, tests and private local extras. Symlinks and unsupported
file types fail the build. The normal privacy scan remains a release gate.

Build locally after staging intended runtime additions:

```sh
python scripts/build_release.py --output dist/journey_guardian.zip
```

Only the validated release job uploads the artifact. Old immutable tags retain
their original installation method. Downloads of the ZIP become GitHub asset
download requests; they are not unique installations or active-user telemetry.
Updates and repeated downloads can increase the count, and HACS statistics may
refresh later. No tracking code, device identifiers or analytics service is added.

Sources: [HACS installer](https://github.com/hacs/integration/blob/main/custom_components/hacs/repositories/base.py)
and [HACS integration publishing guide](https://www.hacs.xyz/docs/publish/integration/).
