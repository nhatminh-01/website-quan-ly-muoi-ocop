# Login artwork and visual verification

The login page now uses `assets/login-hero.png` (1198 × 1313, PNG) instead of CSS scenery. The stylesheet is scoped to `login-v11-*` in `assets/login.css`; the only change in `server.py` registers those two static assets. The existing submit script, field names, remember helpers, session duration, authentication handlers, and bootstrap files are unchanged.

## Artwork provenance

Source: the screenshot supplied by the user on 2026-09-18, `codex-clipboard-f5f98c60-6f4b-4995-b278-27e21fc63f30.png`.

Mode: built-in ImageGen **edit**, using the screenshot as the edit target. This is an image-edit output based on the supplied artwork, not a pixel-identical crop. The two requested central slogan lines were removed and their background filled; the other text and composition were checked visually. No CSS scenery or rectangular cover is used.

Final prompt:

> Use case: precise-object-edit. Input image is the edit target, not inspiration. Produce a standalone hero asset by extracting ONLY the entire LEFT illustrated panel of the supplied screenshot (original x=0..859, y=0..941). Output portrait aspect ratio 859:941, no white right-hand login form, no border or extra margin. Keep the original artwork EXACTLY as closely as possible: same leafy top left canopy, pale green sky, perfectly circular official green-and-gold seal at original x290..563 y92..364 without stretching or redesigning, exact remaining Vietnamese agency headings below it, same agriculture/greenhouses/river/Ho Chi Minh skyline, white glowing digital hexagon icons and connecting lines, all lower green sweeping waves/foliage and original three footer icons/captions. This is extraction and localized cleanup, not a new illustration. ONLY remove the TWO small tagline lines in the sky immediately below the large agency headings: 'NÔNG THÔN PHÁT TRIỂN – NÔNG NGHIỆP BỀN VỮNG' and 'VÌ THÀNH PHỐ XANH, HIỆN ĐẠI' (original y481..516), reconstructing the soft green sky/haze behind them seamlessly, no visible rectangle, no blur strip, no new text. Preserve the large words 'CHI CỤC PHÁT TRIỂN NÔNG THÔN' and 'THÀNH PHỐ HỒ CHÍ MINH', preserve all seal lettering, preserve the bottom captions 'NÔNG NGHIỆP BỀN VỮNG', 'NÔNG THÔN HIỆN ĐẠI', 'VÌ CỘNG ĐỒNG PHÁT TRIỂN'. Keep all relative positions, colors, proportions and details of the original left panel. No other changes.

## Browser verification

`tests/test_login_visual_browser.py` starts the real application HTTP handler on a temporary loopback port, using the existing v1.1 bootstrap without running application startup. A DB guard fails the test if it attempts to access the application database. Credential submissions use dummy values and are intercepted before reaching the backend.

Enable with `OCOP_TEST_BROWSER=1` and run:

```sh
python -B -m unittest discover -s tests -p 'test_login*.py' -v
```

Install Playwright and Chromium first, as the existing CI workflow already does. Optionally set `LOGIN_BROWSER_EXECUTABLE` to an installed Chromium-based browser. Set `LOGIN_SCREENSHOT_DIR` to an output directory to save the three full-page captures. Mobile capture uses a 390 × 844 viewport and includes the scrollable footer.

Checked at 1920 × 1080, 1440 × 900 and 390 × 844:

- Desktop columns 51.4% / 48.6%; artwork uses `object-fit: cover`, never stretching the seal.
- Card, inputs and creator attribution compared visually with the supplied screenshot.
- Mobile crop anchored at the top so the entire seal and agency headings remain visible.
- No horizontal overflow; desktop card fits within the viewport.
- Existing remember control remains usable, restores only the username, clears when unchecked, and never persists the password.
- Error message stays escaped and readable on mobile; form endpoint and input contracts remain unchanged.

Local full suite: 91 discovered, 45 passed, 46 PostgreSQL integration tests skipped without a disposable test DSN. PostgreSQL and remaining browser regressions run in the existing GitHub Actions workflow.
