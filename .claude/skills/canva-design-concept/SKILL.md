---
name: canva-design-concept
description: Turn a topic into at least three design concepts, wait for the user to approve one, then build the chosen deliverable (poster, presentation, social post, and so on) in Canva with the Canva MCP, share a draft link, and on approval export it as PNG, save it locally, and file it in a Canva folder named after the topic. Make sure to use this skill whenever the user gives a topic and wants a Canva design, poster, slide deck, card, social post, or visual concept made, or asks for design ideas for a subject, even if they never say "skill" or name every step. Typical triggers include "캔바로 포스터 만들어줘", "주제로 디자인 컨셉 잡아줘", "canva design about ...", "make a poster on ...", and "디자인 컨셉 3가지".
---

# Canva Design Concept

Take a topic from a vague idea to a finished, filed Canva design in a fixed sequence with two approval gates: the user approves a concept before anything is built, and approves the draft before anything is saved.

The Canva tools create real designs and folders in the user's account. That is why the gates exist. Never skip one, even when the request sounds complete ("make me a poster about X") — the concept still has to be approved first.

## Tools

The Canva tools are deferred. Load their schemas with ToolSearch before the first call, and load everything you will need in one call, for example:

`select:mcp__Canva__create-design,mcp__Canva__get-create-design-async-job,mcp__Canva__read-design,mcp__Canva__edit-design,mcp__Canva__search-folders,mcp__Canva__create-folder,mcp__Canva__get-export-formats,mcp__Canva__export-design,mcp__Canva__move-item-to-folder`

| Step | Tool |
|---|---|
| Create a draft | `create-design`, then `get-create-design-async-job` |
| Check or revise the draft | `read-design`, `edit-design` |
| Find or create the folder | `search-folders`, `create-folder` |
| Export | `get-export-formats`, `export-design` |
| File in the Canva account | `move-item-to-folder` |
| Standalone image only | `generate-image` (use instead of `create-design` when the user asks for an image, illustration, or icon rather than a designed page) |

Always pass `user_intent` on Canva calls. Do not use the legacy generators (`generate-design`, `generate-design-structured`, `request-outline-review`) unless the user wants their own brand kit or brand template applied; see `research/canva-mcp-tools.md` for the full tool reference.

## Workflow

### 1. Propose concepts (no Canva calls)

From the topic, propose **at least three** distinct concepts. Make them genuinely different directions, not three palettes of the same layout. For each concept give:

- a name and a one-line summary
- mood
- colors, as hex values
- font direction
- layout approach
- what it suits best

Show them side by side in one table, name the one you would pick and why in one sentence, and ask which to use. Then stop. Do not call any Canva tool in this step, and do not build anything until the user approves a concept. If the user asks for changes, revise and present again.

### 2. Ask what to make

Once a concept is approved, ask which deliverable the user wants if they have not said: poster, presentation, Instagram post, document, flyer, and so on. If they already named it with the approval ("B, 포스터로"), do not ask again.

Also settle anything that changes the result: how many pages or slides for a presentation, and the exact text if the user has specific wording. Ask once, briefly.

### 3. Build the draft

Write the `create-design` brief in the user's language. The approved concept must be spelled out in it, because the tool does not see the earlier conversation:

- the topic and purpose
- the concept's mood, hex colors, font direction, and layout approach
- the exact wording for the title, subtitle, sections, and closing line (draft it yourself from the topic if the user gave none)
- "do not include unverified numbers, product names, or logos"

Set `format` with the orientation, for example `Poster (Portrait)`. For a presentation, pass `outline.sections` instead of leaving the structure to chance.

`create-design` is asynchronous. Wait the number of seconds in `polling_policy.wait_seconds` (first 15 s, then about 10 s) before each `get-create-design-async-job` call; polling earlier returns the same answer. Use a short PowerShell `Start-Sleep` for the wait, because the Bash tool blocks foreground sleeps.

The generator tends to add text you did not ask for (extra taglines, repeated subtitles, a sample checklist on the cover). Put "use only this wording and add no other text" in the brief to limit it, and still expect some extras.

Before sharing, call `read-design` with `design_metadata` and `design_content` and compare the text to what you asked for. List any extra or reordered text for the user instead of presenting the draft as exact. A line break can make a title read without its space in `design_content` (for example "생산성습관"), so do not report that as a typo until you have seen the exported image. Then give the user:

- the edit link and the view link
- the title and page count
- what you verified (the text) and what you did not (layout and color, which you cannot see before export)

The draft is saved in the user's Canva account automatically. Say so. Ask whether to revise or save.

### 4. Revise if asked

For changes, open an editing transaction with `read-design` (`open_transaction: true`, include `thumbnails`), apply `edit-design` operations with `finalize: "keep_open"`, show the user the result, and only `commit` after they approve. A commit cannot be undone.

### 5. Final save (only after the user approves)

Treat "저장해줘", "승인", "이대로 좋아", or similar as the approval. Then:

1. `search-folders` for a folder named `canva`. Create it with `create-folder` (parent `root`) only if it does not exist.
2. `create-folder` with the **topic as the folder name**, inside `canva`.
3. `get-export-formats` for the design, confirm `png` is listed, then `export-design` with `format: {"type": "png"}`. If PNG is not supported for this design, tell the user and offer the closest format instead of silently changing it.
4. Download each returned URL into the local folder `canva/<topic>/` with `curl -sL -o`. The URLs are signed and expire, so download right away and quote the URL. A multi-page design returns one URL per page: save them as `<name>-1.png`, `<name>-2.png`, and so on.
5. Check each file is really a PNG (`file <path>`) and view it. Report anything that looks wrong.
6. `move-item-to-folder` to file the design in the Canva `canva/<topic>` folder.

Use a file name based on the topic and deliverable, for example `AI-도구-포스터.png`. Replace characters that are invalid in Windows paths (`\ / : * ? " < > |`) in the topic and file names.

### 6. Report

Finish with:

- the local PNG path, with pixel size
- the Canva folder link
- the design link

If the repository's CLAUDE.md asks for it, commit and push the saved files.

## Rules that are easy to get wrong

- **Two gates.** Concept approval before step 3, save approval before step 5. A user's enthusiasm about a draft is not save approval unless they say to save.
- **Do not guess the deliverable.** If it is unclear after approval, ask.
- **Say what you did not check.** You can read the text but not see the layout until the PNG exists; say so when sharing the draft link.
- **Do not create duplicates.** Look for the `canva` folder before creating one, and do not create a second draft unless the user asks for a new one.
- **Video is out of scope.** `create-video` uses the user's monthly AI limit and needs its own explicit confirmation; offer it separately instead of folding it into this flow.

## Verified behavior

Two test runs, both through the full flow.

**Poster, topic "AI 도구"**
- Three concepts were presented first; the user approved one and chose a poster.
- `create-design` with a Korean brief that included hex colors and exact wording produced a one-page poster whose text matched the brief; the generator added line icons on its own.
- The job took about 25 seconds (a 15 s wait, then a 10 s wait).
- `export-design` as PNG returned one signed URL; the file was 2304 x 3456.

**Presentation, topic "생산성 습관", 3 slides**
- `create-design` with `format: "Presentation"` and three `outline.sections` produced a 3-page deck in the approved concept. All three slides kept the same colors and notebook style.
- The job took about 70 seconds and needed four status polls (15 s, then 10 s each).
- The text matched the outline, but the generator added extra text: tagline lines on slide 1, a repeated subtitle on slides 2 and 3, a heading on the checklist, and a different checklist order. These were reported to the user before saving.
- `export-design` as PNG returned three signed URLs, one per page. Each file was a valid 1920 x 1080 PNG and was saved as `<name>-1.png` to `<name>-3.png`.

**Both runs**
- `get-export-formats` listed `pdf`, `jpg`, `png`, `pptx`, `gif`, `mp4`.
- The account already had a `canva` folder, so only the topic subfolder was created each time.
- Not yet verified: PNG export for docs, and revising a draft with `edit-design`.
