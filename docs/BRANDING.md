# Quiblyx

The product name is **Quiblyx**, spelled `q-u-i-b-l-y-x`. Both supplied PNG references in `logo/` were corrected in place. Named light and dark versions are `logo/quiblyx-logo.png` and `logo/quiblyx-logo-dark.png`.

The application uses a simplified SVG adaptation of the supplied blue Q, with a rounded text wordmark for legibility at sidebar size. The SVG is an interface adaptation, not an exact vector trace of the original artwork. Removing the photographic background/glow from the interface version keeps it readable on navy and white surfaces.

- Mark and favicon: `apps/web/public/brand/quiblyx-mark.svg`
- Full raster logos: `apps/web/public/brand/quiblyx-logo.png` and `apps/web/public/brand/quiblyx-logo-dark.png`
- Shared name and metadata: `apps/web/app/brand.ts`
- Theme: `apps/web/app/brand.css`
- Primary blue: `#185CF4`; navigation navy: `#0B1635`
- Optional name override: `NEXT_PUBLIC_PRODUCT_NAME` at web build time. Changing the name does not automatically replace the Q artwork.
- Backend API titles and email subjects use `PRODUCT_NAME` (default `Quiblyx`).

Mock-mode notices remain visible: branding does not change provider support or production readiness.
