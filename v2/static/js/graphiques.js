// Info-bulles des graphiques : au survol de la souris ET au focus clavier (touche Tab).
// Les textes viennent de l'attribut data-info et sont insérés avec textContent
// (jamais innerHTML) : un texte contenant du HTML ne peut pas s'exécuter.
(function () {
  "use strict";
  const bulle = document.createElement("div");
  bulle.className = "infobulle";
  bulle.setAttribute("role", "status");
  bulle.hidden = true;
  document.body.appendChild(bulle);

  function montrer(cible) {
    const info = cible.getAttribute("data-info");
    if (!info) return;
    bulle.textContent = info;
    bulle.hidden = false;
    const r = cible.getBoundingClientRect();
    const b = bulle.getBoundingClientRect();
    let x = r.left + r.width / 2 - b.width / 2 + window.scrollX;
    x = Math.max(8 + window.scrollX, Math.min(x, window.scrollX + document.documentElement.clientWidth - b.width - 8));
    bulle.style.left = x + "px";
    bulle.style.top = (r.top + window.scrollY - b.height - 8) + "px";
  }

  function cacher() { bulle.hidden = true; }

  document.querySelectorAll("[data-info]").forEach(function (cible) {
    cible.addEventListener("pointerenter", function () { montrer(cible); });
    cible.addEventListener("pointerleave", cacher);
    cible.addEventListener("focus", function () { montrer(cible); });
    cible.addEventListener("blur", cacher);
  });
})();
