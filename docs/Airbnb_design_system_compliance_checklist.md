# Airbnb Design System Compliance Checklist

Mapped to [`airbnb_official_website_design_system_audit.md`](airbnb_official_website_design_system_audit.md).

**Total items: 227** · **Checked: 165**

Legend: `[x]` pass · `[ ]` pending · **auto** = verify script · **manual** = human QA · **visual** = browser check

## Typography (§1)

- [x] **DS-01-001** (auto) Figtree loaded via next/font as Cereal-compatible face
- [x] **DS-01-002** (auto) Font stack documents Airbnb Cereal VF + Circular + system fallbacks
- [x] **DS-01-003** (auto) Body uses --font-text; display uses --font-display
- [x] **DS-01-004** (auto) Weights 400/500/600/700 tokenized
- [x] **DS-01-005** (auto) Type scale includes 14/16/18/22/26/32 and display 40+
- [x] **DS-01-006** (auto) Body copy .text-body at 16px / ~20–24 line-height
- [ ] **DS-01-007** (visual) Titles use .text-title / .text-headline semibold
- [ ] **DS-01-008** (visual) Heroes use .text-display
- [x] **DS-01-009** (auto) Captions .text-caption; footnotes .text-footnote 12px
- [x] **DS-01-010** (auto) Display leading tight (~1.06); tracking tight
- [x] **DS-01-011** (auto) Prices use tabular-nums
- [ ] **DS-01-012** (manual) No decorative monospace in UI chrome

## Color (§2)

- [x] **DS-02-001** (auto) Rausch #ff385c primary brand token
- [x] **DS-02-002** (auto) Product Rausch #e00b41 strong action
- [x] **DS-02-003** (auto) --color-action maps to Rausch (not Apple blue)
- [x] **DS-02-004** (auto) Babu #00a699 and Arches #fc642d accent tokens
- [x] **DS-02-005** (auto) Hof #222222 marketplace neutral
- [x] **DS-02-006** (auto) Marketplace gray scale 50–600
- [x] **DS-02-007** (auto) Primary buttons Rausch gradient white text
- [x] **DS-02-008** (auto) Secondary buttons neutral border and card bg
- [x] **DS-02-009** (auto) No --color-action-blue leftover
- [x] **DS-02-010** (auto) No glass-panel or btn-glass classes
- [x] **DS-02-011** (auto) Muted text uses muted-foreground semantic
- [ ] **DS-02-012** (visual) Selected states use action/Rausch
- [ ] **DS-02-013** (visual) Disabled controls reduced opacity
- [x] **DS-02-014** (auto) Scrim overlays neutral black not slate

## Layout (§3)

- [x] **DS-03-001** (auto) container-marketplace max 1280px
- [ ] **DS-03-002** (manual) Homepage modular discovery stack wired
- [x] **DS-03-003** (auto) Global nav in AppShell
- [ ] **DS-03-004** (manual) Market pulse ribbon band
- [ ] **DS-03-005** (visual) Hero headline + subcopy band
- [ ] **DS-03-006** (visual) Home modules horizontal scroll rows
- [ ] **DS-03-007** (manual) Ending soon tile grid
- [x] **DS-03-008** (auto) Footer directory columns
- [ ] **DS-03-009** (visual) Detail page local breadcrumb nav
- [ ] **DS-03-010** (visual) Section bands use gray-100 / muted surfaces
- [x] **DS-03-011** (auto) No page-bg grid patterns
- [ ] **DS-03-012** (visual) Sticky discovery toolbar on scroll
- [ ] **DS-03-013** (visual) List + filter drawer two-column desktop
- [ ] **DS-03-014** (manual) Max-width prose on legal copy

## Spacing (§4)

- [x] **DS-04-001** (auto) Spacing tokens --space-2 through --space-96 defined
- [ ] **DS-04-002** (visual) Card padding uses space-16/24
- [x] **DS-04-003** (auto) Section vertical rhythm space-56/96
- [x] **DS-04-004** (auto) Nav height marketplace token (not Apple 44)
- [x] **DS-04-005** (auto) Page padding 24px / 40px marketplace rhythm
- [ ] **DS-04-006** (visual) Grid gap consistent space-8/16
- [ ] **DS-04-007** (manual) Modal padding space-24
- [ ] **DS-04-008** (visual) Sticky bar padding space-16

## Imagery (§5)

- [x] **DS-05-001** (auto) Auction photos lazy-loaded
- [ ] **DS-05-002** (manual) Alt text on informative images
- [ ] **DS-05-003** (visual) Aspect ratio preserved in listing cards
- [ ] **DS-05-004** (manual) No heavy decorative imagery in chrome
- [ ] **DS-05-005** (visual) Placeholder skeletons neutral gray
- [ ] **DS-05-006** (manual) Map tiles deferred load
- [ ] **DS-05-007** (visual) Gallery overlays readable contrast

## Components (§6)

- [x] **DS-06-001** (auto) btn-primary pill radius + Rausch gradient
- [x] **DS-06-002** (auto) btn-secondary pill radius neutral
- [x] **DS-06-003** (auto) surface-elevated cards with hover elevation
- [ ] **DS-06-004** (manual) Chip primitive + active filter chips
- [x] **DS-06-005** (auto) Modal focus trap and scrim
- [ ] **DS-06-006** (manual) Accordion disclosure pattern
- [x] **DS-06-007** (auto) Filter drawer + bottom sheet
- [ ] **DS-06-008** (manual) Command palette dialog
- [ ] **DS-06-009** (manual) Pagination bar
- [x] **DS-06-010** (auto) Auction card buyer-critical fields
- [ ] **DS-06-011** (manual) Auction table view mode
- [x] **DS-06-012** (auto) Input/Select primitives marketplace styled

## Motion (§7)

- [x] **DS-07-001** (auto) Duration tokens instant through ribbon
- [x] **DS-07-002** (auto) --ease-standard and --ease-marketplace-nav
- [x] **DS-07-003** (auto) Hover transitions use duration-hover
- [x] **DS-07-004** (auto) prefers-reduced-motion respected globally
- [x] **DS-07-005** (auto) No price-pulse or shimmer border effects
- [ ] **DS-07-006** (visual) Modal enter subtle

## Iconography (§8)

- [ ] **DS-08-001** (manual) Lucide icons stroke ~1.5 default
- [ ] **DS-08-002** (visual) Icons paired with text labels in nav
- [ ] **DS-08-003** (manual) Star for watchlist semantic
- [ ] **DS-08-004** (manual) ExternalLink for outbound bid

## Surfaces (§9)

- [x] **DS-09-001** (auto) surface-base page background
- [x] **DS-09-002** (auto) surface-elevated elevated cards
- [x] **DS-09-003** (auto) surface-translucent-nav header
- [x] **DS-09-004** (auto) Radius tokens xs through pill
- [x] **DS-09-005** (auto) --shadow-subtle / --shadow-hover / --shadow-modal
- [x] **DS-09-006** (auto) Tailwind listing-card shadow
- [x] **DS-09-007** (auto) No glass-panel surfaces

## Content (§10)

- [x] **DS-10-001** (auto) Marketplace buyer tone (no terminal metaphors)
- [ ] **DS-10-002** (manual) CTA View listing / Bid on source outbound
- [ ] **DS-10-003** (visual) Short hero subheads
- [x] **DS-10-004** (auto) Disclaimer footnotes present
- [ ] **DS-10-005** (manual) Source capitalization MSTC GeM
- [ ] **DS-10-006** (manual) SEO copy human readable

## Navigation (§11)

- [x] **DS-11-001** (auto) Global header with marketplace container
- [ ] **DS-11-002** (manual) Theme toggle in nav
- [ ] **DS-11-003** (visual) Mobile drawer
- [x] **DS-11-004** (auto) Footer uses marketplace gray
- [ ] **DS-11-005** (visual) Detail breadcrumb
- [ ] **DS-11-006** (manual) Watchlist / Map / Pricing nav links
- [x] **DS-11-007** (auto) Pricing page content inside AppShell

## Interaction (§12)

- [x] **DS-12-001** (auto) focus-ring / focus-visible Rausch halo
- [x] **DS-12-002** (auto) Hover elevation on surface-elevated
- [ ] **DS-12-003** (visual) Disabled opacity on buttons
- [x] **DS-12-004** (auto) Touch targets min 44px primary CTAs
- [x] **DS-12-005** (auto) Link hover underline on link-action

## Forms (§13)

- [x] **DS-13-001** (auto) Input marketplace border and height
- [ ] **DS-13-002** (manual) Labels on filter fields
- [ ] **DS-13-003** (visual) Placeholder muted-foreground
- [ ] **DS-13-004** (manual) Search aria-label present
- [ ] **DS-13-005** (manual) Form error messages visible

## Responsive (§14)

- [x] **DS-14-001** (auto) Breakpoints sm 744 / md 950 / lg 1128 / xl 1440 (not Apple)
- [x] **DS-14-002** (auto) Mobile filter bottom sheet
- [ ] **DS-14-003** (visual) Desktop filter sidebar
- [ ] **DS-14-004** (visual) Cards single column mobile
- [ ] **DS-14-005** (visual) Nav hamburger mobile
- [ ] **DS-14-006** (manual) Safe area bottom sticky bars

## Accessibility (§15)

- [ ] **DS-15-001** (manual) main landmark on pages
- [x] **DS-15-002** (auto) Modal aria-modal true
- [x] **DS-15-003** (auto) Reduced motion global rule
- [x] **DS-15-004** (auto) Focus visible not outline-none alone
- [ ] **DS-15-005** (manual) Decorative icons aria-hidden
- [ ] **DS-15-006** (visual) Color contrast Rausch on white CTAs

## SEO (§16)

- [ ] **DS-16-001** (manual) Metadata on routes
- [ ] **DS-16-002** (visual) Single h1 per page
- [ ] **DS-16-003** (manual) Sitemap static export
- [ ] **DS-16-004** (manual) Internal hub links
- [ ] **DS-16-005** (manual) Canonical / OG patterns

## Performance (§17)

- [ ] **DS-17-001** (manual) Static export out/
- [x] **DS-17-002** (auto) Figtree subset via next/font (no pirated Cereal)
- [x] **DS-17-003** (auto) Image lazy loading
- [x] **DS-17-004** (auto) prefers-reduced-motion kills animations

## Design Tokens (§18)

- [x] **DS-18-001** (auto) All color tokens in globals.css
- [x] **DS-18-002** (auto) Type weight / leading / tracking tokens
- [x] **DS-18-003** (auto) Full spacing + layout container tokens
- [x] **DS-18-004** (auto) Radius + shadow + motion + z-index tokens
- [x] **DS-18-005** (auto) Tailwind darkMode data-theme
- [x] **DS-18-006** (auto) Tailwind action + marketplace-gray + marketplace easing
- [x] **DS-18-007** (auto) HSL shadcn mapped from Rausch primary

## Cross-system

- [x] **DS-19-001** (auto) verify-airbnb-design.mjs passes
- [x] **DS-19-002** (auto) No Apple verifier / container-apple / ease-apple
- [x] **DS-19-003** (auto) No terminal UI chrome copy
- [x] **DS-19-004** (auto) Audit SoT present in docs/
- [ ] **DS-19-005** (manual) Production scrapauctionindia.com /auctions

## Per-route matrix (§3 + §11)

### Route `/`
- [x] **DS-RT-01-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-01-02** (visual) text-display / text-body typography
- [x] **DS-RT-01-03** (visual) SiteFooter or route-appropriate footer

### Route `/[source]/[id]`
- [x] **DS-RT-02-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-02-02** (visual) text-display / text-body typography
- [x] **DS-RT-02-03** (visual) SiteFooter or route-appropriate footer

### Route `/scrap`
- [x] **DS-RT-03-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-03-02** (visual) text-display / text-body typography
- [x] **DS-RT-03-03** (visual) SiteFooter or route-appropriate footer

### Route `/metal-scrap`
- [x] **DS-RT-04-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-04-02** (visual) text-display / text-body typography
- [x] **DS-RT-04-03** (visual) SiteFooter or route-appropriate footer

### Route `/aluminium-scrap`
- [x] **DS-RT-05-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-05-02** (visual) text-display / text-body typography
- [x] **DS-RT-05-03** (visual) SiteFooter or route-appropriate footer

### Route `/coal-auctions`
- [x] **DS-RT-06-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-06-02** (visual) text-display / text-body typography
- [x] **DS-RT-06-03** (visual) SiteFooter or route-appropriate footer

### Route `/timber-auctions`
- [x] **DS-RT-07-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-07-02** (visual) text-display / text-body typography
- [x] **DS-RT-07-03** (visual) SiteFooter or route-appropriate footer

### Route `/vehicle-auctions`
- [x] **DS-RT-08-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-08-02** (visual) text-display / text-body typography
- [x] **DS-RT-08-03** (visual) SiteFooter or route-appropriate footer

### Route `/mstc-auctions`
- [x] **DS-RT-09-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-09-02** (visual) text-display / text-body typography
- [x] **DS-RT-09-03** (visual) SiteFooter or route-appropriate footer

### Route `/gem-forward-auctions`
- [x] **DS-RT-10-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-10-02** (visual) text-display / text-body typography
- [x] **DS-RT-10-03** (visual) SiteFooter or route-appropriate footer

### Route `/eauction-gov-in`
- [x] **DS-RT-11-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-11-02** (visual) text-display / text-body typography
- [x] **DS-RT-11-03** (visual) SiteFooter or route-appropriate footer

### Route `/hub/material/[id]`
- [x] **DS-RT-12-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-12-02** (visual) text-display / text-body typography
- [x] **DS-RT-12-03** (visual) SiteFooter or route-appropriate footer

### Route `/hub/region/[slug]`
- [x] **DS-RT-13-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-13-02** (visual) text-display / text-body typography
- [x] **DS-RT-13-03** (visual) SiteFooter or route-appropriate footer

### Route `/state/[state-slug]`
- [x] **DS-RT-14-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-14-02** (visual) text-display / text-body typography
- [x] **DS-RT-14-03** (visual) SiteFooter or route-appropriate footer

### Route `/watchlist`
- [x] **DS-RT-15-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-15-02** (visual) text-display / text-body typography
- [x] **DS-RT-15-03** (visual) SiteFooter or route-appropriate footer

### Route `/saved`
- [x] **DS-RT-16-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-16-02** (visual) text-display / text-body typography
- [x] **DS-RT-16-03** (visual) SiteFooter or route-appropriate footer

### Route `/map`
- [x] **DS-RT-17-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-17-02** (visual) text-display / text-body typography
- [x] **DS-RT-17-03** (visual) SiteFooter or route-appropriate footer

### Route `/insights`
- [x] **DS-RT-18-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-18-02** (visual) text-display / text-body typography
- [x] **DS-RT-18-03** (visual) SiteFooter or route-appropriate footer

### Route `/liquidate`
- [x] **DS-RT-19-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-19-02** (visual) text-display / text-body typography
- [x] **DS-RT-19-03** (visual) SiteFooter or route-appropriate footer

### Route `/status`
- [x] **DS-RT-20-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-20-02** (visual) text-display / text-body typography
- [x] **DS-RT-20-03** (visual) SiteFooter or route-appropriate footer

### Route `/accessibility`
- [x] **DS-RT-21-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-21-02** (visual) text-display / text-body typography
- [x] **DS-RT-21-03** (visual) SiteFooter or route-appropriate footer

### Route `/pricing`
- [x] **DS-RT-22-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-22-02** (visual) text-display / text-body typography
- [x] **DS-RT-22-03** (visual) SiteFooter or route-appropriate footer

### Route `/account`
- [x] **DS-RT-23-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-23-02** (visual) text-display / text-body typography
- [x] **DS-RT-23-03** (visual) SiteFooter or route-appropriate footer

### Route `/support`
- [x] **DS-RT-24-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-24-02** (visual) text-display / text-body typography
- [x] **DS-RT-24-03** (visual) SiteFooter or route-appropriate footer

### Route `/app`
- [x] **DS-RT-25-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-25-02** (visual) text-display / text-body typography
- [x] **DS-RT-25-03** (visual) SiteFooter or route-appropriate footer

### Route `/terms`
- [x] **DS-RT-26-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-26-02** (visual) text-display / text-body typography
- [x] **DS-RT-26-03** (visual) SiteFooter or route-appropriate footer

### Route `/privacy`
- [x] **DS-RT-27-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-27-02** (visual) text-display / text-body typography
- [x] **DS-RT-27-03** (visual) SiteFooter or route-appropriate footer

### Route `/refund-policy`
- [x] **DS-RT-28-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-28-02** (visual) text-display / text-body typography
- [x] **DS-RT-28-03** (visual) SiteFooter or route-appropriate footer

### Route `/launch-readiness`
- [x] **DS-RT-29-01** (auto) AppShell or equivalent global chrome
- [x] **DS-RT-29-02** (visual) text-display / text-body typography
- [x] **DS-RT-29-03** (visual) SiteFooter or route-appropriate footer
