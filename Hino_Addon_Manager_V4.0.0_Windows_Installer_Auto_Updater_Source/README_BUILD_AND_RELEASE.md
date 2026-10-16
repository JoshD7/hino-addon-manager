# Hino Addon Manager V4.0.0 — Windows installer / self-update foundation

This project builds a **real Windows EXE installer** on GitHub Actions. The Linux build environment used to prepare this source cannot itself produce or run that installer. Do not call the source ZIP a Windows installer.

## First installation

1. Upload/commit this project's contents (including `.github/workflows/windows-release.yml`) to `JoshD7/hino-addon-manager`. Do **not** commit your CurseForge API key or personal configuration files.
2. Open GitHub > Actions > **Build Windows installer** > **Run workflow**. This creates a downloadable installer artifact for a first smoke test, but does not publish a release.
3. Download the build artifact; unzip it and run `HinoAddonManager-Setup.exe` on Windows. It installs under your user profile, creates a Start Menu shortcut and an optional desktop shortcut. Python is not needed.
4. Test opening, local scanning, saved API key, update checks, uninstallation, and whether your antivirus allows it. Unsigned Windows installers may show SmartScreen warnings; the release is NOT digitally signed.

## Enable updates via published releases

1. Change **all three** version strings together for each future release: `hino_selfupdate.py` `APP_VERSION`, `HinoAddonManager.py` window title, and `HinoAddonManager.iss` `AppVersion`.
2. Commit and push the matching source. Tag the commit `v4.0.0` (or the next release, `v4.0.1`, etc.) and push the tag. The workflow builds and publishes two GitHub Release assets **with exact names**:
   - `HinoAddonManager-Setup.exe`
   - `HinoAddonManager-Setup.exe.sha256`
3. The installed app checks GitHub's **latest published, non-prerelease** automatically at startup (only for the packaged EXE) and manually from Settings > Check Hino app update.
4. When a new release is available, the user consents; Hino downloads the installer, checks its SHA-256 against the companion asset, starts the setup, and closes. The installer updates the same per-user installation. WoW addons and ~/.hino-addon-manager*.json are left untouched.

## Security / limitations

- SHA-256 validation protects against corrupted/mismatched artifacts. It is **not** publisher authentication if someone can alter both GitHub release files. Use Windows Authenticode code-signing before distributing publicly.
- GitHub releases must be publicly readable for anonymous API checking; private repositories need authenticated update code, which this build does not include.
- This is **user-approved updating**, not forced unattended background installing.
- The actual Windows installer has not been run in this environment. Treat this as a release candidate until the workflow passes and is tested on Windows.
- The update mechanism downloads the **Hino application**, not CurseForge addon ZIPs. CurseForge automatic downloads remain disabled.
- Inno Setup installs **per user** under LocalAppData and doesn't require admin privileges.
- Release workflow requires repository Actions permissions to create releases. If organization restrictions block publishing, enable appropriate repository workflow permissions.
- If an installer fails, rerun the previously installed setup. Configuration persists separately in the user's home directory.
