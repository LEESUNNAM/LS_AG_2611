# Notes

## Tools called
1. Read SKILL.md
2. ToolSearch (loaded trivago radius-search, accommodation-search, price-trends, WebSearch)
3. trivago-accommodation-search: query "The Shilla Jeju", 2026-11-20 to 11-22, 2 adults, KR/KRW/KO_KR. Returned the correct property (Seogwipo, 5 star, 9.1, 33.247,126.408). No wrong-property mismatch this time.
4. trivago-accommodation-radius-search at 33.2472,126.408: 4-5 star, review 8.0+, max 579,000 KRW per night. Returned 8 properties (no truncation seen).
5. WebSearch (standard): "제주 신라호텔 투숙 후기 장단점 2026"
6. WebSearch (standard): "그랜드조선 제주 숙박 후기 장단점 객실 조식 소음"
7. WebSearch (standard): "롯데호텔 제주 숙박 후기 장단점 객실 노후 조식"
Price-trends tool not called (dates fixed).

## Problems / judgement calls
- trivago tool output instructs "no table, show each hotel as a card"; this conflicted with the skill's table requirement, so I followed the skill (user-facing format).
- Reviews: web results thin. Shilla and Lotte had no usable review details; only Grand Josun had some. Stated as such, no invented quotes.
- Used lowest deal per property, not the tool's first deal (e.g., Kensington first deal was higher than Booking.com).
- Used 579,000 max price as cap (just below Shilla's lowest 580,201) so only cheaper hotels were returned; Bowhill Pension (32 reviews, 71k) excluded as not comparable.
- Distance from Shilla stated as "within ~0.5km" for Grand Josun based on coordinates (33.2525 vs 33.2472), roughly 0.6km; I wrote approx.
- Itinerary skipped (price comparison request); offered in one line.
- Some city labels from trivago ("제주시") look inconsistent with the Jungmun coordinates; noted.
