/*
 * Save the World zone badge colors.
 * Load this file AFTER app.js. It only adds a zone class to .mission-region.
 * It does not alter mission cards, frames, layout, or data.
 */
(() => {
  "use strict";

  const zoneClasses = {
    "stonewood": "zone-stonewood",
    "plankerton": "zone-plankerton",
    "canny valley": "zone-canny",
    "twine peaks": "zone-twine"
  };

  function applyZoneColors(root = document) {
    root.querySelectorAll(".mission-region").forEach((badge) => {
      const zone = (badge.textContent || "").trim().toLowerCase();
      const className = zoneClasses[zone];

      badge.classList.remove(
        "zone-stonewood",
        "zone-plankerton",
        "zone-canny",
        "zone-twine"
      );

      if (className) badge.classList.add(className);
    });
  }

  function start() {
    applyZoneColors();

    const missionList = document.getElementById("missionsList");
    if (!missionList) return;

    const observer = new MutationObserver(() => applyZoneColors(missionList));
    observer.observe(missionList, {
      childList: true,
      subtree: true,
      characterData: true
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
