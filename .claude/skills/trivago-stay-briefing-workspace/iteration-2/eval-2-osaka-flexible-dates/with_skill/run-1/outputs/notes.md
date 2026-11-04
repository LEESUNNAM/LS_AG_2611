# Notes

## Tools called
1. Read SKILL.md
2. ToolSearch (loaded trivago radius-search, accommodation-search, price-trends, WebSearch)
3. trivago-destination-price-trends: query Osaka, 2027-03 to 2027-05, 4star, KR/KRW/KO_KR
4. trivago-accommodation-radius-search (34.6687, 135.5013 Namba), 2027-05-17 to 05-19, 2 adults, 1 room, 4star, rating80, KR/KRW/KO_KR
5. trivago-accommodation-radius-search, same but price_range max 130000 per night (to narrow after truncation)
6. WebSearch (standard): "Smile Hotel Premium Osaka Hommachi guest reviews pros cons"
7. WebSearch (standard): "Hotel Brighton City Osaka Kitahama guest reviews pros cons"
8. WebSearch (standard): "Osaka May 2027 events festivals Osaka Castle Dotonbori opening hours closures"

## Problems
- Both live searches were truncated by the 25k-token output cap. The first cut off after about 15 hotels, the second after City Plaza Osaka. Cheaper hotels may be missing from the table.
- 4-star filter returns serviced apartments mixed with hotels; flagged in briefing.
- The events search found nothing for May 2027 and no opening hours, so the itinerary marks hours as unverified.
- Review searches returned only aggregated summaries, no recent review text. No review search for Keihan Namba Grande or Merbabu Stay.
- Dates (May 17-19, 2027, Mon-Wed) chosen by me to avoid Golden Week; user gave no dates.
- Smile Hommachi is 4 star on trivago but described as 3 star by web sources; noted.
- Itinerary details (specific sights) come from general knowledge, not verified for 2027.
