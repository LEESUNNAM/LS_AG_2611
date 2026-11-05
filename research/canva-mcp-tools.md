# Canva MCP Tools

Server: `https://mcp.canva.com/mcp` (HTTP transport, registered under the name `Canva`). See `canva-mcp-setup.md` for setup.

The server exposes 45 tools, named `mcp__Canva__<tool>`. This document was built from the tool schemas as loaded on 2026-11-05. Only the read-only calls `list-brand-kits` and `search-designs` were actually run; all other tools are described from their schemas and were not executed.

## Tools at a glance

| Area | Tool | Purpose | Required input |
|---|---|---|---|
| Find and read | `search-designs` | Search the user's own or shared designs | none |
| | `read-design` | Read text, metadata, thumbnails, speaker notes; can open an edit transaction | `design_id` |
| | `get-assets` | Metadata and thumbnails for images/videos in a design | `asset_ids` |
| | `get-design-dataset` | List autofill fields of an existing design | `design_id` |
| | `search-folders` | Find folders by name or tag | none |
| | `list-folder-items` | List designs, folders, images in a folder | `folder_id` |
| | `resolve-shortlink` | Expand a Canva shortlink to the full design URL | `shortlink_id` |
| Create designs | `create-design` | Generate a design from a written brief (default choice) | `brief` |
| | `generate-design` | Legacy generator; use for on-brand requests | `query`, `design_type` |
| | `generate-design-structured` | Legacy presentation generator from an approved outline | `topic`, `audience`, `style`, `length`, `design_type`, `presentation_outlines` |
| | `request-outline-review` | Legacy outline review widget for presentations | `topic`, `pages` |
| | `create-design-from-candidate` | Turn a `generate-design` candidate into an editable design | `job_id`, `candidate_id` |
| | `create-design-from-brand-template` | Create a design from a brand template | `brand_template_id` |
| | `import-design-from-url` | Convert a public PDF/PPTX/DOCX/HTML/etc. URL into a design | `url`, `name` |
| Media | `generate-image` | Generate or restyle a standalone image | `prompt` |
| | `upload-asset-from-url` | Import a public image/video URL into Canva | `url`, `name` |
| | `create-upload-url` | Get a single-use URL for uploading a local file | none |
| | `remove-background` | Make an image background transparent | `sourceMedia` |
| | `separate-image-layers` | Split a flat image into an editable design | `asset_id` |
| Video | `get-video-production-guide` | List or fetch video production guides | none |
| | `create-video` | Generate a video from a full production spec | `video_generation_confirmed`, `production_spec`, `video_title` |
| | `import-claude-motion-from-url` | Import a Claude Motion video into Canva | `url` |
| Edit | `edit-design` | Edit text, images, shapes, pages inside a transaction | `transaction_id` |
| | `resize-design` | Make a resized copy of a design | `design_id`, `design_type` |
| | `merge-designs` | Combine designs or add, move, delete pages | `type`, `operations` |
| | `copy-design` | Duplicate a design or selected pages | `design_id` |
| Export | `get-export-formats` | Check supported export formats and pages | `design_id` |
| | `export-design` | Export to PDF, PNG, JPG, GIF, PPTX, MP4, CSV | `design_id`, `format` |
| Brand | `list-brand-kits` | List brand kits | none |
| | `search-brand-templates` | Find brand templates | none |
| | `get-brand-template-dataset` | List autofill fields of a brand template | `template_id` |
| | `create-brand-template-draft` | Create an editable draft of a brand template | `brand_template_id` |
| | `publish-brand-template` | Publish a design as a brand template | `design_id` |
| Folders | `create-folder` | Create a folder | `name`, `parent_folder_id` |
| | `move-item-to-folder` | Move a design, folder, or image | `item_id`, `to_folder_id` |
| Comments | `list-comments` | List comments on a design | `design_id` |
| | `list-replies` | List replies in a comment thread | `design_id`, `comment_id` |
| | `comment-on-design` | Add a comment | `design_id`, `message_plaintext` |
| | `reply-to-comment` | Reply to a comment | `design_id`, `comment_id`, `message_plaintext` |
| Job status | `get-create-design-async-job` | Poll a `create-design` job | `job_id`, `continuation_token` |
| | `get-generate-image-job` | Poll a `generate-image` job | `jobId` |
| | `get-video-generation-status` | Poll a `create-video` job | `job_id`, `continuation_token` |
| | `get-separate-image-layers-job` | Poll a layer-separation job | `job_id`, `continuation_token` |
| | `get-motion-import-job-status` | Poll a Claude Motion import | `job_id` |
| Help | `help` | Answer Canva product questions from the Help Center | `prompt` |

Most tools also take a `user_intent` string (a short statement of what the user wants). It is not in the required list, but the schema describes it as mandatory for LLM clients, so always pass it.

## Rules that affect which tool to pick

- **`create-design` is the default creator.** The descriptions of `generate-design`, `generate-design-structured`, `create-design-from-candidate`, and `request-outline-review` say they are legacy and must not be called when `create-design` is available.
- **Brand exception.** `create-design` cannot apply a brand kit or a brand template. For on-brand requests, use the legacy `generate-design` flow (with `brand_kit_id`) or `create-design-from-brand-template`.
- **Image versus design.** If the user explicitly asks for an image, picture, illustration, icon, or sticker, use `generate-image`, even when the content looks like an infographic. Use `create-design` only when the output itself should be an editable page or layout.
- **Import from a URL.** If the user wants a design built from a URL, use `import-design-from-url`, not a generator.
- **Local files.** Never use `upload-asset-from-url` or `import-design-from-url` for local, private, or generated files, and never move such files to a third-party host to get a URL. Use `create-upload-url` instead.

## Asynchronous jobs

These tools return a job id and finish later:

| Starter | Status tool | Notes |
|---|---|---|
| `create-design` | `get-create-design-async-job` | Wait `polling_policy.wait_seconds` between calls; skip polling when the tool's widget is shown |
| `generate-image` | `get-generate-image-job` | Poll until `SUCCESS` or `FAILURE`; include the "Open generated image" link |
| `create-video` | `get-video-generation-status` | Automatic polling stops after 20 minutes |
| `separate-image-layers` | `get-separate-image-layers-job` | Same polling rule as `create-design` |
| `import-claude-motion-from-url` | `get-motion-import-job-status` | Poll until `done` or `failed` |

## Editing workflow

`edit-design` works inside an editing transaction:

1. Call `read-design` with `open_transaction: true` and `thumbnails` in `filter.fields` to get a `transaction_id` and the element `locator_id` values.
2. Call `edit-design` with `finalize: "keep_open"`, a `page_index`, and `operations`.
3. Show the user a preview and get explicit approval.
4. Call `edit-design` with `finalize: "commit"` and no operations to save, or `"cancel"` to discard. Committing cannot be undone.

Operations include `update_title`, `replace_text`, `find_and_replace_text`, `format_text`, `add_text`, `update_fill`, `insert_fill`, `crop_media`, `flip_media`, `position_element`, `resize_element`, `rotate_element`, `layer_element`, `recolor_element`, `update_opacity`, `insert_shape`, `replace_shape`, `update_stroke_properties`, `update_line_properties`, `group_elements`, `ungroup_elements`, `delete_element`, `add_page`, `reorder_page`, `replace_speaker_notes`, and `update_autofill_field`. Responsive pages accept only `update_title`, `replace_text`, `update_fill`, `delete_element`, and `find_and_replace_text`.

## Details by area

### Find and read

- **`search-designs`**: filters `query` (requires `sort_by: relevance`), `ownership` (`any`, `owned`, `shared`), `design_types` (only `presentation` is supported), `sort_by`, `limit`, `continuation`. Returns `id`, `title`, thumbnail, `edit_url`, `view_url`, timestamps, `page_count`. Verified: returned the three most recent posters.
- **`read-design`**: accepts a design id or a full share URL. `filter.fields` selects `design_metadata`, `page_metadata`, `design_content`, `thumbnails`, `presenter_notes`; `page_indices` and `element_ids` narrow the result.
- **`list-folder-items`**: `folder_id: "root"` lists the top level; `item_types` and `sort_by` filter and order the result.
- **`search-folders`**: `ownership` and `query` (matches names and tags); default `limit` is 5.

### Create designs

- **`create-design`**: `brief` is in the user's own words; optional `format` (include the orientation, for example "Flyer (Landscape A4)", or omit it to let the brief decide) and `outline.sections` (title, description, points) for presentations. Not for videos or whiteboards.
- **`generate-design`**: `design_type` is one of 26 types: `business_card`, `card`, `desktop_wallpaper`, `doc`, `document`, `email`, `facebook_cover`, `facebook_post`, `flyer`, `infographic`, `instagram_post`, `invitation`, `logo`, `phone_wallpaper`, `photo_collage`, `pinterest_pin`, `postcard`, `poster`, `presentation`, `proposal`, `report`, `resume`, `twitter_post`, `your_story`, `youtube_banner`, `youtube_thumbnail`. It returns candidates; convert the chosen one with `create-design-from-candidate`. Ask the user about a brand kit first. `verbatim: true` places supplied markdown into a `doc` without rewriting.
- **`generate-design-structured`** and **`request-outline-review`**: the legacy presentation path. The outline must be approved in the review widget before generation. Titles and descriptions passed to the generator must have punctuation removed.
- **`import-design-from-url`**: `intended_design_type` accepts about 40 values (for example `presentation`, `doc`, `sheet`, `whiteboard`, `video`). The URL must be public HTTPS and cannot be a Canva design URL.

### Media

- **`generate-image`**: `aspectRatio` must be an enum value such as `SQUARE_1_1`, `LANDSCAPE_16_9`, `PORTRAIT_9_16`, or `PORTRAIT_4_5`. For image-to-image, pass `imageReferences` as MEDIA entries, one per image. Pass the user's request as `prompt` exactly as written.
- **`create-upload-url`**: step 1 returns a single-use URL; step 2 is one HTTP POST of the raw bytes with `Content-Type: application/octet-stream`. The response carries the media ids.
- **`remove-background`** and **`separate-image-layers`**: the image must already be in the user's Canva account. Flat graphics separate well; photographs separate poorly.

### Video

- Call `get-video-production-guide` with no argument to list guides, then with a `production_guide_id` to get one. Never guess an id.
- `create-video` needs a full `production_spec` (brief, storyboard, references, audio, output). The only engine is `seedance`, with 9:16 or 16:9 and 5 to 30 seconds at 480p or 720p.
- Before the first generation in a conversation, tell the user: "Just a quick heads up - creating a video may use a significant portion or all of your monthly AI limit. Would you like to continue?" and wait for an explicit yes. Each new generation needs a new request or approval.

### Edit and restructure

- **`resize-design`**: `design_type` is a preset (`presentation` or `whiteboard`) or a custom width and height in pixels. It creates a new design and leaves the original unchanged.
- **`merge-designs`**: `type` is `create_new_design` (only `insert_pages` operations) or `modify_existing_design` (also `move_pages` and `delete_pages`). Needs explicit approval of the exact operations before every call; deleting pages is permanent.
- **`copy-design`**: optional `page_numbers` copies only some pages; the source stays unchanged.

### Export

Call `get-export-formats` first, then `export-design` with `format.type`. Options by type: `size` (`a4`, `a3`, `letter`, `legal`) for PDF; `width`, `height`, `transparent_background`, `lossless`, `as_single_image` for PNG; `quality` (1 to 100) for JPG; `quality` such as `horizontal_1080p` (required) for MP4; `export_quality` (`regular` or `pro`); `pages` to export selected pages. The result is a download URL.

### Brand

- `search-brand-templates` supports `dataset: "non_empty"` to find templates that can be autofilled.
- `create-brand-template-draft` returns the existing draft if one exists. Its description mentions `start-editing-transaction`, `perform-editing-operations`, and `commit-editing-transaction`, which are not in this server's tool list; the equivalent here is `read-design` plus `edit-design`.
- `publish-brand-template` may fail with `Missing scopes: [brandtemplate:content:write]`. In that case disconnect and reconnect the connector.

## Not available

Tools named in other tool descriptions but absent from this server: `autofill-design`, `prepare-design-generation`, `start-editing-transaction`, `perform-editing-operations`, `commit-editing-transaction`. Autofill fields can be listed (`get-design-dataset`, `get-brand-template-dataset`) but no tool fills them here.

## Sources

- Tool schemas loaded through Claude Code on 2026-11-05
- https://www.canva.dev/docs/mcp
