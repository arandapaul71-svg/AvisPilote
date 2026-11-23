/* AvisPilote — interface (JavaScript sans framework)
 *
 * Règles de sécurité suivies ici :
 *  - toute donnée venant du serveur (avis, noms...) passe par esc() avant d'être mise dans le HTML ;
 *  - aucun gestionnaire d'événement "onclick" dans le HTML (bloqué par la CSP) :
 *    on utilise des attributs data-action et un seul écouteur global ;
 *  - chaque requête qui modifie des données envoie le jeton CSRF.
 */
"use strict";

const etat = { me: null, avis: [], filtre: "a_valider", page: 1, edition: null, jours: 90, periode: "mois" };
const app = document.getElementById("app");

// ---------------------------------------------------------------------------
// Outils
// ---------------------------------------------------------------------------
function esc(valeur) {
  return String(valeur ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

async function api(chemin, { methode = "GET", corps } = {}) {
  const options = { method: methode, headers: {}, credentials: "same-origin" };
  if (methode !== "GET") options.headers["X-CSRF-Token"] = etat.me?.csrf || "";
  if (corps !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(corps);
  }
  const reponse = await fetch(chemin, options);
  const donnees = await reponse.json().catch(() => ({}));
  if (reponse.status === 401 && !chemin.startsWith("/api/login")) {
    location.hash = "#/connexion";
  }
  if (!reponse.ok) {
    const err = new Error(donnees.erreur || "Le serveur ne répond pas. Réessayez dans un instant.");
    err.donnees = donnees;
    throw err;
  }
  return donnees;
}

async function chargerMe() {
  etat.me = await api("/api/me");
  return etat.me;
}

let minuteurToast;
function toast(message, erreur = false) {
  const t = document.getElementById("toast");
  t.textContent = message;
  t.className = erreur ? "erreur-toast" : "";
  t.hidden = false;
  clearTimeout(minuteurToast);
  minuteurToast = setTimeout(() => { t.hidden = true; }, 4000);
}

const nombre = (n, d = 0) => (n ?? 0).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
const note = (n) => (n == null ? "—" : nombre(n, 1));

function etoiles(n) {
  const cases = [1, 2, 3, 4, 5].map((i) => `<span class="${i <= n ? "" : "vide"}">★</span>`).join("");
  return `<span class="etoiles" role="img" aria-label="${n} étoile${n > 1 ? "s" : ""} sur 5">${cases}</span>`;
}

function dateCourte(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
}

function dateComplete(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long" }) + " à " +
    d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }).replace(":", "h");
}

function nomMois(aaaamm) {
  const [a, m] = aaaamm.split("-").map(Number);
  return new Date(a, m - 1, 1).toLocaleDateString("fr-FR", { month: "long" });
}

function couleurNote(n) {
  if (n == null) return "var(--brume)";
  if (n >= 4.5) return "#2F7D5B";
  if (n >= 3.5) return "#8DBF9F";
  if (n >= 2.5) return "#F2B01E";
  return "#C2412D";
}

const LOGO = `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#F2B01E" d="M12 2l3 6.9 7.5.6-5.7 4.9 1.8 7.3L12 17.8 5.4 21.7l1.8-7.3L1.5 9.5 9 8.9z"/></svg>`;

// ---------------------------------------------------------------------------
// Routage : #/page?param=valeur
// ---------------------------------------------------------------------------
function lireHash() {
  const [chemin, requete] = location.hash.replace(/^#\/?/, "").split("?");
  return { page: chemin || "dashboard", params: new URLSearchParams(requete || "") };
}

const PAGES_COQUE = {
  dashboard: { titre: "Tableau de bord", rendu: pageDashboard },
  avis: { titre: "Avis et réponses", rendu: pageAvis },
  recap: { titre: "Récapitulatif", rendu: pageRecap },
  abonnement: { titre: "Abonnement", rendu: pageAbonnement },
  parametres: { titre: "Paramètres", rendu: pageParametres },
};

async function router() {
  const { page, params } = lireHash();
  try {
    await chargerMe();
  } catch (e) {
    app.innerHTML = `<p class="chargement">${esc(e.message)}</p>`;
    return;
  }
  if (!etat.me.connecte) return pageConnexion(page === "inscription" ? "inscription" : "connexion");
  if (page === "connexion" || page === "inscription") return (location.hash = "#/dashboard");
  if (page === "demarrage") return pageDemarrage(params);

  const sansSource = etat.me.entreprise.mode === "aucun";
  if (sansSource && !["abonnement", "parametres"].includes(page)) return (location.hash = "#/demarrage");

  const def = PAGES_COQUE[page] || PAGES_COQUE.dashboard;
  afficherCoque(page in PAGES_COQUE ? page : "dashboard");
  document.title = `${def.titre} — AvisPilote`;
  try {
    await def.rendu(params);
  } catch (e) {
    document.getElementById("page").innerHTML = `<div class="bloc"><p class="erreur">${esc(e.message)}</p></div>`;
  }
}

function afficherCoque(pageActive) {
  const me = etat.me;
  const q = me.quota;
  const lien = (page, texte, extra = "") =>
    `<a href="#/${page}" ${page === pageActive ? 'aria-current="page"' : ""}><span>${texte}</span>${extra}</a>`;
  app.innerHTML = `
    <div class="coque">
      <aside class="navigation">
        <div class="logo">${LOGO} AvisPilote</div>
        <nav aria-label="Navigation principale">
          ${lien("dashboard", "Tableau de bord")}
          ${lien("avis", "Avis et réponses", me.a_valider ? `<span class="pastille" title="Réponses à valider">${me.a_valider}</span>` : "")}
          ${lien("recap", "Récapitulatif")}
          ${lien("abonnement", "Abonnement")}
          ${lien("parametres", "Paramètres")}
        </nav>
        <div class="jauge-nav">
          <strong>${esc(me.entreprise.name)}</strong><br>
          Formule ${esc(me.entreprise.plan_nom)} : ${q.utilises} / ${q.quota} avis en ${nomMois(q.mois)}
          <div class="jauge ${q.depasse ? "pleine" : ""}"><span style="width:${q.pourcentage}%"></span></div>
          <button class="bouton-lien" data-action="deconnexion">Se déconnecter</button>
        </div>
      </aside>
      <main class="contenu" id="page"><p class="chargement">Chargement…</p></main>
    </div>`;
}

// ---------------------------------------------------------------------------
// Connexion et inscription
// ---------------------------------------------------------------------------
function pageConnexion(mode) {
  document.title = "AvisPilote — vos avis Google, compris et répondus";
  const plans = etat.me.plans;
  const typeLib = { boulangerie: "Boulangerie", restaurant: "Restaurant", fleuriste: "Fleuriste", coiffeur: "Coiffeur", autre: "Autre commerce" };
  app.innerHTML = `
    <div class="accueil">
      <section class="accueil-gauche">
        <div class="logo">${LOGO} AvisPilote</div>
        <div>
          <h1>Chaque avis Google reçoit sa réponse.</h1>
          <p>AvisPilote répond à vos clients dans votre ton, repère les jours qui ont fait venir du monde
             et vous dit ce que vos clients aiment… et ce qui les agace.</p>
          <div class="avis-exemple">
            ${etoiles(5)} <strong>Léa M.</strong>
            <p>Les croissants sont un régal et la vendeuse est adorable !</p>
            <p class="reponse">Merci beaucoup Léa ! Nous sommes ravis que vous ayez apprécié notre accueil et nos produits. À très vite !</p>
          </div>
        </div>
        <small>Essai gratuit de 14 jours, sans carte bancaire.</small>
      </section>
      <section class="accueil-droite">
        <form data-form="${mode}" novalidate>
          <div class="onglets" role="tablist">
            <button type="button" role="tab" aria-selected="${mode === "connexion"}" data-action="aller" data-cible="#/connexion">Se connecter</button>
            <button type="button" role="tab" aria-selected="${mode === "inscription"}" data-action="aller" data-cible="#/inscription">Créer un compte entreprise</button>
          </div>
          ${mode === "inscription" ? `
            <label for="f-nom">Nom de l'entreprise</label>
            <input id="f-nom" name="name" required maxlength="80" placeholder="Boulangerie Martin">
            <label for="f-type">Type de commerce</label>
            <select id="f-type" name="type">${etat.me.types.map((t) => `<option value="${t}">${typeLib[t] || t}</option>`).join("")}</select>
            <label for="f-plan">Formule</label>
            <select id="f-plan" name="plan">${Object.entries(plans).map(([k, p]) =>
              `<option value="${k}">${esc(p.nom)} — ${p.prix} € HT/mois, ${p.quota} avis/mois</option>`).join("")}</select>` : ""}
          <label for="f-email">Adresse e-mail</label>
          <input id="f-email" name="email" type="email" autocomplete="email" required>
          <label for="f-mdp">Mot de passe</label>
          <input id="f-mdp" name="password" type="password" minlength="8" required
                 autocomplete="${mode === "inscription" ? "new-password" : "current-password"}">
          ${mode === "inscription" ? `<small>8 caractères minimum.</small>` : ""}
          <p class="erreur" id="erreur-form"></p>
          <button type="submit" class="bouton-etoile">${mode === "inscription" ? "Créer mon compte" : "Se connecter"}</button>
        </form>
      </section>
    </div>`;
}

async function soumettreAuth(form) {
  const donnees = Object.fromEntries(new FormData(form));
  const inscription = form.dataset.form === "inscription";
  const erreur = document.getElementById("erreur-form");
  erreur.textContent = "";
  try {
    await api(inscription ? "/api/register" : "/api/login", { methode: "POST", corps: donnees });
    location.hash = inscription ? "#/demarrage" : "#/dashboard";
    router();
  } catch (e) {
    erreur.textContent = e.message;
  }
}

// ---------------------------------------------------------------------------
// Démarrage : lier Google ou essayer la démo
// ---------------------------------------------------------------------------
const ERREURS_GOOGLE = {
  google_non_configure: "La liaison Google n'est pas encore configurée sur ce serveur (identifiants OAuth manquants dans le fichier .env). Utilisez la démo en attendant.",
  etat_invalide: "La connexion Google a expiré. Recommencez.",
  refus: "Vous n'avez pas autorisé l'accès à votre fiche Google.",
  google: "Google a refusé la connexion. Vérifiez que l'accès à l'API Business Profile a été accordé à l'application.",
  aucune_fiche: "Aucune fiche d'établissement n'a été trouvée sur ce compte Google.",
};

function pageDemarrage(params) {
  const me = etat.me;
  const erreur = ERREURS_GOOGLE[params.get("erreur")];
  app.innerHTML = `
    <div class="contenu" style="margin:0 auto">
      <div class="logo" style="margin-bottom:2rem">${LOGO} AvisPilote</div>
      <h1>Bienvenue, ${esc(me.entreprise.name)}</h1>
      <p class="discret">Dernière étape : indiquez d'où viennent vos avis.</p>
      ${erreur ? `<div class="bandeau-quota"><p>${esc(erreur)}</p></div>` : ""}
      <div class="choix-source">
        <section class="bloc">
          <h2>Connecter ma fiche Google</h2>
          <p>Connectez-vous avec le compte Google qui gère votre fiche d'établissement. AvisPilote importe vos avis
             et pourra y répondre en votre nom. Vous gardez la main : les réponses aux avis négatifs attendent toujours votre validation.</p>
          <a class="bouton bouton-etoile" href="/auth/google/start">Connecter Google</a>
          ${me.google_configure ? "" : `<small>Pas encore disponible sur ce serveur.</small>`}
        </section>
        <section class="bloc">
          <h2>Essayer avec des avis de démonstration</h2>
          <p>Trois mois de faux avis pour votre type de commerce, avec un événement, un jour difficile
             et un mois qui dépasse le quota de la formule Essentiel.</p>
          <button class="bouton-clair" data-action="demo">Charger la démo</button>
        </section>
      </div>
      <p style="margin-top:2rem"><button class="bouton-lien" data-action="deconnexion">Se déconnecter</button></p>
    </div>`;
}

// ---------------------------------------------------------------------------
// Tableau de bord
// ---------------------------------------------------------------------------
function bandeauxQuota(q) {
  const plan = etat.me.plans[q.plan];
  if (q.depasse) {
    return `<div class="bandeau-quota" role="alert">
      <p><strong>Quota atteint.</strong> ${q.hors_quota} avis de ${nomMois(q.mois)} ne sont pas pris en compte :
      pas de réponse automatique et pas d'analyse dans le récap. Votre formule ${esc(plan.nom)} inclut ${q.quota} avis par mois.</p>
      <a class="bouton" href="#/abonnement">Voir les formules</a></div>`;
  }
  if (q.pourcentage >= 80) {
    return `<div class="bandeau-quota bandeau-info"><p>Vous avez utilisé ${q.utilises} avis sur ${q.quota} ce mois-ci.
      Au-delà, les nouveaux avis ne seront plus pris en compte jusqu'au mois prochain.</p>
      <a class="bouton bouton-clair" href="#/abonnement">Voir les formules</a></div>`;
  }
  return "";
}

function enteteSource() {
  const e = etat.me.entreprise;
  const source = e.mode === "google" ? `Fiche Google : ${esc(e.google_location_title || "connectée")}` : "Mode démo : avis fictifs";
  const synchro = e.last_sync ? ` (mise à jour le ${dateComplete(e.last_sync)})` : "";
  return `${source}${synchro}`;
}

async function pageDashboard() {
  const page = document.getElementById("page");
  const d = await api(`/api/dashboard?jours=${etat.jours}`);
  const k = d.kpi;
  const evo = k.evolution_note == null ? "" :
    `<span class="${k.evolution_note >= 0 ? "hausse" : "baisse"}">${k.evolution_note >= 0 ? "+" : ""}${nombre(k.evolution_note, 2)} vs période précédente</span>`;

  page.innerHTML = `
    <div class="entete-page">
      <div><h1>${esc(etat.me.entreprise.name)}</h1><p>${enteteSource()}</p></div>
      <button class="bouton-clair" data-action="synchroniser">Mettre à jour les avis</button>
    </div>
    ${bandeauxQuota(d.quota)}
    ${k.a_valider ? `<div class="bandeau-quota bandeau-info"><p><strong>${k.a_valider} réponse${k.a_valider > 1 ? "s attendent" : " attend"} votre validation</strong> (avis de 3 étoiles ou moins).</p>
      <a class="bouton" href="#/avis">Valider les réponses</a></div>` : ""}

    <section class="bloc">
      <div class="entete-page" style="margin-bottom:.5rem">
        <h2>Vos avis jour par jour</h2>
        <div class="periode-choix" role="group" aria-label="Période">
          ${[30, 60, 90].map((j) => `<button class="${j === etat.jours ? "" : "bouton-clair"}" data-action="jours" data-jours="${j}" aria-pressed="${j === etat.jours}">${j} jours</button>`).join("")}
        </div>
      </div>
      <div class="chiffres">
        <div class="chiffre"><b>${note(k.note)} ★</b><span>note moyenne</span> ${evo}</div>
        <div class="chiffre"><b>${k.nombre}</b><span>avis reçus</span></div>
        <div class="chiffre"><b>${k.taux_reponse} %</b><span>avis avec réponse</span></div>
        <div class="chiffre"><b>${k.negatifs}</b><span>avis à 1 ou 2 étoiles</span></div>
      </div>
      ${graphiqueJours(d.par_jour, d.pics)}
      <div class="legende">
        <span><i style="background:#2F7D5B"></i>note du jour ≥ 4,5</span>
        <span><i style="background:#8DBF9F"></i>3,5 à 4,4</span>
        <span><i style="background:#F2B01E"></i>2,5 à 3,4</span>
        <span><i style="background:#C2412D"></i>moins de 2,5</span>
        <span>▼ jour inhabituel</span>
      </div>
    </section>

    <section class="bloc">
      <h2>Les jours qui sortent de l'ordinaire</h2>
      <p class="discret">Un jour est signalé quand il reçoit au moins 2,5 fois plus d'avis que d'habitude.
         S'il est bien noté, c'est souvent qu'une animation ou un produit a attiré du monde : à refaire.</p>
      ${d.pics.length ? `<ul class="evenements">${d.pics.map(pic).join("")}</ul>` : `<p class="vide">Aucun jour inhabituel sur cette période.</p>`}
    </section>

    <div class="grille-2">
      <section class="bloc">
        <h2>Répartition des notes</h2>
        <div class="barres-h">${[5, 4, 3, 2, 1].map((n) => {
          const nb = d.repartition[n] || 0;
          const pct = k.nombre ? (100 * nb) / k.nombre : 0;
          return `<span>${n} ★</span><div class="piste"><span style="width:${pct}%;background:${couleurNote(n)}"></span></div><span class="valeur">${nb}</span>`;
        }).join("")}</div>
      </section>
      <section class="bloc">
        <h2>Par jour de la semaine</h2>
        <div class="barres-h">${(() => {
          const max = Math.max(1, ...d.semaine.map((s) => s.nombre));
          return d.semaine.map((s) => `<span>${s.jour}</span>
            <div class="piste" title="Note moyenne ${note(s.note)}"><span style="width:${(100 * s.nombre) / max}%;background:${couleurNote(s.note)}"></span></div>
            <span class="valeur">${s.nombre}</span>`).join("");
        })()}</div>
        <p class="discret" style="margin-top:.75rem">La couleur indique la note moyenne de ce jour-là.</p>
      </section>
    </div>

    <section class="bloc" style="margin-top:1.25rem">
      <h2>Note moyenne par mois</h2>
      <div class="barres-h">${d.mois.map((m) => `<span>${nomMois(m.month)}</span>
        <div class="piste"><span style="width:${(100 * m.note) / 5}%;background:${couleurNote(m.note)}"></span></div>
        <span class="valeur">${note(m.note)}</span>`).join("")}</div>
    </section>`;
}

function pic(p) {
  return `<li class="evenement">
    <div class="date">${dateCourte(p.jour)}<small>${p.jour_semaine}</small></div>
    <div>
      <span class="nature ${p.nature}">${esc(p.interpretation)}</span>
      <p>${p.nombre} avis ce jour-là contre ${nombre(p.moyenne_habituelle, 1)} d'habitude, note moyenne ${note(p.note)} ★</p>
      <div class="themes">
        ${p.qualites.map((t) => `<span class="theme q">${esc(t)}</span>`).join("")}
        ${p.defauts.map((t) => `<span class="theme d">${esc(t)}</span>`).join("")}
      </div>
      ${p.exemple ? `<blockquote>« ${esc(p.exemple)} »</blockquote>` : ""}
    </div>
  </li>`;
}

function graphiqueJours(jours, pics) {
  const L = 900, H = 250, g = 34, d = 10, h = 34, b = 28;
  const max = Math.max(4, ...jours.map((j) => j.nombre));
  const largeur = (L - g - d) / jours.length;
  const y = (v) => H - b - ((H - b - h) * v) / max;
  const indexPics = new Set(pics.map((p) => p.jour));

  const grille = [0, Math.round(max / 2), max].map((v) =>
    `<line x1="${g}" x2="${L - d}" y1="${y(v)}" y2="${y(v)}" stroke="#E3E6EF"/>
     <text x="${g - 8}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join("");

  let alterne = 0;
  const barres = jours.map((j, i) => {
    const x = g + i * largeur;
    const hauteur = Math.max(0, y(0) - y(j.nombre));
    let rect = j.nombre ? `<rect x="${x + 1}" y="${y(j.nombre)}" width="${Math.max(1, largeur - 2)}" height="${hauteur}" rx="1.5" fill="${couleurNote(j.note)}">
      <title>${dateCourte(j.jour)} : ${j.nombre} avis, note ${note(j.note)}</title></rect>` : "";
    if (indexPics.has(j.jour)) {
      const cx = x + largeur / 2;
      const haut = y(j.nombre) - 8 - (alterne++ % 2) * 14;
      rect += `<text x="${cx}" y="${haut}" text-anchor="middle" class="etiquette-pic">▼ ${j.nombre}</text>`;
    }
    return rect;
  }).join("");

  const pas = jours.length > 60 ? 15 : jours.length > 30 ? 10 : 5;
  const axe = jours.map((j, i) => (i % pas === 0 ? `<text x="${g + i * largeur + largeur / 2}" y="${H - 8}" text-anchor="middle">${dateCourte(j.jour)}</text>` : "")).join("");

  return `<div class="graphique-conteneur"><svg class="graphique" viewBox="0 0 ${L} ${H}" role="img" aria-label="Nombre d'avis par jour sur ${jours.length} jours, coloré selon la note moyenne">
    ${grille}${barres}${axe}</svg></div>`;
}

// ---------------------------------------------------------------------------
// Avis et réponses
// ---------------------------------------------------------------------------
const LIBELLES_FILTRES = { a_valider: "À valider", tous: "Tous", negatifs: "1-2 étoiles", publiees: "Répondus", hors_quota: "Hors quota" };
const LIBELLES_STATUTS = { publiee: "Réponse publiée", a_valider: "À valider", hors_quota: "Hors quota" };

async function pageAvis(params) {
  if (params.get("filtre")) etat.filtre = params.get("filtre");
  const page = document.getElementById("page");
  const d = await api(`/api/reviews?filtre=${encodeURIComponent(etat.filtre)}&page=${etat.page}`);
  etat.avis = d.avis;
  etat.listeInfos = d;
  page.innerHTML = `
    <div class="entete-page">
      <div><h1>Avis et réponses</h1><p>${enteteSource()}</p></div>
      <button class="bouton-clair" data-action="synchroniser">Mettre à jour les avis</button>
    </div>
    ${bandeauxQuota(etat.me.quota)}
    <div class="filtres" role="group" aria-label="Filtrer les avis">
      ${Object.entries(LIBELLES_FILTRES).map(([k, lib]) =>
        `<button data-action="filtre" data-filtre="${k}" aria-pressed="${k === etat.filtre}">${lib} <span class="compte">${d.compteurs[k]}</span></button>`).join("")}
    </div>
    <div id="liste-avis">${listeAvis()}</div>`;
}

function listeAvis() {
  const d = etat.listeInfos;
  if (!etat.avis.length) {
    return `<div class="bloc vide">${etat.filtre === "a_valider"
      ? "Toutes les réponses sont validées. Les prochains avis de 3 étoiles ou moins apparaîtront ici."
      : "Aucun avis dans cette catégorie."}</div>`;
  }
  const pagination = d.pages > 1 ? `<div class="pagination">
      <button class="bouton-clair" data-action="page" data-page="${d.page - 1}" ${d.page <= 1 ? "disabled" : ""}>Page précédente</button>
      <span>Page ${d.page} sur ${d.pages}</span>
      <button class="bouton-clair" data-action="page" data-page="${d.page + 1}" ${d.page >= d.pages ? "disabled" : ""}>Page suivante</button>
    </div>` : "";
  return etat.avis.map(carteAvis).join("") + pagination;
}

function carteAvis(a) {
  const q = etat.me.quota;
  const plan = etat.me.plans[q.plan];
  const enEdition = etat.edition === a.id || (a.processed && a.status === "a_valider");
  const statut = a.processed ? a.status : "hors_quota";

  let bas = "";
  if (!a.processed) {
    bas = `<p class="message-quota">Cet avis n'est pas pris en compte : le quota de ${plan.quota} avis de votre formule
      ${esc(plan.nom)} était atteint ce mois-là. <a href="#/abonnement">Voir les formules</a></p>`;
  } else if (enEdition) {
    bas = `
      ${a.solution ? `<div class="solution"><strong>Ce que vous pouvez faire</strong>${esc(a.solution)}</div>` : ""}
      <label for="rep-${a.id}">Réponse proposée</label>
      <textarea id="rep-${a.id}" maxlength="4000">${esc(a.reply)}</textarea>
      <div class="actions">
        <button class="bouton-etoile" data-action="publier" data-id="${a.id}">Publier la réponse</button>
        <button class="bouton-clair" data-action="regenerer" data-id="${a.id}">Autre formulation</button>
        ${a.status === "publiee" ? `<button class="bouton-lien" data-action="annuler-edition">Annuler</button>` : ""}
      </div>`;
  } else {
    bas = `
      ${a.solution && a.stars <= 3 ? `<div class="solution"><strong>Ce que vous pouvez faire</strong>${esc(a.solution)}</div>` : ""}
      <div class="reponse-publiee">${esc(a.reply)}</div>
      <div class="actions">
        <small>Publiée${a.reply_published_at ? " le " + dateComplete(a.reply_published_at) : ""}</small>
        <button class="bouton-lien" data-action="modifier" data-id="${a.id}">Modifier la réponse</button>
      </div>`;
  }

  return `<article class="avis ${a.stars <= 2 ? "negatif" : ""} ${a.processed ? "" : "hors-quota"}" id="avis-${a.id}">
    <div class="avis-entete">
      <div><strong>${esc(a.author)}</strong> ${etoiles(a.stars)}</div>
      <div><small>${dateComplete(a.created_at)}</small> <span class="statut ${statut}">${LIBELLES_STATUTS[statut]}</span></div>
    </div>
    <p class="texte">${a.comment ? esc(a.comment) : `<span class="discret">Note sans commentaire.</span>`}</p>
    ${a.processed && (a.qualites.length || a.defauts.length) ? `<div class="themes">
      ${a.qualites.map((t) => `<span class="theme q">${esc(t)}</span>`).join("")}
      ${a.defauts.map((t) => `<span class="theme d">${esc(t)}</span>`).join("")}</div>` : ""}
    ${bas}
  </article>`;
}

function rafraichirListe() {
  document.getElementById("liste-avis").innerHTML = listeAvis();
}

// ---------------------------------------------------------------------------
// Récapitulatif
// ---------------------------------------------------------------------------
const PERIODES = { mois: "Mois en cours", mois_precedent: "Mois précédent", semaine: "Cette semaine" };

async function pageRecap() {
  const page = document.getElementById("page");
  let r;
  let erreurPeriode = "";
  try {
    r = await api(`/api/recap?periode=${etat.periode}`);
  } catch (e) {
    if (!e.donnees?.upgrade) throw e;
    erreurPeriode = e.message;
    etat.periode = "mois";
    r = await api("/api/recap?periode=mois");
  }
  const max = Math.max(1, ...r.qualites.map((x) => x.nombre), ...r.defauts.map((x) => x.nombre));
  page.innerHTML = `
    <div class="entete-page">
      <div><h1>Ce que disent vos clients</h1><p>${esc(r.libelle)} : du ${dateCourte(r.debut)} au ${dateCourte(r.fin)}</p></div>
      <div class="periode-choix" role="group" aria-label="Période du récap">
        ${Object.entries(PERIODES).map(([k, lib]) => `<button class="${k === etat.periode ? "" : "bouton-clair"}" aria-pressed="${k === etat.periode}" data-action="periode" data-periode="${k}">${lib}</button>`).join("")}
      </div>
    </div>
    ${erreurPeriode ? `<div class="bandeau-quota bandeau-info"><p>${esc(erreurPeriode)}.</p><a class="bouton" href="#/abonnement">Voir les formules</a></div>` : ""}
    ${r.ignores ? `<div class="bandeau-quota"><p>${r.ignores} avis de cette période ne sont pas inclus dans ce récap : ils dépassent le quota de votre formule.</p>
      <a class="bouton" href="#/abonnement">Voir les formules</a></div>` : ""}
    <section class="bloc"><p class="synthese">${esc(r.synthese)}</p></section>
    <div class="grille-2">
      <section class="bloc">
        <h2 class="titre-q">Qualités relevées</h2>
        ${r.qualites.length ? `<ul class="liste-themes">${r.qualites.map((t) => `
          <li>
            <div class="ligne-theme"><span>${esc(t.libelle)}</span><span class="discret">${t.nombre} avis · ${t.pourcentage} %</span></div>
            <div class="mini-barre"><span style="width:${(100 * t.nombre) / max}%;background:var(--feuille)"></span></div>
            ${t.exemples.map((ex) => `<p class="citation">« ${esc(ex.texte)} » ${esc(ex.auteur)}</p>`).join("")}
          </li>`).join("")}</ul>` : `<p class="vide">Pas encore de qualité relevée sur cette période.</p>`}
      </section>
      <section class="bloc">
        <h2 class="titre-d">Défauts relevés</h2>
        ${r.defauts.length ? `<ul class="liste-themes">${r.defauts.map((t) => `
          <li>
            <div class="ligne-theme"><span>${esc(t.libelle)}</span><span class="discret">${t.nombre} avis · ${t.pourcentage} %</span></div>
            <div class="mini-barre"><span style="width:${(100 * t.nombre) / max}%;background:var(--brique)"></span></div>
            ${t.exemples.map((ex) => `<p class="citation">« ${esc(ex.texte)} » ${esc(ex.auteur)}</p>`).join("")}
            <ul class="solutions-liste">${t.solutions.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
          </li>`).join("")}</ul>` : `<p class="vide">Aucun défaut relevé sur cette période.</p>`}
      </section>
    </div>`;
}

// ---------------------------------------------------------------------------
// Abonnement
// ---------------------------------------------------------------------------
function pageAbonnement() {
  const me = etat.me;
  const q = me.quota;
  const essai = me.entreprise.trial_ends && new Date(me.entreprise.trial_ends) >= new Date(new Date().toDateString());
  document.getElementById("page").innerHTML = `
    <div class="entete-page">
      <div><h1>Abonnement</h1>
      <p>${essai ? `Essai gratuit jusqu'au ${new Date(me.entreprise.trial_ends).toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}. ` : ""}
         Ce mois-ci : ${q.utilises} avis traités sur ${q.quota}${q.hors_quota ? `, ${q.hors_quota} hors quota` : ""}.</p></div>
    </div>
    <div class="formules">
      ${Object.entries(me.plans).map(([cle, p]) => `
        <section class="formule ${cle === me.entreprise.plan ? "actuelle" : ""}">
          <h2>${esc(p.nom)}</h2>
          <div class="prix">${p.prix} € <small>HT / mois</small></div>
          <ul>${p.atouts.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
          ${cle === me.entreprise.plan
            ? `<button class="bouton-clair" disabled>Votre formule actuelle</button>`
            : `<button class="${p.quota > me.plans[me.entreprise.plan].quota ? "bouton-etoile" : "bouton-clair"}" data-action="plan" data-plan="${cle}">Passer à ${esc(p.nom)}</button>`}
        </section>`).join("")}
    </div>
    <p class="discret" style="margin-top:1.25rem">Le quota compte les avis analysés et répondus sur le mois calendaire.
       Une partie est réservée aux avis de 1 et 2 étoiles pour qu'un client mécontent ne reste jamais sans réponse.
       En passant à une formule supérieure, les avis hors quota du mois sont traités immédiatement.</p>
    <p class="discret">Prix annuel : 2 mois offerts. Paiement en ligne à venir : dans cette version, le changement de formule est immédiat.</p>`;
}

// ---------------------------------------------------------------------------
// Paramètres
// ---------------------------------------------------------------------------
function pageParametres() {
  const e = etat.me.entreprise;
  const typeLib = { boulangerie: "Boulangerie", restaurant: "Restaurant", fleuriste: "Fleuriste", coiffeur: "Coiffeur", autre: "Autre commerce" };
  document.getElementById("page").innerHTML = `
    <div class="entete-page"><div><h1>Paramètres</h1><p>Compte : ${esc(etat.me.email)}</p></div></div>
    <div class="grille-2">
      <section class="bloc">
        <h2>Vos réponses</h2>
        <form data-form="reglages">
          <label for="p-nom">Nom de l'entreprise</label>
          <input id="p-nom" name="name" value="${esc(e.name)}" maxlength="80" required>
          <label for="p-type">Type de commerce</label>
          <select id="p-type" name="type">${etat.me.types.map((t) => `<option value="${t}" ${t === e.type ? "selected" : ""}>${typeLib[t] || t}</option>`).join("")}</select>
          <label for="p-ton">Ton des réponses</label>
          <select id="p-ton" name="ton">${etat.me.tons.map((t) => `<option value="${t}" ${t === e.ton ? "selected" : ""}>${t[0].toUpperCase() + t.slice(1)}</option>`).join("")}</select>
          <label for="p-sig">Signature</label>
          <input id="p-sig" name="signature" value="${esc(e.signature)}" maxlength="200" placeholder="L'équipe ${esc(e.name)}">
          <label for="p-contact">Contact proposé aux clients mécontents</label>
          <input id="p-contact" name="contact" value="${esc(e.contact)}" maxlength="120" placeholder="contact@votre-boutique.fr ou 04 94 00 00 00">
          <label class="case"><input type="checkbox" name="auto_publish" ${e.auto_publish ? "checked" : ""}>
            Publier automatiquement les réponses aux avis de 4 et 5 étoiles. Les avis de 3 étoiles ou moins attendent toujours votre validation.</label>
          <p class="erreur" id="erreur-form"></p>
          <button type="submit">Enregistrer</button>
        </form>
      </section>
      <section class="bloc">
        <h2>Source des avis</h2>
        <p>${enteteSource()}</p>
        <p class="discret">Moteur de rédaction : ${etat.me.ia === "claude" ? "Claude (IA)" : "règles intégrées (ajoutez une clé ANTHROPIC_API_KEY pour des réponses plus naturelles)"}.</p>
        <div class="actions">
          <button class="bouton-clair" data-action="synchroniser">Mettre à jour les avis</button>
          <a class="bouton bouton-clair" href="/auth/google/start">${e.mode === "google" ? "Changer de fiche Google" : "Connecter Google"}</a>
          <button class="bouton-clair" data-action="demo">Recharger la démo</button>
        </div>
        <p style="margin-top:1rem"><button class="bouton-lien" data-action="deconnecter-source">Déconnecter la source et effacer les avis importés</button></p>
      </section>
    </div>`;
}

// ---------------------------------------------------------------------------
// Actions (un seul écouteur pour tous les boutons)
// ---------------------------------------------------------------------------
const actions = {
  aller: (el) => { location.hash = el.dataset.cible; },

  async deconnexion() {
    await api("/api/logout", { methode: "POST" });
    location.hash = "#/connexion";
    router();
  },

  async demo(el) {
    if (etat.me.entreprise.mode !== "aucun" &&
        !confirm("Remplacer les avis actuels par des avis de démonstration ?")) return;
    el.disabled = true;
    el.textContent = "Préparation des avis…";
    const r = await api("/api/demo", { methode: "POST" });
    toast(`${r.avis} avis de démonstration chargés.`);
    location.hash = "#/dashboard";
    router();
  },

  async synchroniser(el) {
    el.disabled = true;
    const r = await api("/api/sync", { methode: "POST" });
    toast(!r.ajoutes ? "Vos avis sont à jour." : r.ajoutes === 1 ? "1 nouvel avis importé." : `${r.ajoutes} nouveaux avis importés.`);
    router();
  },

  async "deconnecter-source"() {
    if (!confirm("Déconnecter la source ? Les avis importés et les réponses en attente seront effacés d'AvisPilote (pas de Google).")) return;
    await api("/api/disconnect", { methode: "POST" });
    location.hash = "#/demarrage";
    router();
  },

  jours(el) { etat.jours = Number(el.dataset.jours); router(); },
  periode(el) { etat.periode = el.dataset.periode; router(); },
  filtre(el) { etat.filtre = el.dataset.filtre; etat.page = 1; etat.edition = null; location.hash = "#/avis"; router(); },
  page(el) { etat.page = Number(el.dataset.page); router(); window.scrollTo(0, 0); },
  modifier(el) { etat.edition = Number(el.dataset.id); rafraichirListe(); document.getElementById(`rep-${el.dataset.id}`)?.focus(); },
  "annuler-edition"() { etat.edition = null; rafraichirListe(); },

  async publier(el) {
    const id = Number(el.dataset.id);
    const texte = document.getElementById(`rep-${id}`).value;
    el.disabled = true;
    try {
      const r = await api(`/api/reviews/${id}/publish`, { methode: "POST", corps: { reply: texte } });
      etat.edition = null;
      toast(etat.me.entreprise.mode === "google" ? "Réponse publiée sur Google." : "Réponse publiée (démo : rien n'est envoyé à Google).");
      if (etat.filtre === "a_valider") {
        etat.avis = etat.avis.filter((a) => a.id !== id);
        etat.listeInfos.compteurs.a_valider -= 1;
        await chargerMe();
        router();
      } else {
        etat.avis = etat.avis.map((a) => (a.id === id ? r.avis : a));
        rafraichirListe();
      }
    } catch (e) {
      el.disabled = false;
      toast(e.message, true);
    }
  },

  async regenerer(el) {
    const id = Number(el.dataset.id);
    el.disabled = true;
    const r = await api(`/api/reviews/${id}/regenerate`, { methode: "POST" });
    document.getElementById(`rep-${id}`).value = r.reply;
    el.disabled = false;
  },

  async plan(el) {
    el.disabled = true;
    const r = await api("/api/business/plan", { methode: "POST", corps: { plan: el.dataset.plan } });
    await chargerMe();
    toast(`Formule ${etat.me.entreprise.plan_nom} activée.` + (r.traites ? ` ${r.traites} avis en attente ont été traités.` : ""));
    router();
  },
};

document.addEventListener("click", async (evenement) => {
  const el = evenement.target.closest("[data-action]");
  if (!el || !actions[el.dataset.action]) return;
  evenement.preventDefault();
  try {
    await actions[el.dataset.action](el);
  } catch (e) {
    el.disabled = false;
    toast(e.message, true);
  }
});

document.addEventListener("submit", async (evenement) => {
  const form = evenement.target;
  evenement.preventDefault();
  if (form.dataset.form === "connexion" || form.dataset.form === "inscription") return soumettreAuth(form);
  if (form.dataset.form === "reglages") {
    const donnees = Object.fromEntries(new FormData(form));
    donnees.auto_publish = form.elements.auto_publish.checked;
    try {
      await api("/api/business/settings", { methode: "POST", corps: donnees });
      toast("Paramètres enregistrés.");
      router();
    } catch (e) {
      document.getElementById("erreur-form").textContent = e.message;
    }
  }
});

window.addEventListener("hashchange", router);
router();
