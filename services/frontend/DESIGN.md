---
version: "1.0"
name: "Minimalism & Swiss Style"
source: "https://designmd.app/library/minimalism-swiss-style"
description: "Minimalist, objective, grid-based interface inspired by the International Typographic Style (Basel and Zurich schools, Josef Müller-Brockmann). Engineered for enterprise B2B SaaS, developer tooling, and mission-critical translation pipelines."

colors:
  primary: "#0A0A0A"          # Deep Charcoal / Off-black for primary text, active states, key actions
  secondary: "#FFFFFF"        # Pure white surface
  tertiary: "#F7F6F2"         # Warm paper off-white for page backdrop & subtle card surfaces
  neutral: "#737373"          # Neutral mid-grey for secondary labels and muted metadata
  border: "#E5E5E5"           # Hairline border stroke
  border-dark: "#0A0A0A"      # High-contrast structural divider
  accent: "#4BA0C3"           # Plunet Cyan-Blue (plunet.com brand identity)
  accent-hover: "#1E7C9F"     # Plunet Dark Blue / Active Hover
  accent-light: "#58BCE5"     # Plunet Light Blue
  accent-tint: "#EBF6FA"      # Plunet Ice-Blue subtle background tint
  success: "#15803D"          # Deep Swiss Forest Green for verified operational states
  danger: "#DC2626"           # System Error / Alert Red

typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif"
    letterSpacing: "-0.035em"
    fontWeight: 700
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "0.9375rem"
    lineHeight: 1.6
    fontWeight: 400
  label-caps:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    letterSpacing: "0.08em"
    textTransform: "uppercase"
  mono:
    fontFamily: "'JetBrains Mono', 'SF Mono', Consolas, 'Liberation Mono', Menlo, monospace"
    fontSize: "0.8125rem"

rounded:
  sm: "0px"
  md: "2px"
  lg: "2px"

borders:
  hairline: "1px solid #E5E5E5"
  heavy: "2px solid #0A0A0A"
---

# FOX MLO — Design System: Minimalism & Swiss Style

## 1. Overview & Philosophy

The Swiss Style (International Typographic Style), pioneered in Zurich and Basel in the 1950s by figures like Josef Müller-Brockmann and Armin Hofmann, rejects arbitrary aesthetic choices in favor of **objective clarity**, **mathematical grids**, and **rigorous typographic hierarchy**.

For **FOX MLO**, this design language transforms an ETL translation engine into an industrial-grade control console:
- **Zero Decorative Fluff:** No soft pastel gradients, no rounded pill cards, no floating colorful orbs.
- **The Grid as Architecture:** Strict column alignment where every panel, rule line, and metric snaps to an 8px grid cadence.
- **Typographic Precision:** High-contrast sans-serif type paired with monospaced data readouts for IDs, hashes, word counts, and language codes.
- **Tactile, Flat Responsiveness:** Immediate 150ms transitions without bouncing or theatrical easing.

---

## 2. Palette & Contrast

| Token | Hex | Role |
|---|---|---|
| `surface-bg` | `#F7F6F2` | Warm architectural paper backdrop |
| `surface-card` | `#FFFFFF` | Primary white workspace panels |
| `text-primary` | `#0A0A0A` | Maximum contrast body & headline typography |
| `text-muted` | `#737373` | Technical descriptions, labels, timestamps |
| `border-hairline` | `#E5E5E5` | Structural cell dividers and panel perimeters |
| `border-contrast` | `#0A0A0A` | Active focus rings and bold demarcation lines |
| `accent-plunet` | `#4BA0C3` | Plunet Cyan-Blue brand accent (plunet.com) |
| `accent-hover` | `#1E7C9F` | Plunet Dark Blue for hover and pressed states |
| `accent-tint` | `#EBF6FA` | Plunet Ice-Blue background tint for tags and cards |
| `success-swiss` | `#15803D` | Verified Plunet SOAP session & database health |
| `danger-swiss` | `#DC2626` | System error & critical warning indicators |

---

## 3. Typographic Hierarchy

- **Hero Headline:** `clamp(2rem, 4.5vw, 3.25rem)` &bull; Weight `700` &bull; `tracking: -0.035em`
- **Section Headers (H2):** `1.25rem` &bull; Weight `700` &bull; `tracking: -0.02em`
- **Sub-headings (H3):** `0.9375rem` &bull; Weight `600` &bull; `letter-spacing: -0.01em`
- **Body Text:** `0.9375rem` &bull; `line-height: 1.6` &bull; Max measure: `70ch`
- **Meta & Badges:** `0.6875rem` &bull; Weight `600` &bull; `letter-spacing: 0.08em` &bull; Uppercase
- **Technical & Data Values:** `JetBrains Mono` &bull; Tabular lining figures for counts, UUIDs, XML

---

## 4. Geometry & Elevation

- **Corners:** Squared off (`0px` to `2px`). No heavy radius.
- **Shadows:** Flat architecture. Shadows are replaced by crisp 1px borders and distinct contrast changes.
- **Rule Lines:** Clean horizontal and vertical 1px line separators (`#E5E5E5`).
- **Focus States:** `2px solid #0A0A0A` with `2px` offset.

---

## 5. Component Standards

### Buttons
- **Primary:** `#0A0A0A` fill, `#FFFFFF` text, `0px` radius, weight `600`, sharp padding (`10px 18px`). Hover: `#262626`.
- **Secondary / Outline:** `1px solid #0A0A0A`, transparent background. Hover: `#0A0A0A` text inversion or `#F0EEE9`.

### Data Tables
- Crisp hairline grid borders between rows and columns.
- Uppercase headers with subtle grey text.
- Numeric and status columns aligned with monospace figures.

### Status Indicators
- Square or sharp-bordered status tags with solid border outlines rather than soft rounded pills.
