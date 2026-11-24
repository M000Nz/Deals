# Deals - Australian deal finder

**Start it:** double-click `start.bat` (Windows) or `start.command` (Mac).
Needs Python from https://www.python.org/downloads/ (Windows: tick "Add python.exe to PATH").
First launch installs the small add-ons and offers to set up **browser mode** (below).
**`DealScraper.pyw`, `engine.py` and `ui_kit.py` must all be the latest versions, in the same folder.**

## Where prices come from (Australia only)
| Source | What it gives you |
|---|---|
| **StaticICE** | Price comparison across 200+ Australian retailers, with the real shop link |
| **OzBargain** | Community deals from its public RSS feeds, with their end time. Shown **only when the price is discounted** (see below) |
| **~108 Australian stores** across tech, home, DIY, garden, fashion, sports, outdoors, baby, toys, pets, beauty, auto, books, grocery and more (not eBay) | Direct search of each store's site |

### Browser mode (JavaScript stores)
Many stores only show prices after their page runs JavaScript, or refuse plain requests. Browser mode
loads those in a hidden browser, like a normal visit. It uses **Microsoft Edge or Chrome** if installed
(nothing big to download); otherwise it downloads Chromium (about 150 MB) once. Set it up from the
first-run prompt or Sources > manage sources. The app remembers which stores need it and goes straight
to the browser next time. It can't beat serious bot protection (CAPTCHAs / Cloudflare challenges) -
those show as "Bot-check page shown". First searches are slower while stores are being learned.

### When is an OzBargain deal "discounted"?
It's kept if the post lists an RRP/was price, **or** it's at least 5% cheaper than the typical price
at other shops in the same search. If there's nothing to compare against, a deal with 10+ votes is kept.
Everything else is hidden.

## The screens
- **Search tab:** starts on a centred search box (chips for your watchlist items and recent searches).
  Searching opens the results page; the **Deals** logo or **‹ Home** (Ctrl+H) returns to the start.
- **Results:** product cards in a grid with large pictures (greyscale by default; Settings > colour
  pictures). Real discounts are listed first under **DEALS** with the saving in emerald green; everything
  else follows under **REGULAR PRICES**. If nothing is discounted anywhere you'll see **No current deals found**.
- **Watchlist tab:** its own page. Each item shows its best price, target, a price-history chart (click it
  for the full list) and Open / Edit / Remove. **+ Add item**, **Check now** and the auto-check schedule are at
  the top; **Recent deals** are listed underneath.
- A result counts as a deal when there is evidence of a discount: the shop shows a was-price, it's a
  discounted OzBargain post, or its price fell since your last check.

## Daily deals and For you tabs
- **Daily deals**: runs a sweep of big-ticket categories (TVs, laptops, fridges, power tools, e-bikes...) and
  lists items over $150 that are at least 25% below their normal price, biggest dollar saving first, plus
  OzBargain front-page posts that state both prices. It refreshes about once a day when you open the tab, or
  press Refresh. Thresholds are `DAILY_MIN_PRICE` / `DAILY_MIN_PCT` at the top of that section in engine.py.
- **For you**: looks for discounted items *similar* to your Watchlist (same kind of product, any brand).
  Press **Interested** or **Not interested** on a card. Interested adds that kind of product and brand to
  what it searches for; a few "No" answers for a product type or brand stop it appearing. Each "Find more"
  adds up to 12 new suggestions, so it fills in gradually.
- **Shuffle** (Daily deals) re-mixes the list instantly with a random pick weighted towards bigger savings;
  **Refresh** does a new sweep of 22 randomly chosen categories out of ~45, so each refresh finds different things.
- Every card has a **+** button at the top right of its picture that adds the product to your Watchlist.
  **Interested** only teaches *For you* what you like; it never touches the Watchlist.
- *For you* is lenient: it accepts 8%+ off, vetted OzBargain posts, and items clearly cheaper than most shops
  (shown as "below other shops"), and it also looks at neighbouring product types (headphones -> earbuds).
- eBay stays hidden everywhere except when it comes through an OzBargain post.

## Reviews filter
On the results page (and on Daily deals and For you), **reviews:** in the filter bar has four settings: Off, Show ratings, Hide poor reviews, and
Only 4 stars and up. When on, the app opens each product's own page for its star rating (from the page's
structured data) and searches Reddit for what people say about that product, then shows e.g.
`★ 4.6 (212) · Reddit positive` on the card. Products under 3.5 stars, or that Reddit mostly complains
about, are marked "Poor reviews" in red; a poorly reviewed product priced well above typical is marked
"pricey for what it is". Results are cached for 7 days. Reddit often refuses automated lookups; when it does the
app stops asking for a while and uses product-page ratings alone. Hovering the **+** on a picture shows
what it does.

## Smart store selection (keeps big searches fast)
Searching "makita drill" visits the hardware, general and price-comparison sites, not the beauty or
fashion shops. Searching "sony headphones" visits the tech and general stores. If your words don't hint at
a type of product, every store is searched. Prefer the old way? Set `scope` to `all` in the settings table.
Store web addresses are best-effort: any store that can't be reached is paused automatically.

## Speed
- A search stops waiting for slow stores once about 85% have answered (it gives them a few more seconds).
- Pages are parsed with lxml when it is installed (`pip install lxml`), roughly 50x less CPU on big pages
  than the fallback parser. Browser mode runs 3 pages at once with no pictures or styles.
Searches and watchlist checks run every store (and every watchlist item) at once instead of one after
another, with short timeouts, so a slow or dead site can't hold things up:
- Stores that keep failing (blocked, bot-check, needs JavaScript) are **paused** automatically after 3 failures
  in a row, then retried after a day (then 2, 4, 7 days). **Sources > Test all** re-checks everything and
  clears the pauses. Paused stores are labelled in Sources.
- A site that just failed isn't asked again for the other watchlist items in the same check.
- Slow stores are cut off (45 s for a search, 75 s for a whole watchlist check) and the rest still show.
- The same search at the same store within 5 minutes is answered from memory.
- A **loading screen** with a progress bar shows while searching; the Watchlist tab shows live progress
  while checking.

## Look and feel
- A **red dot** appears on the Watchlist tab when a check finds a new deal, and clears when you open the tab.
- The light/dark toggle (sun and moon) is built to the same height as the tabs so the top bar lines up.
- Crisp on high-resolution screens (the app is DPI-aware and scales its layout), with anti-aliased rounded
  buttons, cards, switches and charts, and smooth eased scrolling.
- On Windows the title bar follows the theme (dark/light, and the exact background colour on Windows 11).
  The window remembers its size and position, and has its own icon.
- Model numbers are exact: searching `galaxy watch 6` won't show a Watch 5, `iphone 6` won't show an
  iPhone 16, `ps5` matches "PlayStation 5".

## Searching
- Ranked by relevance. Name a brand (`apple watch`) and only that brand is shown; name none (`watch`)
  and all brands show. `-word` excludes.
- Accessories (bands, straps, cases...) move down, or switch on **hide accessories**.
- **limited-time only** shows deals with an end date; sort by **Ending soon**.
- Reductions show in $ and %: `-$300.00 (43% off)`, or `-$70.00 (12% below)` against other shops.

## Keeping results clean
- **Hidden sites:** eBay is hidden by default - it never appears in a search or alert, whether it comes from
  a store, StaticICE or an OzBargain post. Settings > hidden sites lets you add more (comma-separated words
  from a store's name or address) or clear the list.
- **Too-cheap listings:** anything priced 90% or more below the typical price of the strong matches
  (screen stickers, cables, parts) is dropped as irrelevant. The count is shown above the results.

## Watchlist
- Add items with **+**. With a target price you're alerted at or below it; otherwise on a markdown or
  price drop (5-50%, you choose), or when a discounted OzBargain deal appears.
- Each item shows a price-history chart (click for the full list). OzBargain posts are community deals
  and are kept out of the retailer price history.
- Alerts pop up and can go to ntfy / Discord / Telegram / email (Settings > alerts).

## Sources screen
Sources > manage sources lists every source with a switch, a status and **the reason** when one fails
(blocked, bot-check page, needs JavaScript, address not found). Test all offers to switch dead ones off.

Shortcuts: Ctrl+L focus search, Ctrl+R check watchlist.  Errors are saved to `deals_error.log`.

## Prices
Prices are read from the shop's own price markup first (price / special-price / old-price), and amounts for
gift cards, bonuses, delivery, instalments (Zip, Afterpay) and "save $X" are ignored.

## New in this version
- **Price history for everything**: every price the app sees is remembered. Cards say "Lowest price seen in N
  days", or "Was price unverified - never seen higher" when a shop's "was" price looks inflated. Sale seasons
  (Black Friday, Boxing Day, EOFY) show a reminder to trust that line over the "was" price.
- **Group stores** (filter bar): the same model at several shops becomes one card, "+3 more stores from $X".
  Click that line (or right-click > Compare) to see every store, the price gap, and a note when a shop advertises
  a price-match/beat policy (always check the current terms).
- **Out of stock / refurbished**: flagged on the card. Out-of-stock items sink to the bottom and are never "deals";
  "hide refurbished" (on by default) removes refurbished, ex-demo, open-box and grey-import listings.
- **Best value** sort: well-reviewed and cheap first (turns on review ratings; ratings from the product page,
  ProductReview.com.au when found, and Reddit).
- **Watchlist**: Pause/Resume, ignore certain stores per item, and an alert when something is back in stock.
- **Wrong price?** Right-click a card > report. It's hidden from then on and listed in the exported CSV.
- **Settings**: cashback % (cards show the price after it), run at startup (starts minimised and checks hourly),
  export data (CSV), back up / restore the database. Alert passwords go in your system password store if
  `keyring` is installed.
- **Sharing**: `build_exe.bat` / `build_exe.sh` build a standalone app with PyInstaller (not tested here).
- Help > "fair use and privacy" explains what the app does and its limits.

## Deal score, daily summary, quiet hours
- **Deal score (0-100)** on every deal card: the real discount, whether it's the lowest price we've seen, reviews, price against
  other shops and OzBargain votes. Prices that were never higher than today's score low ("was-price unverified"). Sort by it
  with Sort > Deal score; right-click a card to see why it scored what it did.
- **Settings > alerts**: choose *instant* or *summary* (one message a day at the hour you pick, with your top Daily deals).
  Turn on **quiet hours** and deals found overnight are held and sent as one message when they end.
- **Settings > check all sources** tests every store with a sample search and lists the ones that need a look; for stores that load
  but return nothing, the page is saved to a `snapshots` folder so a changed layout can be fixed.
- **Help > run self-check** feeds saved example store pages (the `fixtures` folder) through the price reader and checks the
  answers. Run `python selftest.py` after any change to the reader.
- Small extras: a tiny price-history line on cards, an **Undo** bar after hiding a listing or removing a watchlist item,
  *Copy deal text* in the right-click menu, and shortcuts `/` or Ctrl+K to jump to search.

## Paste a link, spelling help, colour cues
- **Paste a product link** into the search box. Deals reads the page (brand, model, price), then searches every other store
  for the same product and tells you if anyone is cheaper, with a Watch this product button.
- **Spelling is forgiven.** "samsnug galxy", "play station" or "aple airpods" are fixed automatically; the top of the
  results says what we searched for and offers "Search instead for ..." if we guessed wrong. If a search finds nothing,
  we retry with a looser spelling fix. Model numbers and -excluded words are never changed.
- **Colour cues** always come with a symbol so they work for colour-blind users: green ▼ saves/drops and ✓ good,
  red ▲ price rises and ⚠ poor reviews or inflated "was" prices.

## Pictures and the reviews button
- **Missing pictures**: the app now picks the real product photo on each card (skipping logos, badges and
  placeholder pixels, and choosing the largest size offered), asks image hosts the way a browser would (with the
  shop as referrer), retries, and if a picture still won't load it uses the product page's own main photo.
  Cards with no picture show the store name until one arrives.
- **Reviews button**: the **★** button beside **+** on every picture. Hover it and it checks that product's
  reviews and tells you what it found ("Reviews: ★ 4.6 (212) · Reddit positive" or "No ratings found - click to
  search"). Click it for links to the store page, ProductReview.com.au, Reddit and Google. The star turns green
  or red once reviews are known.
