# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Instructions

- Your name is 이선남 (Lee Sunnam).
- When the user types "클론해줘" ("clone it"), clone the connected Git repository (see the repository link below).
- Write and edit all `.md` files in English, whether creating a new one or modifying an existing one.
- Keep each `.md` file in English, and save a translated `.txt` version of it in a separate, new folder (`translations/`).
- When a `.md` file is modified, update the translated `.txt` file with the same base name as well.
- Whatever task the user requests, first create a todo list and report it to the user, then wait for the user's approval before performing the task. Do not start the work until approval is given.
- When a requested task is finished, upload (commit and push) the result to the connected Git repository.
- Save every output produced with the Playwright MCP (screenshots, snapshots, downloads, logs) in `output/playwright/`, creating the folder if it does not exist. Pass that path explicitly (for example as the screenshot filename) instead of leaving files in the default `.playwright-mcp/` folder.
- Git repository link: https://github.com/LEESUNNAM/LS_AG_2611

## Folder layout

- `output/docx/`, `output/xlsx/`: finished Word and Excel deliverables.
- `output/playwright/`: all outputs produced with the Playwright MCP.
- `output/data/`: the JSON specs the reports are generated from.
- `output/samples/`: sample files written by `scripts/create_docx.py` and `scripts/create_xlsx.py`.
- `research/notes/`: research notes in Markdown (Canva and trivago MCP references).
- `research/reports/`: finished research reports.
- `scripts/`: Python generators; `scripts/archive/` holds retired versions.
- `canva/`: exported Canva designs, grouped by topic.
- `img/`: JPG images copied from the Downloads folder (not committed to Git).
- `translations/`: translated `.txt` versions of the `.md` files.

New skill output lands flat in `output/` (as the skills specify); sort it into the subfolders above afterwards.
