---
name: AWE TraceGate
description: Calm evidence review for agent workflow candidates
colors:
  action-blue: "#285f9e"
  action-blue-deep: "#174875"
  cool-paper: "#f6f8fa"
  surface: "#ffffff"
  graphite: "#18202b"
  secondary-text: "#5b6675"
  divider: "#d7dde5"
  workspace-divider: "#cbd7e4"
  workspace-field: "#dfeaf7"
  verified-green: "#1e6b43"
  review-amber: "#855f00"
  refused-red: "#9b2c2c"
  disabled-text: "#8b95a3"
typography:
  display:
    fontFamily: "Atkinson Hyperlegible Next, Segoe UI Variable Text, Noto Sans Thai, Leelawadee UI, Segoe UI, Arial, sans-serif"
    fontSize: "clamp(2.25rem, 5vw, 4.6rem)"
    fontWeight: 720
    lineHeight: 0.98
    letterSpacing: "-0.04em"
  body:
    fontFamily: "Atkinson Hyperlegible Next, Segoe UI Variable Text, Noto Sans Thai, Leelawadee UI, Segoe UI, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  intro:
    fontFamily: "Atkinson Hyperlegible Next, Segoe UI Variable Text, Noto Sans Thai, Leelawadee UI, Segoe UI, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  heading:
    fontFamily: "Atkinson Hyperlegible Next, Segoe UI Variable Text, Noto Sans Thai, Leelawadee UI, Segoe UI, Arial, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.3
  title:
    fontFamily: "Atkinson Hyperlegible Next, Segoe UI Variable Text, Noto Sans Thai, Leelawadee UI, Segoe UI, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.4
  compact:
    fontFamily: "Atkinson Hyperlegible Next, Segoe UI Variable Text, Noto Sans Thai, Leelawadee UI, Segoe UI, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  metadata:
    fontFamily: "Atkinson Hyperlegible Next, Segoe UI Variable Text, Noto Sans Thai, Leelawadee UI, Segoe UI, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 650
    lineHeight: 1.4
  label:
    fontFamily: "Atkinson Hyperlegible Next, Segoe UI Variable Text, Noto Sans Thai, Leelawadee UI, Segoe UI, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 650
    lineHeight: 1.4
  mobile-display:
    fontFamily: "Atkinson Hyperlegible Next, Segoe UI Variable Text, Noto Sans Thai, Leelawadee UI, Segoe UI, Arial, sans-serif"
    fontSize: "2.55rem"
    fontWeight: 720
    lineHeight: 0.98
  evidence:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, Liberation Mono, monospace"
    fontSize: "12px"
    fontWeight: 400
rounded:
  control: "8px"
  brand: "9px"
  compact-surface: "10px"
  surface: "14px"
  app-shell: "16px"
  status: "999px"
spacing:
  tight: "8px"
  control: "14px"
  section: "28px"
  page: "32px"
components:
  button-primary:
    backgroundColor: "{colors.action-blue}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.graphite}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
---

# Design System: AWE TraceGate

## Overview

**Creative North Star: "The Calibration Bench"**

The interface behaves like a measured workbench where one candidate moves
through fixed verification stations. Evidence remains visible while status
changes, so a reviewer compares the path rather than trusting a final badge.
The world is quiet, technical, and daylight-readable without imitating a
terminal or filling the screen with dashboard cards.

**Key Characteristics:**

- One horizontal evidence path is the primary organizing structure.
- Inputs, decisions, and artifacts occupy distinct measured regions.
- Status color is rare and always paired with explicit text.
- Digests and structured evidence use monospace; product language does not.

## Surface naming and product boundary

- **AWE TraceGate** is the deterministic evidence gate.
- **TraceGate Review** is the local review UI shipped by this repository.
- An external agent host or workspace may produce evidence, but it is outside
  this product's trusted boundary. Do not use TraceGate Review as a goal
  composer or imply that the verifier can execute work.

## Colors

The restrained daylight palette uses Cool Paper as the page field, Graphite for
primary text, Action Blue for deliberate controls, Verified Green only for
validated outcomes, Review Amber for uncertainty, and Refused Red for invalid
or unsupported evidence. Soft semantic tints are permitted only behind the
matching status text.

**The Evidence Before Color Rule.** A status must remain understandable when
all color is removed.

## Typography

**Display Font:** Atkinson Hyperlegible Next with system fallbacks

**Body Font:** Atkinson Hyperlegible Next with system fallbacks

**Evidence Font:** native monospace with Consolas and Liberation Mono fallbacks

The variable font is self-hosted from the packaged `/assets` route so the local
review surface does not depend on a font CDN. Its
[OFL license](src/awe_tracegate/web/fonts/OFL.txt) travels beside the font
source. The fallback stack includes Segoe UI Variable Text, Noto Sans Thai, and
Leelawadee UI for clear Latin and Thai text. Hierarchy comes from size, weight,
and spacing rather than uppercase labels. The display headline uses a tight,
balanced scale; body copy stays below 68ch. Only hashes, node IDs, code, and
measured machine values use monospace.

## Layout

The desktop TraceGate Review frame uses a 244px pale-blue navigation rail beside
a flexible evidence surface. The five-stage review path is horizontal so
navigation and review progress never become nested sidebars. Below 920px the
rail becomes a compact route bar, while the ordered path remains horizontally
scrollable without page-level overflow. Section rhythm is 28px; control groups
use 8px gaps.

## Elevation & Depth

Surfaces are separated by tone and spacing. The complete workbench receives one
structural shadow (`0 14px 34px rgba(42, 55, 73, 0.1)`); routine evidence rows
remain flat and use dividers.

**The One Lift Rule.** Only the outer workbench is elevated at rest.

## Shapes

Controls use an 8px radius and the outer workbench uses 14px. Status markers and
tags are pill-shaped only when their compact form communicates one state.

## Components

### Buttons

- **Primary:** Action Blue, white text, 8px corners, 44px minimum height.
- **Secondary:** white surface, graphite text, one divider-strong border.
- **Hover / Focus:** one-pixel upward response on hover and a visible blue focus
  outline. Disabled controls remain legible and never respond to hover.

### Status Chips

- Pair semantic tint and text; never rely on color alone.
- Use explicit vocabulary: Compiled, Source inputs revalidated, Pass, Review,
  Block, Approved, Rejected, or Waiting.

### Evidence Trajectory

- Nodes are fixed-width evidence records connected by a one-pixel direction
  line. The container scrolls horizontally without widening the page.
- Each node shows effect and version, tool name, then node ID.

### Inputs

- White background, one strong neutral border, 8px corners, and an explicit
  label. Focus changes the border to Action Blue.

### Human Decision

- Start with no decision selected; approval must always be an explicit action.
- Align Decision and Reviewer identifier controls at the same vertical origin,
  with help and validation text kept inside each field group.
- Label the identity field **Reviewer identifier** and state that it is recorded
  as an assertion, not authenticated by TraceGate.
- On failed submission, show an inline error and move focus to the first invalid
  control.

### Review Path

- All five stations remain visible in order. The numbered marker carries state
  while the adjacent text explains the decision or reason.

### Review Actions

- TraceGate Review uses explicit, labeled buttons and forms for loading files,
  validating evidence, exporting artifacts, and recording a decision.
- Keep primary actions near the evidence they affect. Do not use a fixed bottom
  composer that can cover form controls or validation feedback.
- TraceGate Review never impersonates a model conversation. The user's external
  agent host owns goals, commands, execution permissions, and model credentials.

## Do's and Don'ts

### Do:

- **Do** keep the complete decision sequence visible.
- **Do** label synthetic evidence wherever it could be mistaken for real data.
- **Do** provide keyboard focus, loading, empty, refusal, and error states.
- **Do** preserve the full baseline/candidate metric comparison on mobile.
- **Do** keep approval neutral until the reviewer chooses a decision.

### Don't:

- **Don't** use decorative gradients, glow, glass, or fake terminal chrome.
- **Don't** hide refusal reasons behind a generic error message.
- **Don't** turn every fact into a same-sized card.
- **Don't** imply that a typed reviewer identifier is an authenticated account.
