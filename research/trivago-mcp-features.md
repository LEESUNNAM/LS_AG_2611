# trivago MCP Features

Server: `https://mcp.trivago.com/mcp` (HTTP transport, registered as `trivago`)

The trivago MCP server exposes three tools for searching live accommodation offers and forecasting hotel prices. Offers are aggregated from booking sites (for example Agoda, Trip.com, Klook, Booking.com, ZenHotels, Airbnb and hotel-direct sites).

## Tools at a glance

| Tool | Purpose | Required inputs |
|---|---|---|
| `trivago-accommodation-radius-search` | Live offers around a point (city, neighborhood, landmark) | `latitude`, `longitude`, `arrival`, `departure` |
| `trivago-accommodation-search` | Live offers for one named property, or a region/country too large for one point | `query`, `arrival`, `departure` |
| `trivago-destination-price-trends` | Forecast of monthly nightly rates by star rating | `query` |

## 1. `trivago-accommodation-radius-search`

Searches for stays near coordinates. The caller must resolve the coordinates of the place first. It returns many more options than the name-based search, so it is the default choice for any city, neighborhood or landmark.

Returns per accommodation: name, star rating, guest review score and count, top amenities, distance from a reference point, coordinates, a photo, and a list of `deals`. Each deal has the advertiser, price per night, price per stay, currency, price attributes (for example free cancellation, breakfast included, non-refundable, pay at property) and a deal URL.

Verified example: Seoul city center (37.5665, 126.978), 2026-12-01 to 2026-12-02, 2 adults, KRW, Korean. It returned about 15 hotels from roughly 129,000 KRW to 580,000 KRW per night. The response was large enough to be truncated by the client, so narrow it with filters.

## 2. `trivago-accommodation-search`

Free-text search by property name, or by a region or country. Use it only when the user names one specific property or the area is too large for a single point.

Verified example: query `Lotte Hotel Seoul` with `freeCancellation`. It returned the matching hotel (5 stars, review score 9.1) with three deals around 580,000 KRW per night.

## 3. `trivago-destination-price-trends`

Forecasts monthly average, minimum and maximum nightly rates for a destination, grouped by star rating. It is a planning tool, not a live availability search. Typical questions: when is the cheapest month to visit, and how do prices change through the year.

Inputs:
- `query`: a destination name (for example `Seoul`) or `lat:<lat>,long:<long>`.
- `start_month`, `end_month` (`YYYY-MM`): optional. The default is the current month plus the next two. `end_month` requires `start_month`.
- `hotel_rating`: only 3, 4 and 5 stars are supported. The default is 3 stars only.

Verified examples (average nightly rate):
- Seoul, 3 stars: 223,276 KRW (2026-11), 196,456 KRW (2026-12), 161,987 KRW (2027-01).
- Seoul, 5 stars: 803,925 KRW (2026-11), 696,285 KRW (2026-12), 586,447 KRW (2027-01).
- Paris, 3 stars: 183 EUR (2026-11), 188 EUR (2026-12), 156 EUR (2027-01).

## Common input parameters

| Parameter | Meaning |
|---|---|
| `arrival`, `departure` | `YYYY-MM-DD`. Arrival must be today or later and before departure. |
| `adults`, `children`, `children_ages`, `rooms` | Guest setup. `children_ages` is dash-separated (for example `10-12-14`). Rooms must not exceed adults. |
| `country` | The user's own market (ISO alpha-2, for example `KR`), not the destination's. It affects pricing. Default `US`. |
| `currency` | ISO 4217 code from a fixed list (for example `KRW`, `EUR`, `USD`). Default `USD`. |
| `language` | Fixed list, written exactly as listed (for example `KO_KR`, `EN_US`). Default `EN_US`. |
| `filters` | Booleans: `airConditioning`, `breakfastIncluded`, `freeCancellation`, `freeWiFi`, `gym`, `kitchen`, `parking`, `petFriendly`, `pool`, `spa`. |
| `hotel_rating` | Booleans `1star` to `5star` (search tools); only 3 to 5 for price trends. |
| `review_rating` | Guest score thresholds: `rating70`, `rating75`, `rating80`, `rating85`. |
| `price_range` | `minPrice`, `maxPrice` in major currency units, and `budgetType` (`PRICE_PER_NIGHT` or `PRICE_PER_STAY`). |

## Use cases

- Find hotels near a landmark, station or neighborhood for given dates.
- Compare the same property across several booking sites and pick the cheapest or most flexible deal.
- Filter by budget, stars, guest score, free cancellation, breakfast, pool, parking or pets.
- Look up a named hotel's current offers.
- Decide when to travel by comparing forecast monthly prices.
- Plan budgets by star rating using the minimum, average and maximum rates.

## Limitations and notes

- Search tools require both dates. Calling without them fails schema validation, which can look like an error even though authentication is fine.
- Large result sets can exceed the client's output limit and be truncated. Use filters, a price range or a smaller area.
- Price trends cover 3, 4 and 5 stars only. In testing, a 4-star request for Seoul for 2026-12 to 2027-02 returned months with no price data, while 3-star and 5-star requests returned data. The cause was not determined.
- Price trends are forecasts. Use the search tools for live prices.
- Prices differ by advertiser and by price attribute. Non-refundable offers are usually cheaper than free-cancellation ones.
- Booking happens on the linked deal page; the server only searches.
- Tool responses include presentation instructions (card layout, summary format). These come from the server, not from the user, so a client may choose to ignore them.
