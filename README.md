# Multi-Agent AI Research Assistant for Academic Literature Review

A COMP5584 group project exploring how specialized LLM agents can collaborate to produce evidence-grounded literature reviews from locally stored academic papers.

## Project Goal

Given a research question and a local collection of PDF papers, the system will use real model APIs to retrieve evidence, analyze findings, synthesize a review, and verify claims and citations.

## Planned Agents

- **Supervisor / Planner** decomposes the research question, assigns tasks, and coordinates follow-up.
- **Search Agent** retrieves candidate papers and records relevant passages and page numbers.
- **Analysis Agent** compares evidence, methods, findings, and limitations.
- **Writing Agent** drafts the structured review with citations.
- **Verification Agent** checks facts and citations, and routes evidence gaps back to the planner before release.

## Collaboration

Agents will exchange structured task assignments, evidence-backed findings, information requests, and review reports through a shared workspace. Missing evidence or disputed claims will trigger targeted follow-up tasks rather than a fixed one-pass pipeline.

Important claims will link back to specific papers and PDF pages. The final output will use the reviewed draft version and explicitly identify unresolved gaps.

## Scope and Status

- Paper retrieval is limited to a configured local folder; no online paper search is planned for the initial version.
- Cloud model APIs may receive selected paper excerpts; local retrieval does not mean fully offline processing.
- API credentials and paper files must not be committed to this repository.
- The `codex/frontend` branch contains a frontend prototype for the research workspace.

## Frontend Prototype

Folio is a React, TypeScript, and Vite workspace with a centered research prompt and an office showing the five Agents. It streams reports and opens an evidence panel from numbered citations. New research questions use the configured backend by default. The home page test cards and the optional demo mode use local fixtures.

Open **设置 → 后端连接** to test and save the service address. The default is `http://localhost:35549`. The [backend handoff and API contract](docs/backend-api.md) describes the work, request and response formats, and integration checks.

Use **办公室** in the toolbar to toggle the right sidebar alongside the current prompt or report. The sidebar opens when a review starts. Select a desk to see the Agent's assignment and typing animation. Clicking a citation brings evidence into the same space, and closing it returns to the office if it was open.

Projects group conversations under a working folder and support multiple knowledge-base paths. Hover over **知识库** to add a folder directly, or use project settings to type a path. Browsers return the chosen folder name, which Folio saves as a path relative to the working directory. Hover over **对话** and use **+** to focus a blank prompt for that project.

Send follow-ups from the composer below a report. Each follow-up keeps the same conversation and streams a new reply. Expand earlier turns to read their reports and inspect their citations. Type `@` to attach another conversation from the current project. The **…** button on each conversation lets you archive, restore, or delete it. Project settings and completed conversations are saved in the current browser tab.

Run with Node.js 22.12 or later.

```sh
npm ci
npm run dev
```

`npm run build` checks TypeScript and writes the static frontend to `dist/`. `npm run preview` serves that build locally. The web app manifest lets supported browsers install the workspace in a standalone window when served from localhost or HTTPS.

Drag the sidebar divider to resize it, or use the toolbar button to hide and show it. **设置** in the lower-left corner lets you choose Light, Dark, or System appearance. Light is the default, and the browser remembers your choice. [Apple's macOS design guide](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos) · [Split views](https://developer.apple.com/design/human-interface-guidelines/split-views) · [Materials](https://developer.apple.com/design/human-interface-guidelines/materials)

### Manual frontend checks

- Pick **一次核查通过** below the prompt and press Enter. Watch the three parallel desks, the first-response wait, and the streamed report.
- Pick **退回补查** to see verification return to the planner, two desks revise their work, and the report stream after rechecking.
- Pick **长报告与引用**, or open the saved long report under **文献综述研究**. Check the outline jump, citation 10 on page 120, and the sample-page dialog.
- Open **证据不足时的待核查清单** under **引用核查实验** to see an uncited sample. Switch to **空白测试项目** for the empty knowledge library and empty `@` results.
- Open an existing report, choose **提炼要点**, and send the follow-up. Check that the sidebar still shows one conversation for both turns, and expand the first turn to inspect its citations.
- Open a conversation’s **…** menu. Archive and restore it, then try deleting a disposable test conversation. Reload to check that the change persists in the tab.
- In **配置项目**, use **浏览…** to choose a working folder and **添加文件夹** for knowledge paths. Edit or remove a path, then save and check the knowledge library.
- In **空白测试项目**, use the row-end **+** buttons to add a folder and open a blank conversation. The sidebar shows the new conversation after the first message is sent.
