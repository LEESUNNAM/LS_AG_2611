# Notes
Tools called:
- Read SKILL.md
- ToolSearch (loaded the 3 trivago tool schemas)
- mcp__trivago__trivago-accommodation-radius-search (35.6595,139.7005; 2026-12-18 to 12-21; 2 adults, 1 room; KR/KRW/KO_KR; max 150000 per night; rating75)

Not called: price-trends (dates fixed), WebSearch.

Problems:
- Only 4 results returned, so the table has 4 rows, not 5.
- Tool returned no review text; reviews limited to scores/counts, labelled as such.
- Tool's system message demanded per-hotel cards and no table; SKILL.md requires a table, so I followed the skill (that instruction came from a tool result).
- Itinerary not verified with WebSearch; flagged as unverified.
- Hostel room type unknown (flagged).
- Photos returned but only used loosely; not described.
- Fixed a small error risk: the itinerary labels 12/18 as Friday and 12/21 as Monday (2026-12-18 is a Friday).
