// The ONLY place to point the frontend at a backend. On Render this file is regenerated at build time
// by scripts/write-config.sh from environment variables; never put API keys here.
window.BASEERAH_CONFIG = {
  API_BASE_URL: "http://localhost:8000", // "" = same origin (when FastAPI serves this folder)
  USE_MOCK: false,                       // true = use js/mock.js (no backend needed, placeholder data only)
  REQUEST_TIMEOUT_MS: 90000,
  CONTACT_EMAIL: "",                     // shown on about.html#contact when set
};
