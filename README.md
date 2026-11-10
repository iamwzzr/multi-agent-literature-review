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

Folio is a React, TypeScript, and Vite prototype. It opens with a centered research prompt. Submit a question to see all five Agents in a shared research office. The simulation covers planning, parallel search, analysis and writing, verification feedback, revision, and a final check. Once the report is ready, click a numbered citation to open its evidence panel. The reports, papers, and excerpts use demo data.

Open **办公室** in the toolbar to view the project office at any time. Select a desk to see the Agent's assignment. Working Agents switch from the idle sprite to a typing animation. The room and sprites load with the office view.

Projects group conversations under a working folder and support multiple knowledge-base paths. Type `@` in the composer to attach an existing conversation from the current project. Project settings and completed demo sessions are saved in the current browser tab. Paths are stored as configuration text for the prototype.

Run with Node.js 22.12 or later.

```sh
npm ci
npm run dev
```

`npm run build` checks TypeScript and writes the static frontend to `dist/`. `npm run preview` serves that build locally. The web app manifest lets supported browsers install the workspace in a standalone window when served from localhost or HTTPS.

Drag the sidebar divider to resize it, or use the toolbar button to hide and show it. **设置** in the lower-left corner lets you choose Light, Dark, or System appearance. Light is the default, and the browser remembers your choice. [Apple's macOS design guide](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos) · [Split views](https://developer.apple.com/design/human-interface-guidelines/split-views) · [Materials](https://developer.apple.com/design/human-interface-guidelines/materials)
