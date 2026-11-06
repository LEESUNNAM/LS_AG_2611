# Browser notes for tistory-post-writer

Practical findings from driving Chrome with claude-in-chrome. Read this when a step behaves unexpectedly.

## Research navigation

- Google News search pages list headlines, but `get_page_text` on the list does not give article URLs. Use `find` or `read_page` (interactive filter) to get each link's ref, then `left_click` the ref. The article usually opens in a NEW tab; call `tabs_context_mcp` for its ID and read it with `get_page_text`.
- Navigating directly to a Google News `./read/...` link sometimes shows an empty page for a moment. Wait 3 seconds, then read; the tab's URL becomes the real article URL.
- `get_page_text` can be cut at 50,000 characters on very long pages. Say in the source list that the page was only partly read if the part you needed was within the limit but the rest was not, or read further with `read_page` on a ref.
- Some publishers show a "temporarily restricted" or bot-check page, or the extension reports "Permission denied for reading page content on this domain". Treat both as blocked: do not retry in a loop, do not try to bypass, drop the source and use another. Do not cite a page you could not read.
- Paywalled or truncated pages (for example Barron's, or Fast Company behind an "expand to continue" prompt) return only a headline and a few paragraphs, and some pages (Motley Fool in one run) return just a title. That is a partial read at best. Do not count it as read, and do not cite facts that were not in the text you saw. If you cite what you did see, label it "(본문 일부만 열람)".
- Some domains are blocked by the extension itself ("This site is blocked."). The tab for such a page may also refuse to close with `tabs_close_mcp`; tell the user which tab to close by hand.
- In one run only 2 of 8 sources opened cleanly. Open more candidates than you need, and say plainly in the post and in the final message when fewer than 5 were read in full.
- Click-through can open a different article than the headline you meant (related-article lists change). Always check the title and URL in the result before using the text.
- When a site reminds you not to reproduce its content verbatim, summarize in your own words and cite.

## Tistory UI

- Logged-in check: the home page header has a "글쓰기" link; the account menu has a "로그아웃" button. Both are hidden when logged out. The logged-out header shows a "시작하기" button that opens a dialog with "카카오계정으로 로그인".
- "글쓰기" opens `https://<blog>.tistory.com/manage/newpost` in a new tab.
- Editor layout (narrow viewport): the toolbar is on top, then a category dropdown, a title field, and the body area. The viewport may be narrower than the editor, so some controls are off-screen; use `find` and `scroll_to` on a ref rather than guessing coordinates.
- Buttons at the bottom: "미리보기", "맞춤법", "임시저장", "완료". The page also autosaves (an "자동 저장 완료 HH:MM:SS" label appears).
- Draft confirmation: after "임시저장" a banner reads "작성 중인 글이 저장되었습니다." and the button shows a count ("임시저장 개수 1개"). Use these as the evidence that the draft saved.
- URLs typed on their own line are turned into link preview cards by the editor (title, description, domain). This is harmless, and it makes the source list look richer, but it takes more vertical space.
- "완료" opens the publish panel with radio buttons "공개", "공개(보호)", "비공개", and a bottom button whose label follows the choice ("비공개 저장" for private). The panel may remember the last visibility, so always read the selected option from a screenshot before confirming.
- After the bottom button, a DKAPTCHA dialog can appear (map image, a fill-in-the-blank word, "답변 제출"). Only the user may solve it.
- After a successful publish the browser goes to `<blog>.tistory.com/manage/posts/`. The list shows title, category, author, date, and a "비공개" label for private posts. A title link's href gives the post URL, e.g. `https://<blog>.tistory.com/4`.

## Typing into the editor

- Click the title field, type the title, click the body area, type the body. The `type` action accepts newlines. Pass the text as normal JSON strings; a malformed batch (for example, a very long body that is cut off or escaped incorrectly) fails with an input validation error before anything is typed, so resend a clean call.
- Screenshots right after typing may show the editor scrolled to the bottom. Scroll up before judging whether the text landed.
