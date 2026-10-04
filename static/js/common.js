// Shared across every page's JS.
//
// Module 7 removed DEMO_USER_ID entirely — identity now comes from the
// session cookie the browser sends automatically, not from a hardcoded
// constant. Any request that needs to know "which user" just fetches
// from an endpoint that reads request.session server-side (see auth.js
// for the shared fetch wrapper that handles the "not logged in" case).

function money(n) {
  return "₹" + Math.round(Number(n)).toLocaleString("en-IN");
}

function specsLine(p) {
  return `${p.bedrooms} bed · ${p.bathrooms} bath · ${p.area_sqft ? p.area_sqft + " sqft" : "—"} · ${p.parking ? "Parking" : "No parking"}`;
}

// Small inline SVG icons, replacing the emoji characters (♡ ♥ 💬 ✕) the
// UI used to rely on for icon duty — emoji rendering varies by OS/font
// and reads as an unstyled default rather than a deliberate choice.
// currentColor means each icon inherits whatever color its button uses.
const ICONS = {
  heartOutline: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>',
  heartFilled: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:-2px"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>',
};
