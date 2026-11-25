<p align="center">
  <img src="assets/banner.png" alt="Deals - Australian deal finder" width="100%">
</p>

<p align="center">
  <b>Find the real deals across Australian shops - without opening fifty tabs.</b><br>
  Search once, see genuine discounts first, and get alerted when the price you want shows up.
</p>

<p align="center">
  <a href="https://github.com/M000Nz/Deals/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/M000Nz/Deals?style=flat-square&color=10b981&label=release"></a>
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows-0a0a0a?style=flat-square">
  <img alt="Region" src="https://img.shields.io/badge/region-Australia-0a0a0a?style=flat-square">
  <img alt="Sources" src="https://img.shields.io/badge/sources-180%2B-10b981?style=flat-square">
  <img alt="Privacy" src="https://img.shields.io/badge/data-stays%20on%20your%20PC-0a0a0a?style=flat-square">
</p>

<p align="center">
  <a href="#download">Download</a> ·
  <a href="#what-it-does">Features</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#a-quick-tour">Tour</a> ·
  <a href="#faq">FAQ</a> ·
  <a href="#for-developers">Developers</a>
</p>

---

## Download

1. Open the **[latest release](https://github.com/M000Nz/Deals/releases/latest)** and download **`Deals-Setup.exe`**.
2. Run it. No Python or other software is needed, and it installs for your user only (no admin prompt).
3. Open **Deals** from the Start menu or the desktop icon.

> **Windows SmartScreen warning?** The app isn't code-signed yet, so Windows may say it "protected your PC".
> Click **More info → Run anyway**. Each release ships with a SHA-256 checksum (`Deals-Setup.exe.sha256`) so you can verify it.

**Updates are automatic.** Deals checks for a new version every time it opens. When one is available you press
**Update** and it downloads, verifies the checksum, installs and reopens itself.

Your watchlist, price history and settings live in `%APPDATA%\Deals`, so updating never touches them.

---

## What it does

| | |
|---|---|
| **Search everything at once** | One search asks 180+ Australian sources: major retailers, specialist shops, [StaticICE](https://www.staticice.com.au) (200+ more shops) and OzBargain. The first results appear in seconds and improve while slower shops finish. |
| **Real discounts first** | A result only counts as a deal if there's evidence: a marked-down price, a price that fell since your last check, or a vetted OzBargain post (with its discount code when it lists a real one). Everything else sits under *Regular prices*. |
| **Watchlist with alerts** | Follow a product, set a target price, and get alerted on desktop, ntfy, Discord, Telegram or email. Each item keeps a price-history graph and a **Buy now / Wait / Fair price** verdict based on its own history and the sale calendar. |
| **Daily deals** | The biggest discounts on big-ticket items, refreshed daily. Pick a **category** (golf, cycling, camping, music, gaming...) to search that hobby directly. |
| **For you** | Suggestions based on what you follow and like, with a few outliers mixed in. **Find more** gives you a fresh page every time; **Interested** finds similar deals straight away and **Not interested** clears that brand and type. |
| **Daily digest (opt in)** | Pick up to 5 categories and get the best new deals in just those, once a day, to your phone or inbox. Off unless you turn it on. |
| **Paste a link** | Paste any product link and Deals finds the same product at every other shop - confirmed by barcode or model code, with different models left out. |
| **Exact matches** | Model numbers are respected - *galaxy watch 6* never shows a Watch 5. Name a brand and only that brand appears. |
| **Spelling forgiven** | *samsnug galxy* and *play station 5* are corrected automatically. |
| **Honest prices** | Inflated "was" prices are flagged, junk listings (stickers, cables, parts priced 90%+ below normal) are dropped, and sale-season reminders tell you when to trust the price history. |
| **Shared shop list** | New shops and fixed search addresses arrive from this repo each time Deals opens - no app update needed. |
| **Private and light** | Everything stays on your computer. Runs at low priority so it never slows your other programs. |

---

## How it works

```
  You search  ──►  Deals picks the shops that fit the product  ──►  reads each shop in parallel
                                                                            │
   Alerts  ◄──  Watchlist re-checks on a schedule  ◄──  ranks by relevance, then by real discount
```

1. **Smart store selection.** Searching *makita drill* visits hardware, general and price-comparison shops - not the beauty or fashion ones. If your words don't hint at a product type, every shop is searched. If a search finds very little, Deals **automatically widens** it to every remaining shop.
2. **Reading the shop.** Prices are read from each shop's own price markup first. Shops that only show prices after JavaScript runs are opened in a hidden browser (**Microsoft Edge or Chrome** if you have it - nothing big to download).
3. **Ranking.** Results are ranked by relevance, then real discounts. Accessories (cases, straps, bands) move down. Out-of-stock and refurbished listings are never counted as deals.
4. **Self-healing sources.** Shops that keep failing are paused automatically so searches stay quick, and **Repair** tries to find a working search address for them.
5. **Alerts.** The Watchlist re-checks on the schedule you choose and alerts you once per deal, with optional quiet hours and a daily summary.

### What counts as a "deal"?

A result is a deal when at least one of these is true: the shop shows a **was price**; it's an **OzBargain post** that states a discount (or is clearly cheaper than other shops); or its **price fell** since your last check. Deals also get a **0-100 score** that blends the real discount, whether it's the lowest price seen, reviews, the price against other shops and OzBargain votes.

---

## A quick tour

**Search** - A centred search box with chips for your watchlist and recent searches. Results show large product photos, with real discounts in green under *Deals*.

**Watchlist** - Each item shows its best price, your target, a price-history graph (click for the full list) and quick actions. Collapse any item - or all of them - to a single line with a small graph of the change since the last check (green ▼ cheaper, red ▲ dearer).

**Daily deals** - Big-ticket items at least 25% below their normal price. The **category** picker steers the search itself, so choosing *Golf* goes and looks for golf deals rather than just filtering what's already there. **Sort** and **Shuffle** only change the order.

**For you** - Press **Interested** or **Not interested** and suggestions improve. If you press **Find more** several times without reacting, it switches to other categories. **Reset recommended** starts again from scratch.

**Sources** - Every shop with a switch, a status and the *reason* it failed if it did. **Test** one shop or all of them.

**System tray** - Deals keeps an icon in the notification area (look under the small ^ arrow by the clock). Its tooltip and menu show what it's doing, including while it checks your watchlist or installs an update. Right-click it for **Open**, **Check watchlist now**, **Quit Deals** and **Force quit**. In **Settings → close button**, choose whether the window's X quits Deals or keeps it running in the tray so alerts keep working.

**Look and feel** - A dark, minimal interface with a single emerald accent, a rounded custom window, smooth scrolling and a light theme if you prefer it (sun/moon toggle, top right).

### Shortcuts

| Key | Action |
|---|---|
| `Ctrl+K` or `/` | Jump to search |
| `Ctrl+L` | Focus the search box |
| `Ctrl+R` | Check the watchlist now |
| `Ctrl+H` | Back to the home screen |

---

## FAQ

**Does it cost anything or need an account?** No. There's no account, no API key and no subscription.

**Is my data sent anywhere?** No. Your watchlist, history and settings stay in `%APPDATA%\Deals`. Alert passwords are kept in your system's password store when the optional `keyring` add-on is available.

**Why does a shop show "Bot-check page shown" or "Needs JavaScript"?** Some shops block automated visits. Deals tries a hidden browser for those; shops with serious bot protection can't always be read, and are paused so they don't slow searches. Press **Verify** beside the shop in Sources: a real browser window opens, you pass the check once, close it, and Deals reuses that session for later searches (it only works for checks a person can pass). You can also use **Test** on one shop, or **Repair**, to retry. StaticICE, Getprice and OzBargain still cover many of the shops that block direct visits.

**Why isn't eBay in the results?** It's hidden by default, whether it comes directly or through OzBargain. Add or clear hidden sites in **Settings → hidden sites**.

**A price looks wrong.** Prices are read automatically and can occasionally be wrong - check the shop before you buy. Right-click a card → **report** to hide it for good.

**Something isn't found.** Try the model number, or a simpler name. Deals widens thin searches by itself, and you can add shops under **Sources → add custom**.

**Where are the error logs?** In `%APPDATA%\Deals` (`deals_error.log`, plus `price_check.log` and `image_check.log` for diagnostics).

**Back up or move my data?** **Settings → back up / restore database**. Restoring reopens the app automatically.

---

## Privacy and fair use

Deals is for **personal use**. It reads public pages the way a browser would, one request at a time per site, and stops asking sites that refuse it. Store websites can change or block this at any time, and their terms may restrict automated access - so don't use it to resell data or run it at high volume. Prices and reviews are read automatically: always check the shop before you buy.

---

## For developers

<details>
<summary><b>Run from source, build and release</b></summary>

### Run from source

Needs Python 3.10+ and the packages in `requirements.txt`.

```bash
pip install -r requirements.txt
python DealScraper.pyw        # or double-click start.bat (Windows) / start.command (Mac)
python selftest.py            # checks the price reader against saved example pages
```

`DealScraper.pyw`, `engine.py` and `ui_kit.py` must all be the same version and sit in the same folder.

### Project layout

| File | Purpose |
|---|---|
| `DealScraper.pyw` | The app: screens, dialogs and window behaviour |
| `engine.py` | Searching, store handling, price reading, ranking, watchlist, alerts, updates |
| `ui_kit.py` | Custom widgets, the frameless window and the icon |
| `selftest.py` + `Fixtures/` | Price-reader checks (also run inside the built exe) |
| `installer.iss` | Inno Setup installer script |
| `.github/workflows/release.yml` | Builds, self-tests and publishes releases |
| `Version.txt` | Newest version plus the release notes shown in the app |

### Publish a release

1. Raise `ENGINE_VERSION` in `engine.py`, and the matching check in `DealScraper.pyw`.
2. Put the version on the first line of `Version.txt`, the repository URL on the second, then one `note:` line per change.
3. Commit and push, then run the **release** workflow (Actions → *Run workflow*) with the tag, e.g. `v86`.

The workflow builds the app with PyInstaller, runs `--selftest` on the built exe, builds the installer with Inno Setup and publishes `Deals-Setup.exe` with its `.sha256` to the release. `build_exe.bat` is only for local test builds.

### Adding or fixing a shop (no release needed)

Shops live in **`stores.json`** at the root of this repo. Every copy of Deals downloads it each time it opens and
merges it into its Sources, so a fix reaches everyone at their next launch - no new installer.

```json
{"name": "Example Shop", "url": "https://example.com.au/search?q={query}", "cats": ["tech", "gaming"],
 "browser": false, "enabled": true, "note": "shown in Sources"}
```

- Add or edit a line, then **raise `version`** at the top (the app ignores a list that isn't newer).
- `enabled: false` pauses a shop for everyone (users can switch it back on). `browser: true` marks shops that need the hidden browser.
- Only `https` addresses containing `{query}` are accepted; malformed entries are skipped, and a broken file is ignored.
- It overrides the built-in list in `engine.py`, which is the fallback for offline and first launch.
- Shops that need new parsing code still need a normal release.

### Tuning

`DAILY_MIN_PRICE`, `DAILY_MIN_PCT` and `DAILY_CATS` control Daily deals. `WIDEN_BELOW` sets when a thin search widens to every shop. `POOL_WORKERS` limits how many shops are read at once.

</details>

---

<p align="center"><sub>Deals* - made in Australia, for Australian shoppers.</sub></p>
