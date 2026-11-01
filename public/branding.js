// Visual cleanup: hide source cards and replace the text V-Bucks glyph with the actual coin artwork.
(() => {
  const hideSources = () => {
    const sourceBox = document.getElementById("sourceStatus");
    if (sourceBox) sourceBox.style.display = "none";
  };

  const replaceRewardGlyphs = () => {
    document.querySelectorAll(".reward, .history-row strong").forEach(el => {
      if (el.dataset.vbucksArtDone === "1") return;
      const raw = el.textContent.trim();
      const match = raw.match(/^(?:Ⓥ|V-Bucks)\s*([\d,]+)$/i);
      if (!match) return;
      const amount = match[1];
      const img = document.createElement("img");
      img.src = "vbucks-logo.png";
      img.alt = "V-Bucks";
      img.className = "vbucks-mark";
      const span = document.createElement("span");
      span.textContent = amount;
      el.replaceChildren(img, span);
      el.dataset.vbucksArtDone = "1";
    });
  };

  const refresh = () => {
    hideSources();
    replaceRewardGlyphs();
  };

  refresh();
  const observer = new MutationObserver(refresh);
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
})();
