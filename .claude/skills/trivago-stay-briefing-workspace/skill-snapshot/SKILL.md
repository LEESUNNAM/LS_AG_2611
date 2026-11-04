---
name: trivago-stay-briefing
description: Compare the lowest-priced accommodations with the trivago MCP and deliver a briefing that combines a price ranking, a trip itinerary, and a review summary. Make sure to use this skill whenever the user asks for cheap hotels or the lowest price, wants to compare lodging options, asks when to travel to save money, or wants a trip plan or review summary around a place to stay, even if they never mention trivago. Typical triggers include "최저가 숙소", "호텔 비교", "숙소 추천", "3박 4일 일정", "후기 요약", "cheapest hotel in ...", and "where should I stay in ...".
---

# trivago Stay Briefing

Turn a vague travel request ("cheap hotel in Osaka in December") into a decision-ready briefing: which stays are cheapest, whether other dates are cheaper, what the trip could look like, and what guests say about the top picks.

Users want a recommendation, not a data dump. Run the searches yourself, filter out noise, and present a short ranked comparison with a clear pick.

## Tools

| Tool | Use for |
|---|---|
| `mcp__trivago__trivago-accommodation-radius-search` | Default for any city, neighborhood, or landmark. Needs latitude and longitude, which you resolve yourself. |
| `mcp__trivago__trivago-accommodation-search` | Only for a specific property by name, or a region or country too large for one point. |
| `mcp__trivago__trivago-destination-price-trends` | Monthly average, min, and max nightly price by star rating (3-5 star only). This is a forecast, not live availability. |
| WebSearch (optional) | Fill gaps in itinerary and review content that trivago does not return. |

The trivago tools are deferred. Load their schemas with ToolSearch (`select:mcp__trivago__trivago-accommodation-radius-search,...`) before the first call.

## Workflow

### 1. Collect inputs
Needed: destination, check-in and check-out dates (or a month plus nights), number of adults, and budget. If only some are missing, ask once and briefly. If the user is flexible on dates, skip to the price-trends step first.

Dates must be today or later, and departure must be after arrival. If not, tell the user instead of searching.

Defaults for a Korean-speaking user: `country=KR`, `currency=KRW`, `language=KO_KR`. Use the user's own market, not the destination's. Switch only if they ask. Set `rooms` to 1 unless the group is large.

### 2. Flexible dates: check price trends first
Call `trivago-destination-price-trends` with the destination and a `start_month`/`end_month` window. Report the cheapest and most expensive months for the user's preferred star level and suggest the cheapest window. Say plainly that this is a forecast. Then run the live search on the dates the user picks.

### 3. Search live prices
Call `trivago-accommodation-radius-search` with the resolved coordinates and the user's constraints mapped to filters: `price_range` (state whether it is per night or per stay), `hotel_rating`, `review_rating`, and amenities such as `freeCancellation`, `breakfastIncluded`, `freeWiFi`.

If the user gave no quality bar, add `review_rating.rating75` (7.5+). The cheapest listings are often poorly rated, and a "lowest price" pick the user would hate is not useful. Mention that you applied this floor. If too few results come back, relax it and say so.

For a named property, use `trivago-accommodation-search`.

### 4. Compare
Build a table of the top 5 (fewer if fewer exist), sorted by total price for the stay:

| Rank | Property | Stars | Guest rating | Per night | Total | Key amenities | Cancellation | Link |

- Show both per-night and total price, since users compare against a total budget.
- Use only values the tool returned. If a field is missing, write "n/a". Never estimate prices or ratings.
- Name the cheapest option and the best value (lowest price among well-rated options) separately when they differ.

### 5. Reviews
Summarize guest sentiment for the top 2-3 picks: the rating, 2-3 recurring strengths, and 1-2 recurring weaknesses. Use whatever rating and review data the trivago results contain. If that is thin, run a WebSearch for recent guest reviews of that property, and label the content as coming from the web. Do not invent review quotes. If no review evidence exists, say "no review details available" rather than guessing.

### 6. Itinerary
Write a day-by-day plan matched to the number of nights, with check-in and check-out days treated as partial days. Anchor it to the recommended hotel's area (walkable or short transit hops), and keep it light: 2-3 items per day, a rough pace, and one food suggestion per day. Use WebSearch if you need current opening hours, closures, or seasonal events for the travel dates. Mark anything you could not verify.

### 7. Deliver
Use this structure:

```
## 한눈에 보기
- Recommended pick, price, and one-line reason
- Cheapest option and best-value option, if different

## 최저가 비교
(table)

## 날짜별 가격 동향   (only when dates were flexible)

## 후기 브리핑
(per property)

## 추천 일정
(day by day)

## 참고
- Assumptions made (filters, currency, rating floor), data caveats, booking links
```

Write in the user's language. End with an offer to adjust one thing (dates, budget, area), not a list of options.

## Notes
- Prices come from live metasearch and change quickly. Say that they should be rechecked at booking time.
- Do not book anything; give the links returned by the tool.
- If a search returns nothing, widen one constraint at a time (budget, then rating, then radius or dates), tell the user what changed, and retry.
