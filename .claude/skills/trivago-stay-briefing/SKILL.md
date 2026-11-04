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

## Scope: match the briefing to the request

The three parts of this skill (price comparison, reviews, itinerary) are not all wanted every time. Decide from the user's words:

- **Full briefing** ("브리핑", "일정까지", "후기랑 일정", or an explicit trip plan request): include all three.
- **Price or recommendation question** ("싼 달", "더 싼 곳 비교", "어떤 호텔이 좋을지"): include the price comparison and a short review summary for the recommended pick. Leave out the itinerary and offer it in one line at the end.

Padding a narrow question with an unrequested itinerary makes the answer longer and the part the user asked for harder to find.

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

For a named property, try `trivago-accommodation-search` first. Name search often matches the wrong property (for example, "제주 신라호텔" returned a hotel in Gyeongju). Check that the returned city matches the user's intent. If it does not, resolve the property's coordinates yourself and run a radius search there, then pick the property out of the results.

Search output is capped, and long result lists get cut off, which can hide cheaper options. Narrow the query up front with `price_range`, `hotel_rating`, and `review_rating` instead of searching wide and reading a truncated list. If a result still looks cut off, say so in the notes.

### 4. Compare
Build a table of the top 5 (fewer if fewer exist), sorted by total price for the stay:

| Rank | Property | Stars | Guest rating | Per night | Total | Key amenities | Cancellation | Link |

- Show both per-night and total price, since users compare against a total budget.
- Use only values the tool returned. If a field is missing, write "n/a". Never estimate prices or ratings.
- Name the cheapest option and the best value (lowest price among well-rated options) separately when they differ.
- When the user named a reference property (for example, "find something cheaper than X"), put it in the table and add a "vs reference" column with the price difference in currency and percent. The comparison is the point of that request, so make it readable at a glance.
- Give one overall recommendation with a one-line reason. Other picks (cheapest, best location) can follow, but the user should never have to choose among four "bests".

### 5. Reviews
trivago returns only a score and a review count, never review text. Those two numbers do not tell the user what staying there is like, so the review section needs real content. For the top 2-3 picks, run a WebSearch for recent guest reviews and summarize 2-3 recurring strengths and 1-2 recurring weaknesses per property (cleanliness, noise, location, room size, staff). Label this content as coming from the web and name the source type (for example, "Google/Tripadvisor-style reviews").

Do not invent review quotes. If the search finds nothing usable for a property, write "no review details found" for that property only, and still give its score and review count. Treat a small review count (under about 200) as a caution when the score is very high.

### 6. Itinerary
Include this section only for a full briefing (see Scope above). If the user asked only for prices, a comparison, or a hotel recommendation, skip it and offer it in one line at the end.

Write a day-by-day plan matched to the number of nights, with check-in and check-out days treated as partial days. Anchor it to the recommended hotel's area (walkable or short transit hops), and keep it light: 2-3 items per day, a rough pace, and one food suggestion per day. Run a WebSearch to confirm current opening hours, closures, and seasonal events for the travel dates (winter illuminations, festivals, holiday closures), because a plan with a closed attraction is worse than none. Mark anything you could not verify.

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
