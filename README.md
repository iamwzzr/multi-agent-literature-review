# Multi-Agent AI Research Assistant for Academic Literature Review

A COMP5584 group project exploring how specialized LLM agents can collaborate to produce evidence-grounded literature reviews from locally stored academic papers.

## Project Goal

Given a research question and a local collection of PDF papers, the system will use real model APIs to retrieve evidence, analyze findings, synthesize a review, and verify claims and citations.

## Planned Agents

- **Coordinator:** Decomposes the research question, assigns tasks, and manages follow-up work.
- **Researchers:** Investigate different subquestions through local paper retrieval, reading, and analysis.
- **Synthesizer:** Combines research findings into a structured review and requests missing evidence.
- **Reviewer:** Checks claims against original passages and reports issues for revision.

## Collaboration

Agents will exchange structured task assignments, evidence-backed findings, information requests, and review reports through a shared workspace. Missing evidence or disputed claims will trigger targeted follow-up tasks rather than a fixed one-pass pipeline.

Important claims will link back to specific papers and PDF pages. The final output will use the reviewed draft version and explicitly identify unresolved gaps.

## Scope and Status

- Paper retrieval is limited to a configured local folder; no online paper search is planned for the initial version.
- Cloud model APIs may receive selected paper excerpts; local retrieval does not mean fully offline processing.
- API credentials and paper files must not be committed to this repository.
- The `codex/frontend` branch contains a frontend prototype for the research workspace.

## Frontend Prototype

Folio is a React, TypeScript, and Vite prototype. It opens with an example review. Use **新建综述** to start a demo session, or click a numbered citation to inspect its excerpt and sample page. The papers and excerpts are fictional. Demo sessions are kept in memory for the current tab.

Run with Node.js 22.12 or later.

```sh
npm ci
npm run dev
```

`npm run build` checks TypeScript and writes the static frontend to `dist/`. `npm run preview` serves that build locally. The web app manifest lets supported browsers install the workspace in a standalone window when served from localhost or HTTPS.

The interface uses system fonts, a collapsible sidebar, and a trailing evidence inspector. The review text uses an opaque reading surface and the controls follow the system light or dark preference. [Apple's macOS design guide](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos) · [Split views](https://developer.apple.com/design/human-interface-guidelines/split-views) · [Materials](https://developer.apple.com/design/human-interface-guidelines/materials)
