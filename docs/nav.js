// Barre de navigation commune à toutes les pages (IA, compte du bot, Élan crypto).
// À charger juste après <body> : elle s'insère en haut de page et en bas sur téléphone.
(function () {
  "use strict";
  const LOGO = '<svg viewBox="0 0 24 24" aria-hidden="true"><g stroke="#22ab94" stroke-width="1.6" stroke-linecap="round">'
    + '<path d="M5 13v8M12 8v11M19 3v12"/></g><g fill="#22ab94"><rect x="3" y="15" width="4" height="4.5" rx=".6"/>'
    + '<rect x="10" y="10" width="4" height="6.5" rx=".6"/><rect x="17" y="5" width="4" height="8" rx=".6"/></g></svg>';
  const IC = {
    ia: '<path d="M4 18l5-6 4 3 7-9"/><path d="M4 21h16"/>',
    accueil: '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 9h18M8 14h3"/>',
    graphique: '<path d="M7 3v18M17 3v18"/><rect x="5" y="7" width="4" height="8"/><rect x="15" y="5" width="4" height="10"/>',
    ordres: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    plus: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
  };
  const ico = id => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${IC[id]}</svg>`;
  const HAUT = [["ia", "IA", "ia.html"], ["accueil", "Compte", "index.html#accueil"], ["graphique", "Graphique", "index.html#graphique"],
    ["strategies", "Stratégies", "index.html#strategies"], ["ordres", "Ordres", "index.html#ordres"], ["journal", "Journal", "index.html#journal"],
    null, ["elan", "Élan crypto", "elan.html"], ["reglages", "Réglages", "index.html#reglages"]];
  const BAS = [["ia", "IA", "ia.html"], ["accueil", "Compte", "index.html#accueil"], ["graphique", "Graphique", "index.html#graphique"],
    ["ordres", "Ordres", "index.html#ordres"], ["plus", "Plus", "index.html#plus"]];
  const DANS_PLUS = ["plus", "strategies", "journal", "reglages", "elan"];

  const entete = document.createElement("header");
  entete.className = "entete";
  entete.innerHTML = `<a class="marque" href="ia.html">${LOGO}<span>Bot de trading</span></a>
    <nav class="onglets" aria-label="Navigation">${HAUT.map(x => x ? `<a href="${x[2]}" data-nav="${x[0]}">${x[1]}</a>` : '<span class="sep"></span>').join("")}</nav>
    <div class="droite" id="entete-droite"><span class="etiquette-demo">DÉMO</span></div>`;
  const bas = document.createElement("nav");
  bas.className = "onglets-bas";
  bas.setAttribute("aria-label", "Navigation");
  bas.innerHTML = BAS.map(([id, nom, href]) => `<a href="${href}" data-nav="${id}">${ico(id)}${nom}</a>`).join("");
  document.body.prepend(entete);
  document.body.append(bas);

  window.navActif = function (id) {
    entete.querySelectorAll("[data-nav]").forEach(a => a.dataset.nav === id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
    const idBas = DANS_PLUS.includes(id) ? "plus" : id;
    bas.querySelectorAll("[data-nav]").forEach(a => a.dataset.nav === idBas ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  };
  const page = location.pathname.split("/").pop();
  navActif(page === "ia.html" ? "ia" : page === "elan.html" ? "elan" : (location.hash.slice(1) || "accueil"));

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
})();
