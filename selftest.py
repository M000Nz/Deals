"""Self-check for the page readers: feeds saved store-page layouts (fixtures/) through the parser and checks
that titles and prices come out right. Run:  python selftest.py   (also in Deals: Help > run self-check)."""
from pathlib import Path

import engine as E

HERE = next((p for p in (Path(__file__).parent / "fixtures", Path(__file__).parent / "Fixtures") if p.exists()), Path(__file__).parent / "fixtures")
# fixture -> {product keyword: (expected price, expected was-price or None)}
EXPECT = {
    "jsonld_grid.html": {"xm5": (399.0, None), "quietcomfort": (549.0, None)},
    "was_price_cards.html": {"qn90c": (999.0, 1499.0), "oled65c3": (2495.0, None)},
    "savings_noise.html": {"v15": (899.0, 1049.0)},
    "gift_card_badge.html": {"srf7100bb": (2199.0, None)},
}


def run() -> list[str]:
    """Returns a list of problems (empty = all good)."""
    bad = []
    for name, want in EXPECT.items():
        path = HERE / name
        if not path.exists():
            bad.append(f"{name}: fixture file missing")
            continue
        try:
            offers = E._parse_store_page(path.read_text(encoding="utf-8"), "https://example.com.au/search?q=x",
                                         {"name": "Test store", "search_url": "https://example.com.au/search?q={query}"})
        except Exception as e:  # noqa: BLE001
            bad.append(f"{name}: crashed ({e})")
            continue
        for kw, (price, was) in want.items():
            hit = next((o for o in offers if kw in E.norm(o.title)), None)
            if not hit:
                bad.append(f"{name}: '{kw}' not found")
            elif abs(hit.price - price) > 0.01:
                bad.append(f"{name}: '{kw}' price {hit.price} (expected {price})")
            elif was and (not hit.was_price or abs(hit.was_price - was) > 0.01):
                bad.append(f"{name}: '{kw}' was-price {hit.was_price} (expected {was})")
            elif not was and hit.was_price:
                bad.append(f"{name}: '{kw}' invented a was-price {hit.was_price}")
    for text, fixed in (("samsnug galxy", "samsung galaxy"), ("play station 5", "playstation 5")):
        got = E.correct_query(text)[0]
        if got != fixed:
            bad.append(f"spelling: '{text}' became '{got}' (expected '{fixed}')")
    return bad


if __name__ == "__main__":
    problems = run()
    print("\n".join(problems) if problems else "All checks passed.")
    raise SystemExit(1 if problems else 0)
