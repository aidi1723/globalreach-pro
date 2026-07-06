# GlobalReach PRO UI Design

## Design Intent

- Product archetype: desktop B2B outreach operations workbench.
- Primary use cases: importing lead lists, checking send readiness, controlling SMTP sending, reviewing task outcomes.
- Overall mood: calm, dense, reliable, and operational.
- Keywords: console, governed sending, reviewable state, compact workflow, controlled action.
- Non-goals: marketing-page drama, decorative illustration, playful animation, broad navigation redesign.
- Best-fit screens: workbench, template center, preflight and sending, SMTP console, license status.

## Color System

- Background: `#07111F`
- Background alt: `#08111E`
- Surface: `#0C1A2B`
- Surface elevated: `#10233A`
- Primary text: `#EAF2FF`
- Secondary text: `#8BA2BF`
- Accent: `#2563EB`
- Accent contrast: `#FFFFFF`
- Border: `#1C3552`
- Success: `#16A34A`
- Warning: `#B45309`
- Danger: `#8A3B3B`

Use accent sparingly for active navigation and primary commands. Large surfaces stay quiet; warning and danger colors are reserved for send-risk decisions and terminal actions.

## Typography

- Sans family: Arial for current CustomTkinter compatibility.
- Display family: Arial bold.
- Mono family: Menlo for logs, reports, generated content, and machine-readable status.
- Display style: compact product titles, never oversized.
- Heading style: 13-16 px, bold, direct.
- Body style: 11-13 px, high contrast on dark surfaces.
- Label style: short Chinese labels with concise helper text.
- Tracking and casing rules: no negative tracking, no all-caps labels unless a platform convention requires it.

## Layout and Spacing

- Max content width: use available desktop width through existing tab content; do not add narrow marketing containers.
- Grid or column pattern: two-column grids for related controls, full-width bands for task status and reports.
- Section spacing: 8-12 px between related controls, 10-15 px between panels.
- Component spacing: compact dashboard density with stable button widths.
- Preferred density: operational and scan-friendly, not roomy.
- Mobile behavior: not a priority for this desktop app; layouts should still avoid text overflow in narrower windows.

## Shape and Surface

- Corner radius: 8 px for panels and buttons where CustomTkinter allows it; avoid larger decorative rounding.
- Border style: 1 px border using the shared border color.
- Shadow style: none; rely on borders and surface contrast.
- Blur or glass usage: none.
- Texture, grain, or gradient usage: none.

Use elevation only to group workflow sections. Do not nest decorative cards inside cards.

## Components

### Buttons

- Default button: muted surface color, compact height, clear command label.
- Primary button: accent or success color for the next safe action.
- Secondary button: neutral blue-gray for refresh, resume, and non-destructive utilities.
- Destructive button: danger color only for stop/delete actions.
- Hover and active feel: subtle built-in CustomTkinter hover, no animation flourish.

### Inputs

- Input shell: dark surface with clear border and stable width.
- Focus treatment: preserve CustomTkinter focus visibility.
- Placeholder tone: muted text.
- Error state: messagebox or status panel copy plus warning/danger color when shown inline.

### Cards and Panels

- Card background: `Surface` or `Surface elevated`.
- Border and shadow: border only.
- Internal padding: 10-14 px.
- Title and meta styling: bold title, muted helper text below when needed.

### Navigation

- Header or sidebar style: persistent left console navigation.
- Active state: accent-filled nav control.
- Divider usage: avoid extra dividers; use panel spacing and borders.

### Tables, Lists, and Data

- Row density: compact.
- Header treatment: bold section label plus muted helper text.
- Selection style: obvious, not purely color-only when possible.
- Empty state tone: brief, operational, and tells the next action.

## Motion

- Transition speed: use platform defaults.
- Easing feel: restrained.
- Reveal patterns: none beyond existing tab switches.
- Hover energy: low.
- Loading tone: textual status updates.

## Content Tone

- Sentence case or title case: Chinese operational labels; English technical values remain literal.
- Label tone: terse and specific.
- Empty state tone: say what is missing and what to do next.
- Error tone: direct cause plus recovery action.
- CTA tone: command-oriented.

## Implementation Notes

- Preferred token layer: shared constants and helper builders in `app/ui/builders.py`.
- CSS variable naming: not applicable.
- Tailwind or theme mapping: not applicable.
- Things to avoid: scattered raw colors, hero styling, decorative gradients, oversized cards, page-level behavior changes without tests.

## Do / Do Not

- Do: make send readiness and task state visible before the operator acts.
- Do: keep panels compact and easy to scan.
- Do: reuse helper builders and semantic colors.
- Do not: redesign the product information architecture in a visual polish pass.
- Do not: hide risky send controls behind ambiguous labels.
