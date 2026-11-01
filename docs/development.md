# Development and releases

[Back to the getting-started guide](../README.md)

## Develop the editor

The editable frontend sources are **TypeScript and SCSS** in `editor/src/`. Do not edit the generated `actions/analog-meter-reading/ui/editor.js` or `editor.css` directly.

```sh
cd editor
npm ci
npm run build
```

The build runs strict TypeScript checking, bundles the ES module and compiles SCSS. Generated assets are included in the Action package; Studio needs no Node.js toolchain at runtime. Python handles image processing and inference.

Studio's development Compose configuration mounts this repository read-only at `/local-actions`. Refresh the local source in Settings → Action repositories. Create an Analog Meter Reader, or save/discard changes, deactivate an existing instance and select **Reload from source**. Running instances remain pinned to their installed source. Identity, routes and request history are preserved.

## Release packages

Generated JS and CSS are build outputs and are not tracked in Git. Build locally
before refreshing a local development source. Production installation uses the
built GitHub Release asset, rather than the source archive or a Git branch.

In Studio Settings → Action repositories, choose **GitHub Release**, enter this
repository's public HTTPS URL and use `latest` (latest published stable release)
or an explicit stable release tag. Refresh updates the creation catalog only;
existing Actions remain pinned to their installed snapshot, including after restart.

To prepare a release, set `actions/analog-meter-reading/action.json` to the desired
version, commit the sources and push the matching `v<version>` tag. The release
workflow installs locked editor dependencies, runs editor tests and the build,
checks packaging, and publishes `ha-ai-studio-actions.zip` with
`ha-ai-studio-actions.zip.sha256`. Tags containing a hyphen publish prereleases,
which Studio does not install. PRs and manual workflow runs validate and upload a
CI artifact without publishing a release. A release is published only after all
build checks pass. Existing release assets are never overwritten by this workflow.

The archive includes both Actions and the Device templates, preserves the Action directories, and includes the Python runtime,
models, notices, manifest, lockfile and compiled editor, and uses an explicit file
allowlist. Add new runtime files to `scripts/package_release.py`. Never add private
images, settings, credentials or development data to that allowlist.

### AI release notes

Maintain a non-empty `## <version>` section in `CHANGELOG.md` for every release,
matching the Action manifest and tag. Tagged releases generate an English AI
summary and highlights using the organization's `OPENAI_API_KEY` Actions secret;
its repository access policy must include this repository. Optionally set the
`OPENAI_RELEASE_MODEL` Actions variable (default: `gpt-4o-mini`). The key is only
provided to the release-notes step, never PR builds or the distributed Action.

Only the versioned changelog and bounded commit subjects are sent to the API,
with response storage disabled. The maintained changelog and installation notes
are always included. Missing credentials, API failures or invalid AI output fall
back to the changelog with a generic workflow notice; missing release changelog
entries fail publication. PR checks test generation with mocked API responses.
