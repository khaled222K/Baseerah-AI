// Inline stroke icons (24x24). Built with DOM APIs, never innerHTML.
const C = (r = 9) => `M12 ${12 - r}a${r} ${r} 0 1 0 0 ${2 * r}a${r} ${r} 0 1 0 0-${2 * r}Z`;
const PATHS = {
  home: ["M3 10.5 12 3l9 7.5", "M5 9.5V21h14V9.5", "M10 21v-6h4v6"],
  chat: ["M20.5 11.5a8.5 8.5 0 0 1-12.4 7.6L3.5 20.5l1.4-4.4A8.5 8.5 0 1 1 20.5 11.5Z"],
  search: ["M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14Z", "m20.5 20.5-4.3-4.3"],
  book: ["M2.5 4.5H8a4 4 0 0 1 4 4V21a3 3 0 0 0-3-3H2.5Z", "M21.5 4.5H16a4 4 0 0 0-4 4V21a3 3 0 0 1 3-3h6.5Z"],
  info: [C(), "M12 16.5v-5", "M12 8h.01"],
  plus: ["M12 5v14", "M5 12h14"],
  send: ["M21.5 2.5 10.5 13.5", "M21.5 2.5 15 21.5l-4.5-8-8-4.5Z"],
  bookmark: ["M18.5 21 12 16.5 5.5 21V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2Z"],
  star: ["M12 2.8l2.8 5.8 6.4.9-4.6 4.5 1.1 6.3L12 17.3l-5.7 3 1.1-6.3L2.8 9.5l6.4-.9Z"],
  copy: ["M9 9h11v11H9Z", "M5 15H4V4h11v1"],
  external: ["M14.5 3.5h6v6", "M10 14 20.5 3.5", "M18 13.5V19a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 19V8a1.5 1.5 0 0 1 1.5-1.5H11"],
  list: ["M9 6h12", "M9 12h12", "M9 18h12", "M4 6h.01", "M4 12h.01", "M4 18h.01"],
  menu: ["M4 6h16", "M4 12h16", "M4 18h16"],
  x: ["M18 6 6 18", "M6 6l12 12"],
  check: ["M20 6 9 17l-5-5"],
  checkCircle: [C(), "m8.5 12.5 2.5 2.5 5-5.5"],
  alert: [C(), "M12 7.5v5.5", "M12 16.5h.01"],
  help: [C(), "M9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.6", "M12 17h.01"],
  trash: ["M3.5 6.5h17", "M9 6.5V4h6v2.5", "M18.5 6.5 17.6 20.5H6.4L5.5 6.5"],
  refresh: ["M20.5 12a8.5 8.5 0 1 1-2.5-6", "M20.5 3.5V9H15"],
  shield: ["M12 21.5s7.5-3.7 7.5-9.5V5.3L12 2.5 4.5 5.3V12c0 5.8 7.5 9.5 7.5 9.5Z", "m9 12 2.2 2.2L15.5 10"],
  layers: ["M12 2.5 2.5 7.5 12 12.5l9.5-5Z", "m2.5 16.5 9.5 5 9.5-5", "m2.5 12 9.5 5 9.5-5"],
  file: ["M14 2.5H6.5A1.5 1.5 0 0 0 5 4v16a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 20V7.5Z", "M14 2.5v5h5", "M8.5 13h7", "M8.5 17h7"],
  cpu: ["M6 6h12v12H6Z", "M9.5 9.5h5v5h-5Z", "M9 2.5V6", "M15 2.5V6", "M9 18v3.5", "M15 18v3.5", "M2.5 9H6", "M2.5 15H6", "M18 9h3.5", "M18 15h3.5"],
  sparkle: ["M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9Z", "M19 16v4", "M17 18h4"],
  arrowUpLeft: ["M17 17 7 7", "M7 16V7h9"],
  chevronDown: ["m6 9 6 6 6-6"],
  clock: [C(), "M12 7v5l3.2 2"],
  quote: ["M9.5 7.5H5.5v5h4v-1c0 2-1 3.5-3 4.5", "M18.5 7.5h-4v5h4v-1c0 2-1 3.5-3 4.5"],
  scale: ["M12 3v18", "M7 21h10", "M5 7h14", "m5 7-3 6a3.5 3.5 0 0 0 6 0Z", "m19 7-3 6a3.5 3.5 0 0 0 6 0Z"],
  gear: [C(3), "M12 2.5v3", "M12 18.5v3", "M2.5 12h3", "M18.5 12h3", "m5.3 5.3 2.1 2.1", "m16.6 16.6 2.1 2.1", "m5.3 18.7 2.1-2.1", "m16.6 7.4 2.1-2.1"],
};

export function icon(name, cls = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", `icon ${cls}`.trim());
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  for (const d of PATHS[name] || PATHS.info) {
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", d);
    svg.appendChild(p);
  }
  return svg;
}
