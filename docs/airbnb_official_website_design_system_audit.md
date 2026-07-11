# Airbnb Official Website Design System Audit

Comprehensive reference based on Airbnb's live website, Airbnb Help Centre, Airbnb host pages, Airbnb Newsroom, public Airbnb Design writing, and observed live CSS/HTML tokens.

Prepared on: 2026-07-11  
Primary observed pages: [airbnb.com](https://www.airbnb.com/), [Airbnb search/homes](https://www.airbnb.com/s/homes), [Airbnb listing page](https://www.airbnb.com/rooms/50842466), [Airbnb Help Centre](https://www.airbnb.com/help), [Host your home on Airbnb](https://www.airbnb.com/host/homes), [Airbnb Newsroom](https://news.airbnb.com/)  
Public design references: [Building a Visual Language](https://medium.com/airbnb-design/building-a-visual-language-behind-the-scenes-of-our-airbnb-design-system-224748775e4e), [Working Type](https://medium.com/airbnb-design/working-type-81294544608b), [Airbnb Design Language System by Karri Saarinen](https://karrisaarinen.com/dls/), [Airbnb Newsroom](https://news.airbnb.com/), [Airbnb accessibility newsroom article](https://news.airbnb.com/en-uk/innovating-to-make-travel-more-accessible/)

## Scope And Interpretation

This document focuses on Airbnb's public web product: discovery, search, listing detail pages, hosting pages, Help Centre, and Newsroom. Airbnb is not a static marketing site. It is a transactional marketplace with large-scale search, localization, maps, filters, listing photography, booking workflows, account menus, help content, host onboarding, app deep links, and SEO landing pages.

The system has several layers:

- Brand layer: Airbnb logo, Rausch red, travel/community tone, photography-led identity.
- Product layer: search, category tabs, listing cards, maps, filters, booking widgets, user menus.
- Content layer: destination SEO pages, listing metadata, Help Centre articles, host education, newsroom.
- DLS/token layer: CSS variables for palette, typography, spacing, motion, shadows, material blur, and components.
- Infrastructure layer: preloaded JS chunks, LCP instrumentation, image CDN transforms, OpenSearch, app metadata, JSON-LD, and localized domains.

Important caveat: no finite document can literally contain every Airbnb asset, experiment, localized variant, listing, route, or private internal design decision. This file aims to leave out no major observable design, content, interaction, commerce, accessibility, SEO, performance, or token system visible in the sampled official Airbnb web properties and public Airbnb design references.

## 1. Typography

### Typeface System

Airbnb's product typography is anchored in Airbnb Cereal. Airbnb's public "Working Type" design article explains that Airbnb created Cereal to unify typography across product and brand surfaces, and that its Design Language System references type styles as system values rather than ad hoc font declarations. The live Airbnb site exposes this font stack:

```css
--typography-font-family-cereal-font-family:
  'Airbnb Cereal VF', 'Circular', -apple-system, 'BlinkMacSystemFont',
  'Roboto', 'Helvetica Neue', sans-serif;
```

The observed stack is meaningful:

- `Airbnb Cereal VF`: primary custom variable font.
- `Circular`: historical/geometric fallback.
- `-apple-system` and `BlinkMacSystemFont`: platform-native Apple fallback.
- `Roboto`: Android/Google platform fallback.
- `Helvetica Neue`: broad web fallback.
- `sans-serif`: final generic fallback.

This makes Airbnb typography more brand-owned than a pure system-font interface, while still resilient when the custom font fails.

### Font Weights

Observed DLS weight tokens include:

```css
--typography-weight-book400: 400;
--typography-weight-medium500: 500;
--typography-weight-semibold600: 600;
--typography-weight-bold700: 700;
```

Airbnb uses weight as hierarchy:

- 400 Book: body text, descriptions, supporting copy, standard metadata.
- 500 Medium: subtle emphasis and selected/interactive labels.
- 600 Semibold: card titles, section titles, buttons, important labels.
- 700 Bold: strong emphasis, occasional badge/label use.

The interface rarely uses ultra-heavy display text on transactional pages. Host and marketing pages use larger display treatments, but search/listing pages stay compact and scannable.

### Type Scale

Observed live tokens include:

```css
--typography-base-extra-small10px-font-size: 0.625rem;
--typography-body-text_11_15-font-size: 0.6875rem;
--typography-body-text_12_16-font-size: 0.75rem;
--typography-body-text_14_18-font-size: 0.875rem;
--typography-body-text_16_20-font-size: 1rem;
--typography-body-text_18_24-font-size: 1.125rem;
--typography-body-paragraphs-text_14_20-font-size: 0.875rem;
--typography-body-paragraphs-text_16_22-font-size: 1rem;
--typography-body-paragraphs-text_16_24-font-size: 1rem;
--typography-body-paragraphs-text_18_28-font-size: 1.125rem;
--typography-titles-semibold_14_18-font-size: 0.875rem;
--typography-titles-semibold_16_20-font-size: 1rem;
--typography-titles-semibold_18_24-font-size: 1.125rem;
--typography-titles-semibold_22_26-font-size: 1.375rem;
--typography-titles-semibold_26_30-font-size: 1.625rem;
--typography-titles-semibold_32_36-font-size: 2rem;
--typography-special-display-medium_40_44-font-size: 2.5rem;
--typography-special-display-medium_48_54-font-size: 3rem;
--typography-special-display-medium_60_68-font-size: 3.75rem;
--typography-special-display-medium_72_74-font-size: 4.5rem;
```

Practical usage:

- 10-12px: compact captions, legal/support metadata, small badges.
- 14px: listing card metadata, secondary labels, compact buttons.
- 16px: form labels, body, Help Centre paragraphs, nav labels.
- 18px: medium titles or support article cards.
- 22-32px: section headings, listing titles, Help Centre page sections.
- 40-72px: host/marketing hero display copy.

### Line Height

Airbnb's tokens encode size and line height in the token name. Examples:

- `body-text_12_16`: 12px text on 16px line-height.
- `body-text_14_18`: 14px text on 18px line-height.
- `body-text_16_20`: 16px text on 20px line-height.
- `body-paragraphs-text_16_24`: 16px body paragraph on 24px line-height.
- `titles-semibold_22_26`: 22px title on 26px line-height.
- `special-display-medium_72_74`: 72px display on 74px line-height.

This yields tight but readable UI text. Transactional card text is compact; support and explanatory body copy gets more breathing room.

### Letter Spacing

Most observed Airbnb typography tokens use `normal` letter spacing. A separate wide tracking token exists:

```css
--typography-tracking-normal-letter-spacing: normal;
--typography-tracking-wide-letter-spacing: 0.04em;
```

Airbnb does not rely on aggressive negative display tracking like some premium hardware brands. The geometric proportions of Cereal do much of the brand work. Wide tracking is reserved for specific labels, not general UI.

### Heading Hierarchy

Airbnb heading hierarchy varies by page type:

- Home/search pages: product UI is dominant; visible headings may be sparse because search and card grids carry the experience.
- Listing pages: listing title is the primary H1-like object; sections such as amenities, reviews, location, and host info follow.
- Help Centre: strong heading hierarchy with H1 for Help Centre identity/search and H2/H3 for article groups such as top articles and explore sections.
- Host pages: large marketing H1, followed by explanatory H2 sections.
- Newsroom: editorial H1/H2/H3 structure with article cards and press-style pages.

Observed markup uses role-based headings in places, such as `role="heading"` with `aria-level="2"` or `aria-level="3"`, especially in heavily componentized pages.

### Paragraph Rhythm

Airbnb product copy uses short fragments and metadata rows. Help and host pages use fuller paragraphs. The rhythm is task-driven:

- Search cards: short location/name line, distance/date line, price line.
- Listing pages: short descriptive sections with expandable content.
- Help Centre: direct explanatory sentences and article summaries.
- Host page: reassuring benefit-led copy.
- Newsroom: editorial paragraphs, longer than product UI.

The product interface avoids long paragraphs in the booking path; detailed text is progressively disclosed.

## 2. Color Palette / Color System

### Core Brand Color

Airbnb's signature red is exposed as Rausch:

```css
--palette-rausch: #FF385C;
--palette-rausch600: #FF385C;
--palette-product-rausch: #E00B41;
--palette-bg-primary-core: #FF385C;
```

Historically Airbnb used `#FF5A5F` in brand assets such as mask-icon color. Current live DLS tokens use `#FF385C` as the core interface red. Both appear in official assets, but they should not be treated as interchangeable for modern UI. Use `#FF385C` for current product UI and `#FF5A5F` only when matching legacy favicon/mask assets.

### Named Palette Tokens

Airbnb DLS uses named colors as well as semantic tokens:

```css
--palette-hof: #222222;
--palette-foggy: #6A6A6A;
--palette-bobo: #B0B0B0;
--palette-deco: #DDDDDD;
--palette-bebe: #EBEBEB;
--palette-faint: #F7F7F7;
--palette-white: #FFFFFF;
--palette-black: #000000;
--palette-arches: #C13515;
--palette-spruce: #008A05;
--palette-ondo: #E07912;
--palette-mykonou5: #428BFF;
--palette-plus: #92174D;
--palette-luxe: #460479;
```

The names make the palette easier to remember internally, while semantic aliases make components easier to theme.

### Neutral System

Observed neutral scale:

```css
--palette-grey0: #FFFFFF;
--palette-grey100: #F7F7F7;
--palette-grey200: #F2F2F2;
--palette-grey300: #EBEBEB;
--palette-grey400: #DDDDDD;
--palette-grey500: #C1C1C1;
--palette-grey600: #8C8C8C;
--palette-grey700: #6C6C6C;
--palette-grey800: #515151;
--palette-grey900: #3F3F3F;
--palette-grey1000: #222222;
--palette-grey1100: #000000;
```

These neutrals dominate Airbnb's UI. Listings and photos provide visual color; interface chrome remains white, light gray, and dark gray.

### Semantic Text Colors

Observed text tokens:

```css
--palette-text-primary: #222222;
--palette-text-primary-hover: #000000;
--palette-text-primary-disabled: #DDDDDD;
--palette-text-primary-inverse: #FFFFFF;
--palette-text-secondary: #6C6C6C;
--palette-text-secondary-disabled: #DDDDDD;
--palette-text-primary-error: #C13515;
--palette-text-legal: #318CF7;
--palette-text-link-disabled: #929292;
--palette-text-focused: #3F3F3F;
```

Primary text is nearly black, not pure black. Secondary text is medium gray. Error uses warm red/brown (`Arches`) rather than the primary brand red, reducing confusion between brand emphasis and error state.

### Background Colors

Observed background tokens:

```css
--palette-bg-primary: #FFFFFF;
--palette-bg-primary-hover: #F7F7F7;
--palette-bg-primary-selected: #F7F7F7;
--palette-bg-primary-disabled: #F7F7F7;
--palette-bg-primary-error: #FFF5F3;
--palette-bg-secondary: #F7F7F7;
--palette-bg-quaternary: #F2F2F2;
--palette-bg-primary-inverse: #222222;
--palette-bg-primary-inverse-hover: #000000;
```

Airbnb pages are usually white with gray section breaks. The Help Centre and footer use light-gray blocks. Dark surfaces appear in specific promotional or overlay contexts, not as a default app theme.

### Gradients

Airbnb uses branded gradients for primary actions and premium tiers:

```css
--palette-rausch-gradient-linear-gradient:
  linear-gradient(to right, #E61E4D 0%, #E31C5F 50%, #D70466 100%);

--palette-rausch-gradient-radial-gradient:
  radial-gradient(circle at center, #FF385C 0%, #E61E4D 27.5%,
  #E31C5F 40%, #D70466 57.5%, #BD1E59 75%, #BD1E59 100%);

--palette-plus-gradient-linear-gradient:
  linear-gradient(to right, #BD1E59 0%, #92174D 50%, #861453 100%);

--palette-luxe-gradient-linear-gradient:
  linear-gradient(to right, #59086E 0%, #460479 50%, #440589 100%);
```

The gradients have RTL variants, proving the system accounts for directionality.

### Buttons

Primary buttons can use the Rausch gradient or solid dark/white treatments depending on context. Observed button variables include background, color, border color, border width, border radius, backdrop filter, padding, and shadow. Default DLS button radius falls back to 8px.

### Borders

Observed border tokens include:

```css
--palette-border-primary: #222222;
--palette-border-secondary: #8C8C8C;
--palette-border-tertiary: #DDDDDD;
--palette-border-primary-inverse: #FFFFFF;
--palette-border-secondary-disabled: #EBEBEB;
--palette-border-tertiary-error: #C13515;
```

Airbnb uses borders to define cards, inputs, filters, menus, and search containers. Border contrast is usually restrained; selected states use darker borders or inset outlines.

### Overlays

Overlay and modal backgrounds use white surfaces, dark scrims, and material blur tokens. Shadow tokens include black alpha levels from 0.04 to 0.60, supporting everything from faint card separation to heavy modal backdrop depth.

## 3. Layout System

### Page Families

Airbnb has several distinct page families:

- Search/discovery: header, search bar, category tabs, listing grid, optional map, filters.
- Listing detail page: header, photo gallery, title block, summary, booking card, details sections, reviews, host info, location, policies.
- Help Centre: search-led support landing, top articles, category cards, contact section.
- Host landing page: marketing hero, earnings/benefits, hosting education, co-host paths.
- Newsroom: editorial homepage, article cards, category archives, press releases.
- Footer/global utility: legal, language, currency, social, sitemap-like links.

Each page family uses the same DLS tokens but different density and hierarchy.

### Containers

Observed container variables include:

```css
--page-shell-max-content-width: 1280px;
--page-shell-max-content-width: 1440px !important;
```

Listing pages expose a local max-width around 1120px for main content sections. Help pages can use wider page shells up to 1280px or 1920px depending on component. Airbnb does not use one global container width; it adapts per content type.

### Grid System

Search pages use responsive card grids. At wide widths, listings appear in multiple columns with consistent gutters. With map enabled, the layout can split into results and map. Listing pages use a two-column detail pattern: main content column plus sticky booking card/sidebar on desktop, collapsing on mobile.

Common grid patterns:

- Multi-column listing card grid.
- Horizontal category scroller.
- Split results/map view.
- Listing detail content plus reservation panel.
- Help article card grid.
- Host page marketing sections with image/text alternation.
- Footer columns on desktop, stacked/collapsible sections on mobile.

### Page Structure

Search/discovery page:

1. Global header/logo/user menu.
2. Search form with destination/date/guest controls.
3. Category tabs or filters.
4. Listing grid and/or map.
5. Floating map/list controls on mobile.
6. Footer/discover links.

Listing page:

1. Header.
2. Listing title and actions.
3. Photo gallery.
4. Overview and key facts.
5. Main detail sections.
6. Sticky reservation card.
7. Reviews/location/host/policies.
8. Similar listings/internal links.

Help page:

1. Header.
2. Search field.
3. Suggested/top article sections.
4. Topic cards.
5. Contact prompt.
6. Footer.

### Alignment

Airbnb uses left alignment for dense content and centered alignment for marketing/host hero moments. Cards are left-aligned inside their tile. Search controls use pill-contained grouped alignment. Prices and action controls often align to right edges where scanning benefits.

## 4. Spacing System

### Spacing Tokens

Observed spacing tokens:

```css
--spacing-micro2px: 2px;
--spacing-micro4px: 4px;
--spacing-micro8px: 8px;
--spacing-micro12px: 12px;
--spacing-micro16px: 16px;
--spacing-micro24px: 24px;
--spacing-micro32px: 32px;
--spacing-macro16px: 16px;
--spacing-macro24px: 24px;
--spacing-macro32px: 32px;
--spacing-macro40px: 40px;
--spacing-macro48px: 48px;
--spacing-macro64px: 64px;
--spacing-macro80px: 80px;
```

The distinction between micro and macro spacing is important:

- Micro spacing governs labels, icon gaps, form internals, card text, chips.
- Macro spacing governs sections, page gutters, card grids, modal padding.

### Margins And Padding

Common observed button padding defaults:

```css
--dls-button_padding-top: 14px;
--dls-button_padding-right: 24px;
--dls-button_padding-bottom: 14px;
--dls-button_padding-left: 24px;
```

Search and card components use dense internal spacing because users scan many items. Marketing and Help Centre sections use more vertical space.

### Vertical Rhythm

Airbnb's vertical rhythm is dense in product surfaces and relaxed in educational surfaces:

- Listing card: image, small gap, title, metadata, price.
- Search form: compact grouped controls.
- Listing page: section dividers create rhythm.
- Help articles: heading, short summary, card grid.
- Host page: larger hero spacing and roomy section transitions.

### Card Spacing

Listing cards usually have no heavy outer card chrome. The image and text block define the card. Internal rhythm is tight: title and metadata lines are close enough to scan rapidly, with price emphasized. Help cards use more explicit card boundaries and larger internal padding.

### Section Spacing

Airbnb uses section dividers and whitespace rather than decorative bands. On listing pages, rules between sections are essential for readability. On host pages, larger visual sections create campaign-like pacing.

## 5. Imagery System

### Photo Style

Airbnb is a photography-led product. The imagery system includes:

- Listing photos uploaded by hosts.
- Editorial host/guest photography.
- Help Centre illustrations/photos.
- Newsroom press images.
- Destination and category imagery.
- User profile/avatar images.
- Map/listing thumbnails.

The system must handle inconsistent user-generated listing photography while preserving a polished product UI. Airbnb does this through fixed aspect ratios, object-fit cover, border radius, skeleton loading, and consistent card composition.

### Image Tokens And Behavior

Observed image variables:

```css
--AirImage-aspect-ratio
--AirImage-height
--AirImage-width
--AirImage-border-radius
--AirImage-object-fit
--AirImage-object-position
```

Observed image CSS includes:

```css
object-fit: cover;
aspect-ratio: var(--AirImage-aspect-ratio, var(--dls-liteimage-aspect-ratio));
border-radius: var(--AirImage-border-radius, var(--dls-liteimage-border-radius));
```

This shows that image behavior is componentized rather than manually styled per image.

### Aspect Ratios

Observed aspect-ratio references include:

- Square: `1 / 1`.
- 16:9.
- 9:16.
- 4:3.
- 3:4.
- 3:2.
- 2:3.
- Custom listing/card ratios.
- Host/help images with explicit pixel height.

Listing card images often use rounded rectangular crops. Listing detail galleries use larger multi-image compositions with a hero image and smaller thumbnails on desktop.

### Crops

Airbnb crops for usefulness. A listing image must reveal the space: room, bed, view, pool, exterior, amenity, or atmosphere. Crops are usually centered/object-cover, with object position available for tuning. Help Centre photos/illustrations can be more symbolic.

### Galleries

Listing pages include photo galleries with previous/next controls and accessible labels such as "Button: Next Image" and "Button: Previous Image". Gallery interactions must support browsing, modal expansion, and mobile swiping.

### Overlays And Captions

Overlays appear for image controls, save/share buttons, badges, and gallery buttons. Listing card captions are not overlaid on images by default; text sits below the image for readability. Badges such as "Guest favourite" can appear in or near card media.

### Lazy Loading And LCP

Live markup includes `elementtiming="LCP-target"` and LCP instrumentation scripts that observe images and headings. Airbnb cares explicitly about which image/text becomes the Largest Contentful Paint candidate.

## 6. Component System

### Buttons

Airbnb buttons are tokenized through DLS variables:

```css
--dls-button_background
--dls-button_color
--dls-button_border-color
--dls-button_border-width
--dls-button_border-radius
--dls-button_padding-top
--dls-button_padding-right
--dls-button_padding-bottom
--dls-button_padding-left
--dls-button_box-shadow
--dls-button_backdrop-filter
```

Button types:

- Primary booking/search buttons, often Rausch/gradient.
- Secondary outline buttons.
- Text buttons.
- Icon buttons.
- Menu buttons.
- Close buttons.
- Carousel controls.
- Filter buttons.
- Language/currency buttons.
- Social links.

### Cards

Card types:

- Listing card.
- Experience/service card.
- Help article card.
- Help topic card.
- Host education card.
- Newsroom article card.
- Modal selection card.
- Filter option card.

Listing cards are image-first and compact. Help cards are content-first. Host cards are editorial. The component system adapts the card grammar by task.

### Navbars

Airbnb header includes:

- Logo/home link with accessible label.
- Search form or compact search trigger.
- Primary tabs such as stays/experiences/services depending on current product state.
- "Airbnb your home" / hosting CTA in some contexts.
- Language/currency button.
- Profile/menu button.

Header density changes by viewport and route. Search pages use a more functional header; host pages can use more marketing-style navigation.

### Search Forms

Search is a core component, not just a form field. It includes:

- Destination ("Where").
- Date range.
- Guests.
- Category/product tabs.
- Submit/search button.
- Expanded overlays for date picker and guest controls.
- Mobile full-screen or bottom-sheet variants.

Observed search form markup uses `role="search"` and `method="get"`.

### Accordions

Accordions appear in filters, Help Centre content, listing details, policies, FAQs, and footer/mobile sections. They conserve vertical space and support progressive disclosure.

### Tabs

Tabs appear in search product/category switching. Observed markup includes `role="tablist"`, `role="tab"`, `aria-selected`, and tab ids such as `search-block-tab-STAYS`.

### Carousels

Carousels appear in listing images, recommendation sections, category scrollers, and possibly Help/host content. Controls use previous/next labels and direction-aware placement.

### Modals And Sheets

Airbnb uses modal/sheet patterns for:

- Login/sign-up.
- Language/currency selection.
- Filters.
- Share.
- Save/wishlist.
- Photo gallery.
- Date picker.
- Guest selector.
- Map/list toggles.
- Cancellation or policy details.

Desktop often uses centered modals or popovers; mobile often uses full-screen sheets or bottom sheets.

### Filters

Filters are critical to Airbnb's product. They can include:

- Type of place.
- Price range.
- Rooms and beds.
- Amenities.
- Booking options.
- Property type.
- Accessibility features.
- Host language.
- Location/category constraints.

Filter UI combines chips, segmented controls, steppers, checkboxes, toggles, sliders, and modal sheets.

## 7. Motion System

### Motion Tokens

Observed motion curves:

```css
--motion-standard-curve-animation-timing-function: cubic-bezier(0.2, 0, 0, 1);
--motion-enter-curve-animation-timing-function: cubic-bezier(0.1, 0.9, 0.2, 1);
--motion-exit-curve-animation-timing-function: cubic-bezier(0.4, 0, 1, 1);
--motion-linear-curve-animation-timing-function: cubic-bezier(0, 0, 1, 1);
```

Observed spring tokens include fast, standard, slow, and bounce variants with computed durations such as roughly 584ms standard and 746ms slow.

### Transition Durations

Observed durations include:

- 100ms for stay-length slider transitions.
- 140ms for compact transform feedback.
- 150ms for small animations.
- 200ms for focus/box-shadow transitions.
- 250ms for button content transforms.
- 300ms for button background/border/color changes.
- 500ms for some slider and reduced-motion animation fallbacks.
- 1.3s for shimmer/skeleton animation.

### Hover States

Hover states are usually subtle:

- Background changes to gray100 or gray200.
- Text/icon darkens from secondary to primary.
- Cards may reveal carousel controls.
- Buttons can alter background/gradient.
- Search segments can elevate or highlight.

### Active States

Active states include transform compression, darker fills, selected borders, and stronger shadows. Buttons often transition `box-shadow`, `transform`, `background-color`, `border-color`, and `color`.

### Scroll Effects

Airbnb uses scroll for sticky headers, sticky booking cards, category bars, map/list controls, and content section anchoring. The markup includes scroll-related controls and animation timeline checks. Motion is functional rather than cinematic on core booking pages.

### Loading States

Observed skeleton/shimmer tokens:

```css
--dls-shimmer-duration: 1.3s;
--dls-shimmer_delay: 100ms;
--dls-shimmer-animation-end-color: var(--palette-grey300);
```

Shimmer placeholders appear for images, cards, and content during route/data loading. Airbnb also includes explicit map loading labels.

### Reduced Motion

Observed reduced-motion variables appear in animation declarations. This indicates that Airbnb can adjust motion duration and animation behavior for reduced-motion contexts.

## 8. Iconography

### Icon Style

Airbnb icons are simple, rounded, geometric, and interface-focused. The logo is a filled vector mark/wordmark. UI icons include search, menu, user/profile, globe/language, heart/save, share, close, chevrons, filters, map, rating star, and social icons.

### Filled Versus Outline

Usage pattern:

- Logo: filled.
- Navigation/utility icons: mostly outline or simple filled shapes.
- Star/rating: filled or solid at small sizes.
- Heart/save: outline default, filled/active when saved.
- Social icons: brand-recognizable glyphs.
- Amenity/accessibility icons: line or simple pictogram style.

### Size

Icons are small visually but live in larger hit targets. Header icons sit inside circular or pill buttons. Listing controls use compact but tappable buttons. Mobile controls are larger and often inside bottom bars or sheets.

### Stroke Width

Airbnb's icon style uses medium-weight strokes: not hairline, not heavy. Strokes are balanced to 14-18px text. The system prioritizes recognition at small sizes.

### Usage Rules

Icons are used when they reduce cognitive load:

- Search button icon.
- Filter icon.
- Map/list toggle.
- Rating star.
- Heart/save.
- Globe/language.
- Menu/profile.
- Carousel arrows.
- Amenity icons.

Airbnb does not decorate every heading with icons. Icons support actions, categories, amenities, and status.

## 9. Material / Surface System

### Surface Types

Airbnb surfaces include:

- Page background: white.
- Secondary section background: #F7F7F7.
- Cards: white or image-led.
- Header: white, sometimes sticky.
- Search bar: white pill with border/shadow.
- Dropdowns/popovers: white elevated surfaces.
- Modals/sheets: white with shadow/scrim.
- Map controls: white floating controls.
- Material blurred surfaces in select controls.

### Material Blur Tokens

Observed material tokens:

```css
--material-backgrounds-extra-thin-background-color: rgba(218,218,218,0.40);
--material-backgrounds-extra-thin-backdrop-filter: blur(8px) saturate(1);
--material-backgrounds-thin-background-color: rgba(240,240,240,0.50);
--material-backgrounds-thin-backdrop-filter: blur(36px) saturate(1.6);
--material-backgrounds-regular-background-color: rgba(250,250,250,0.72);
--material-backgrounds-regular-backdrop-filter: blur(24px) saturate(1.6);
--material-backgrounds-thick-background-color: rgba(240,240,240,0.86);
--material-backgrounds-thick-backdrop-filter: blur(12px) saturate(3);
--material-backgrounds-extra-thick-background-color: rgba(255,255,255,0.925);
--material-backgrounds-extra-thick-backdrop-filter: blur(16px) saturate(1.6);
```

Airbnb uses blur/material sparingly compared with card and shadow surfaces. It appears where overlays or floating controls benefit from background context.

### Shadows

Observed shadows include:

```css
0 1px 2px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.05)
0 2px 16px rgba(0,0,0,0.12)
0 6px 16px rgba(0,0,0,0.12)
0 6px 20px rgba(0,0,0,0.2)
0 8px 28px rgba(0,0,0,0.28)
```

Shadow tokens:

```css
--palette-shadow50: rgba(0,0,0,0.04);
--palette-shadow100: rgba(0,0,0,0.08);
--palette-shadow150: rgba(0,0,0,0.12);
--palette-shadow200: rgba(0,0,0,0.135);
--palette-shadow250: rgba(0,0,0,0.18);
--palette-shadow300: rgba(0,0,0,0.20);
--palette-shadow350: rgba(0,0,0,0.28);
--palette-shadow600: rgba(0,0,0,0.60);
```

### Radius

Observed radii:

- 4px: small details.
- 8px: default DLS button fallback.
- 12px: listing cards/images.
- 16px, 20px, 24px, 28px, 32px: larger cards/modals.
- 40px, 50px, 99em, 9999px: pills and circular controls.
- 100% / 50%: avatars and icon buttons.

Airbnb's radius system is friendlier and softer than strict enterprise UI, but not cartoonish.

### Elevation

Elevation is functional:

- Header/search bar can elevate on scroll.
- Popovers float above page.
- Booking card can be sticky/elevated.
- Map controls float.
- Modals have heavy depth.
- Cards generally do not need heavy elevation because images and grid gaps define them.

## 10. Content System

### Tone Of Voice

Airbnb's voice is direct, warm, and practical. It balances travel aspiration with transactional clarity. Examples from observed metadata and pages:

- "Get an Airbnb for every kind of trip."
- "Host your home on Airbnb."
- "Your home could make money with Airbnb."
- "Search how-tos and more."
- "Need to get in touch?"
- "We’ll start with some questions and get you to the right place."

### Content By Page Type

Search/discovery:

- Short labels.
- Destination/category names.
- Price and availability.
- Ratings and guest-favorite badges.
- Minimal prose.

Listing page:

- Listing title.
- Location and room facts.
- Host-written description.
- Amenities.
- Reviews.
- Rules, cancellation, safety, policies.

Help Centre:

- Plain-language problem statements.
- Article titles like "Cancel your home reservation as a guest."
- Summary copy that tells the user what the article helps with.

Host page:

- Benefit-led copy.
- Reassurance.
- Money-making potential.
- Co-host and setup support.

Newsroom:

- Corporate/editorial tone.
- Announcements, policy, travel trends, host/community stories.

### Headings

Airbnb headings are often plain and task-focused rather than clever. They name the task or promise:

- "Top articles"
- "Explore more"
- "Need to get in touch?"
- "Host your home on Airbnb"
- "Popular homes"
- "Holiday rentals, cabins, beach houses & more"

### CTAs

Common CTA patterns:

- Search.
- Reserve.
- Show more.
- Contact us.
- Get started.
- Learn more.
- Log in or sign up.
- Airbnb your home.
- Find a co-host.
- Choose a language.
- Choose a currency.

### SEO Copy

Airbnb SEO copy is extremely inventory/category driven. The home page meta description states broad marketplace scale: millions of rentals, Guest Favourites, and 220+ countries/regions. Listing pages use listing-specific titles and descriptions with date, property type, location, and amenities. This gives search engines highly specific indexable content.

### Page Narrative

Airbnb product pages follow a conversion narrative:

1. Let the user search.
2. Show credible inventory quickly.
3. Make comparison easy through photos, price, rating, and location.
4. Provide filters when intent sharpens.
5. Give deep listing detail when a user selects a stay.
6. Reserve with clear price/date/guest context.
7. Support trust through reviews, host info, policies, and help.

## 11. Navigation System

### Header

Airbnb header patterns include:

- Logo/home link.
- Search form or compact search pill.
- Product tabs.
- Host CTA.
- Language/currency button.
- Profile/menu button.

The header adapts significantly by route and viewport.

### Menu

The profile/menu system exposes actions such as log in/sign up, hosting links, help, and account-oriented links. It is usually a dropdown/popup on desktop and can become a sheet on mobile.

### Breadcrumbs

Airbnb public listing/search pages do not emphasize visible breadcrumb trails the way documentation sites do. SEO hierarchy is handled through metadata, internal links, destination/category pages, and structured data rather than prominent breadcrumb UI.

### Footer Links

The footer supports:

- Inspiration links.
- Support links.
- Hosting links.
- Airbnb corporate/company links.
- Newsroom links.
- Terms, privacy, sitemap.
- Language selector.
- Currency selector.
- Social links.

Footer content varies by locale and page family.

### Mobile Navigation

Mobile Airbnb navigation is bottom-sheet and task oriented:

- Search becomes a compact trigger or full-screen flow.
- Filters become modal sheets.
- Date/guest selection uses touch-friendly controls.
- Map/list toggle becomes prominent.
- Sticky reservation or action bars appear on listing pages.

### Sticky CTAs

Sticky CTAs are important on listing pages:

- Desktop: sticky booking/reservation card.
- Mobile: sticky bottom reserve bar or action area.
- Search: floating map/list control or filter/action buttons.

## 12. Interaction System

### Hover

Hover states:

- Gray background for buttons and menu items.
- Darker text/icon states.
- Image carousel controls appear.
- Card affordance increases subtly.
- Search segments highlight.

### Focus

Observed focus rings use strong dual-ring shadows:

```css
box-shadow: 0 0 0 2px rgba(255,255,255,0.8),
            0 0 0 4px var(--palette-border-primary);
```

Other focus patterns use `0 0 0 2px` primary outlines. Airbnb's focus styles are intentionally visible.

### Active

Active states include pressed transforms, darker backgrounds, selected outlines, inset shadows, and filled icons. Buttons transition transform and color properties.

### Disabled

Disabled states use muted text/border/background:

- `--palette-text-primary-disabled: #DDDDDD`
- `--palette-border-primary-disabled: #DDDDDD`
- `--palette-bg-primary-disabled: #F7F7F7`
- `--palette-text-link-disabled: #929292`

### Selected

Selected filters/tabs use darker borders, selected text color, or filled backgrounds. Tabs include `aria-selected`. Chips and filters show selected state through border/fill contrast.

### Error

Error states use `Arches` red/brown tokens:

```css
--palette-text-primary-error: #C13515;
--palette-bg-primary-error: #FFF5F3;
--palette-border-tertiary-error: #C13515;
```

This separates error from brand red.

### Success

Success uses Spruce green:

```css
--palette-icon-success: #008A05;
--palette-spruce: #008A05;
```

Success appears in confirmation, verification, or included-feature contexts.

## 13. Form System

### Inputs

Airbnb forms include:

- Search destination input.
- Date picker.
- Guest steppers.
- Price sliders.
- Filter checkboxes/toggles.
- Login/sign-up fields.
- Help Centre search.
- Host onboarding fields.
- Language/currency selectors.

Inputs are generally large, rounded, and label-forward.

### Labels

Search controls use compact labels such as "Where". Help Centre search uses "Search how-tos and more". Language/currency selectors use descriptive labels such as "Choose a language" and "Choose a currency."

### Validation

Validation must handle:

- Required destination/date fields.
- Invalid date ranges.
- Guest count limits.
- Payment method issues.
- Login/signup credential errors.
- Booking availability changes.
- Host onboarding missing information.

Errors should be field-specific, direct, and recoverable.

### Error Messages

Airbnb's help content style suggests error messaging should be plain and action-oriented. Do not use internal codes as primary copy. Preserve user input where possible.

### Contact Forms

Airbnb Help Centre does not lead with a generic contact form. It starts with search and guided questions, then routes the user to the right place. This is more scalable than a single open-ended form.

### Quote Forms

Airbnb does not use "quote forms" in the typical B2B sense. Pricing is produced through listing availability, dates, guests, fees, taxes, discounts, and policies. The equivalent is a reservation price breakdown.

## 14. Responsive System

### Mobile

Mobile behavior:

- Search expands into full-screen or sheet flows.
- Category tabs are horizontally scrollable.
- Listing grid becomes one or two columns depending width.
- Map/list toggle becomes a floating control.
- Filters open in sheets.
- Listing pages use sticky bottom reserve actions.
- Photo galleries become swipe-first.
- Footer stacks/collapses.

### Tablet

Tablet behavior:

- Search remains prominent.
- Listing grids gain more columns.
- Listing detail pages may still collapse booking components depending width.
- Larger images and modal sheets use more spacious layouts.

### Desktop

Desktop behavior:

- Full header/search bar.
- Multi-column listing grid.
- Optional split map/results.
- Listing detail with sticky booking card.
- Rich photo gallery layout.
- Footer columns.

### Breakpoints

Airbnb uses component-specific breakpoints rather than one simple scale. Observed CSS/media references include `min-width: 0px`, route/component-specific container widths, and page shell max widths of 1280px and 1440px. Public CSS class names are generated, so exact breakpoint naming is less human-readable than token values.

### Touch Targets

Airbnb maintains large interactive surfaces:

- Pill search controls.
- Round icon buttons.
- Large filter rows.
- Stepper controls.
- Full-width mobile buttons.
- Bottom sticky action bars.

### Image Resizing

Images use CDN transformations such as `im_w`, width, quality, and `auto=webp`. Listing images are served at multiple sizes and cropped through object-fit. This supports responsive performance and stable card composition.

### Safe Areas

Viewport metadata includes `viewport-fit=cover` on core Airbnb pages. This allows proper use of safe areas on modern mobile devices.

## 15. Accessibility System

### Semantic Structure

Observed accessibility patterns:

- `role="search"` on search form.
- `role="tablist"` and `role="tab"` for search tabs.
- `aria-selected` for selected tabs.
- `aria-label` for logo, search, menu, profile, close, language, currency, carousel controls, social links.
- `role="heading"` with `aria-level` in componentized headings.
- `aria-busy` on loading/skeleton elements.
- Decorative image wrappers marked `role="presentation"` and `aria-hidden="true"`.

### Contrast

Primary text `#222222` on white has strong contrast. Secondary text `#6C6C6C` is readable on white for metadata. Brand red must be used carefully for small text; Airbnb generally uses it for actions/backgrounds rather than long paragraphs.

### Keyboard Navigation

Keyboard users need access to:

- Search fields.
- Tabs.
- Filters.
- Date picker.
- Guest controls.
- Listing cards.
- Carousel/gallery controls.
- Menu/profile.
- Modal close buttons.
- Reservation controls.

Observed focus-visible styles support keyboard navigation.

### Screen Reader Labels

Airbnb labels visual controls explicitly. Examples observed include "Airbnb homepage", "Main navigation menu", "Search", "Choose a language", "Choose a currency", "Close", "Button: Next Image", and "Button: Previous Image".

### Focus Rings

Focus rings are visible and often dual-layered. Some focus styles use white and dark rings to remain visible on varied backgrounds.

### Readable Text

Help Centre uses larger paragraph line heights such as 16/24. Listing cards use compact text but rely on short lines. Long listing descriptions are typically expandable.

### Accessibility Filters

Airbnb has public accessibility initiatives and accessibility search filters. Airbnb's newsroom describes moving from a single "wheelchair accessible" filter to more detailed accessibility features, such as step-free access and accessible parking. This is part of the product system, not just compliance.

## 16. SEO Structure

### Metadata

Observed core metadata:

- `locale`.
- `application-name`.
- `theme-color`.
- viewport.
- OpenSearch link.
- Apple touch icons.
- favicon and mask icon.
- Open Graph site name, locale, URL, title, description, type, image.
- Twitter card, title, site, app ids, app URLs, description, image.
- app deep links.
- JSON-LD structured data.

### H1/H2 Hierarchy

Airbnb's componentized app may use role-based headings and dynamic headings. Listing pages and Help Centre pages expose structured headings for content sections. Newsroom uses conventional editorial heading structure.

### Internal Links

Internal links include:

- Destination/category pages.
- Listing pages.
- Help articles.
- Hosting pages.
- Co-host paths.
- Login/signup.
- Language/currency.
- Footer support/company links.
- Newsroom article/category links.

### Schema

Core Airbnb pages include `application/ld+json`. Listing pages include structured data scripts. Newsroom includes Yoast schema graph JSON-LD. This supports rich search representation and content hierarchy.

### Keyword Page Structure

Airbnb SEO is built from destination, property type, rental type, amenity, and trip-intent keywords:

- Holiday rentals.
- Cabins.
- Beach houses.
- Unique homes.
- Villas.
- Apartments.
- Monthly rentals.
- City/destination combinations.
- Listing-specific title/location/amenity combinations.

### App SEO / Deep Linking

Airbnb includes Twitter app metadata for iPhone, iPad, and Google Play, app ids, and `airbnb://` app URLs. Listing pages deep-link to rooms. This bridges web SEO with app acquisition and app reopening.

### Localization

Sampled Airbnb pages resolved with `en-IN` locale metadata and `airbnb.co.in` Open Graph URLs. Newsroom exposes many alternate locales. SEO structure is therefore region-aware.

## 17. Performance System

### Image Optimization

Airbnb images are delivered through `a0.muscache.com` and other asset hosts with transformation parameters:

- `im_w` for image width.
- `quality`.
- `auto=webp`.
- Explicit width/height attributes.
- `srcSet` variants.
- object-fit cover.

Listing images are the performance centerpiece because they dominate LCP and user decision-making.

### Lazy Loading

The app uses skeleton/shimmer states and route-level JS loading. Images and content can hydrate progressively. LCP candidates are tracked.

### Font Loading

Airbnb uses a custom Cereal variable font stack with robust fallbacks. There is also a script that checks Apple system-body font behavior and adjusts root font size if needed, showing attention to platform typography quirks.

### Script Weight

Airbnb is a heavy SPA-like marketplace. Observed pages preload many JavaScript chunks:

- Hyperloop browser runtime.
- Metro require/runtime chunks.
- Route handlers.
- Locale chunks.
- Homepage/search route chunks.
- App initializer.
- Common chunks.

The performance strategy is not "minimal JS"; it is chunking, preloading, instrumentation, caching, and progressive hydration.

### Core Web Vitals

Observed LCP instrumentation registers candidates among images and headings. Airbnb explicitly observes `IMG`, `H1`, `H2`, `H3`, `H4`, `H5`, and SVG candidates. This is unusually direct evidence that Core Web Vitals are integrated into the frontend runtime.

### Loading States

Skeleton shimmer gives users immediate structure while data/images load. Map loading uses accessible labels such as "Map is loading."

### CDN And Asset Domains

Observed asset sources:

- `a0.muscache.com` for Airbnb assets and transformed images.
- `images.contentstack.io` for Help/host content imagery.
- `news.airbnb.com` WordPress/newsroom assets.
- `d0a7e.airbnb.com` tags/monitoring script.

### Stability

Aspect-ratio wrappers, explicit width/height, page shell max widths, and image dimensions help reduce layout shift. Listing pages require stable layout because users compare many cards rapidly.

## 18. Design Tokens

### Color Tokens

```css
:root {
  --color-brand-rausch: #FF385C;
  --color-product-rausch: #E00B41;
  --color-text-primary: #222222;
  --color-text-secondary: #6C6C6C;
  --color-border: #DDDDDD;
  --color-border-strong: #222222;
  --color-bg-primary: #FFFFFF;
  --color-bg-secondary: #F7F7F7;
  --color-bg-quaternary: #F2F2F2;
  --color-error: #C13515;
  --color-success: #008A05;
  --color-info: #318CF7;
  --color-warning: #E07912;
}
```

### Typography Tokens

```css
:root {
  --font-cereal: 'Airbnb Cereal VF', 'Circular', -apple-system,
    'BlinkMacSystemFont', 'Roboto', 'Helvetica Neue', sans-serif;

  --weight-book: 400;
  --weight-medium: 500;
  --weight-semibold: 600;
  --weight-bold: 700;

  --text-12-16: 0.75rem / 1rem var(--font-cereal);
  --text-14-18: 0.875rem / 1.125rem var(--font-cereal);
  --text-16-20: 1rem / 1.25rem var(--font-cereal);
  --paragraph-16-24: 1rem / 1.5rem var(--font-cereal);
  --title-22-26: 1.375rem / 1.625rem var(--font-cereal);
  --title-32-36: 2rem / 2.25rem var(--font-cereal);
  --display-72-74: 4.5rem / 4.625rem var(--font-cereal);
}
```

### Spacing Tokens

```css
:root {
  --space-2: 2px;
  --space-4: 4px;
  --space-8: 8px;
  --space-12: 12px;
  --space-16: 16px;
  --space-24: 24px;
  --space-32: 32px;
  --space-40: 40px;
  --space-48: 48px;
  --space-64: 64px;
  --space-80: 80px;
}
```

### Radius Tokens

```css
:root {
  --radius-xs: 4px;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;
  --radius-xxl: 32px;
  --radius-pill: 9999px;
  --radius-circle: 50%;
}
```

### Shadow Tokens

```css
:root {
  --shadow-card: 0 1px 2px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.05);
  --shadow-popover: 0 6px 16px rgba(0,0,0,0.12);
  --shadow-modal: 0 8px 28px rgba(0,0,0,0.28);
  --shadow-focus: 0 0 0 2px rgba(255,255,255,0.8), 0 0 0 4px #222222;
}
```

### Motion Tokens

```css
:root {
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --ease-enter: cubic-bezier(0.1, 0.9, 0.2, 1);
  --ease-exit: cubic-bezier(0.4, 0, 1, 1);
  --ease-linear: cubic-bezier(0, 0, 1, 1);

  --duration-fast: 100ms;
  --duration-feedback: 140ms;
  --duration-focus: 200ms;
  --duration-button-transform: 250ms;
  --duration-button-color: 300ms;
  --duration-skeleton: 1.3s;
}
```

### Material Tokens

```css
:root {
  --material-extra-thin: rgba(218,218,218,0.40);
  --material-extra-thin-filter: blur(8px) saturate(1);
  --material-regular: rgba(250,250,250,0.72);
  --material-regular-filter: blur(24px) saturate(1.6);
  --material-thick: rgba(240,240,240,0.86);
  --material-thick-filter: blur(12px) saturate(3);
}
```

### Z-Index Tokens

Airbnb's exact internal z-index scale is not publicly readable as a simple token ladder from the sampled output, but a faithful implementation should maintain:

```css
:root {
  --z-base: 0;
  --z-card-control: 1;
  --z-sticky-header: 100;
  --z-sticky-reserve-bar: 200;
  --z-popover: 500;
  --z-map-control: 600;
  --z-scrim: 900;
  --z-modal: 1000;
  --z-toast: 1100;
}
```

## Cross-System Consistency Rules

To avoid contradictions when applying this audit:

1. Use Airbnb Cereal VF as the primary font; keep robust system fallbacks.
2. Use `#FF385C`/Rausch for current product brand action, not every red state.
3. Use `#C13515`/Arches for error states.
4. Let listing photography carry visual richness; keep UI chrome neutral.
5. Keep search and booking flows task-first and dense.
6. Use larger, warmer storytelling only on host/news/marketing pages.
7. Use card grids for inventory, not decorative cards for every section.
8. Use explicit accessible labels for icon-only controls.
9. Use skeleton loading for marketplace data and media.
10. Preserve page-specific SEO metadata for homepage, listing, host, help, and newsroom pages.
11. Treat mobile as a sheet-first, touch-first flow.
12. Keep filters progressive and recoverable; never bury core search actions.
13. Use component-specific breakpoints instead of forcing one layout breakpoint ladder.
14. Keep legal, cancellation, safety, and pricing copy clear and qualified.
15. Separate current live DLS tokens from older brand references when color values differ.

## Source Notes

Official Airbnb sources consulted:

- [Airbnb home page](https://www.airbnb.com/)
- [Airbnb search/homes](https://www.airbnb.com/s/homes)
- [Airbnb listing page sample](https://www.airbnb.com/rooms/50842466)
- [Airbnb Help Centre](https://www.airbnb.com/help)
- [Host your home on Airbnb](https://www.airbnb.com/host/homes)
- [Airbnb Newsroom](https://news.airbnb.com/)
- [Building a Visual Language - Airbnb Design](https://medium.com/airbnb-design/building-a-visual-language-behind-the-scenes-of-our-airbnb-design-system-224748775e4e)
- [Working Type - Airbnb Design](https://medium.com/airbnb-design/working-type-81294544608b)
- [Airbnb Design Language System - Karri Saarinen](https://karrisaarinen.com/dls/)
- [Airbnb accessibility newsroom article](https://news.airbnb.com/en-uk/innovating-to-make-travel-more-accessible/)

Implementation observations were made from live Airbnb HTML/CSS available on 2026-07-11, including DLS token variables, palette variables, typography variables, motion variables, material blur variables, Open Graph/Twitter metadata, JSON-LD script tags, accessibility attributes, image CDN URLs, LCP instrumentation, and route-level preloaded JavaScript bundles.
