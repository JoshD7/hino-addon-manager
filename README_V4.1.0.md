# Hino Addon Manager V4.1.0 — safer CurseForge workflow

This release keeps the minimal My Addons interface and existing self-updater.

## Changes
- Discover has **Open Forever release** and **Install downloaded ZIP** actions.
- A metadata-only CurseForge update in My Addons can open its **official file page** after confirmation instead of presenting a nonfunctional update action.
- CurseForge URLs come from the official mod metadata endpoint and are validated to remain on the CurseForge website.
- Existing downloaded-ZIP installation still performs WoW interface checks, staging, backups, and rollback.
- No direct CurseForge API downloads are implemented. The API key remains in Windows Credential Manager when saved.

## Important limitations
- Forever/1.60.1 labels are only metadata evidence, not compatibility guarantees.
- The manager deliberately does not automatically download CurseForge files or bypass distribution restrictions.
- Close WoW before installing an addon ZIP.
- V4.0.3 remains the confirmed working fallback until V4.1.0 passes Windows tests.

## Publish
Create the `v4.1.0` tag from main. Wait for the Windows installer workflow to complete and check both release assets:
`HinoAddonManager-Setup.exe` and `HinoAddonManager-Setup.exe.sha256`.
Then update the installed application through Settings > Check Hino app update.

## Smoke test
1. Launch via desktop shortcut.
2. Check Updates; verify CurseForge projects show the correct latest metadata and manual-update status.
3. Discover > search Polestar Guides > select project > Open Forever release.
4. Confirm browser opens the official CurseForge file page (not a third-party mirror).
5. Download a compatible ZIP manually and install via Add addon > Install downloaded ZIP; confirm backups appear.
6. Verify GitHub Update all and application self-updater still work.
