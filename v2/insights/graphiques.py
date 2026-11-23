"""Calcul de la géométrie des graphiques (SVG dessiné par les gabarits Django).

Pourquoi du SVG généré côté serveur plutôt qu'une bibliothèque JS ?
- aucune dépendance externe (la CSP n'autorise que nos propres scripts) ;
- les textes passent par l'échappement automatique des gabarits (pas de XSS) ;
- le graphique s'affiche même sans JavaScript ; le petit script ne fait que l'info-bulle.

Règles de dessin (guide dataviz) : barres ≤ 24 px, bout arrondi de 4 px, 2 px d'espace
entre segments empilés, lignes de 2 px, grille fine et discrète, un seul axe.
"""
import math

LARGEUR, HAUTEUR = 640, 220
MARGE_G, MARGE_D, MARGE_H, MARGE_B = 34, 40, 14, 26


def _virgule(nombre, decimales=2):
    return f"{nombre:.{decimales}f}".replace(".", ",")


def _pas_propre(maximum, nb_graduations=4):
    if maximum <= 0:
        return 1
    brut = maximum / nb_graduations
    puissance = 10 ** math.floor(math.log10(brut))
    for m in (1, 2, 5, 10):
        if brut <= m * puissance:
            return max(1, int(m * puissance))
    return int(10 * puissance)


def _colonne_arrondie(x, y, l, h, r=4):
    """Chemin d'une barre arrondie en haut, carrée en bas."""
    r = min(r, h, l / 2)
    return (f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
            f"H{x + l - r:.1f} Q{x + l:.1f},{y:.1f} {x + l:.1f},{y + r:.1f} V{y + h:.1f} Z")


def _etiquettes_x(points, cle_x="cx"):
    """Au plus ~7 libellés sur l'axe X, toujours le dernier."""
    n = len(points)
    pas = max(1, math.ceil(n / 6))
    indices = [i for i in range(n) if i % pas == 0]
    if indices and indices[-1] != n - 1:
        if n - 1 - indices[-1] < pas:
            indices[-1] = n - 1  # le dernier remplace l'avant-dernier trop proche (pas de chevauchement)
        else:
            indices.append(n - 1)
    return [points[i] for i in indices]


def colonnes_empilees(series):
    """Nombre d'avis par période, empilé : positifs (bas), neutres, négatifs (haut)."""
    n = len(series)
    zone_l = LARGEUR - MARGE_G - MARGE_D
    zone_h = HAUTEUR - MARGE_H - MARGE_B
    bande = zone_l / max(n, 1)
    l = min(24, bande * 0.7)
    maximum = max([s["total"] for s in series] + [1])
    pas = _pas_propre(maximum)
    haut = pas * math.ceil(maximum / pas)
    echelle = zone_h / haut
    base = MARGE_H + zone_h

    colonnes = []
    for i, s in enumerate(series):
        x = MARGE_G + i * bande + (bande - l) / 2
        segments, y = [], base
        empiles = [(k, s[k]) for k in ("positifs", "neutres", "negatifs") if s[k]]
        for j, (cle, valeur) in enumerate(empiles):
            h = valeur * echelle
            dernier = j == len(empiles) - 1
            espace = 0 if j == 0 else 2  # 2 px de surface entre deux segments
            hauteur = max(h - espace, 1)
            y_haut = y - h
            if dernier:
                chemin = _colonne_arrondie(x, y_haut, l, hauteur)
            else:
                chemin = f"M{x:.1f},{y_haut + hauteur:.1f} V{y_haut:.1f} H{x + l:.1f} V{y_haut + hauteur:.1f} Z"
            segments.append({"classe": cle, "d": chemin})
            y = y_haut
        info = f"{s['libelle']} : {s['total']} avis — {s['positifs']} positifs, {s['neutres']} neutres, {s['negatifs']} négatifs"
        colonnes.append({"segments": segments, "cx": x + l / 2, "libelle": s["libelle"], "info": info,
                         "cible_x": MARGE_G + i * bande, "cible_l": bande})
    graduations = [{"y": base - v * echelle, "valeur": v} for v in range(0, haut + 1, pas)]
    return {"largeur": LARGEUR, "hauteur": HAUTEUR, "colonnes": colonnes, "graduations": graduations,
            "axe_x": _etiquettes_x(colonnes), "base": base, "x0": MARGE_G, "x1": LARGEUR - MARGE_D,
            "haut_zone": MARGE_H, "vide": all(s["total"] == 0 for s in series), **_reperes(base)}


def courbe_note(series):
    """Note moyenne cumulée (une seule série : pas de légende, le titre la nomme)."""
    points_valides = [s for s in series if s["note_cumulee"] is not None]
    if not points_valides:
        return {"vide": True}
    n = len(series)
    zone_l = LARGEUR - MARGE_G - MARGE_D
    zone_h = HAUTEUR - MARGE_H - MARGE_B
    notes = [s["note_cumulee"] for s in points_valides]
    bas = max(1.0, math.floor((min(notes) - 0.2) * 2) / 2)
    haut = 5.0
    if haut - bas < 1:
        bas = haut - 1
    bande = zone_l / max(n, 1)

    def px(i):
        return MARGE_G + i * bande + bande / 2

    def py(v):
        return MARGE_H + (haut - v) / (haut - bas) * zone_h

    points, cibles = [], []
    for i, s in enumerate(series):
        if s["note_cumulee"] is None:
            continue
        points.append({"cx": px(i), "cy": py(s["note_cumulee"]), "libelle": s["libelle"]})
        cibles.append({"x": MARGE_G + i * bande, "l": bande, "cx": px(i),
                       "info": f"{s['libelle']} : note moyenne {_virgule(s['note_cumulee'])} ★ ({s['total']} avis reçus)"})
    chemin = "M" + " L".join(f"{p['cx']:.1f},{p['cy']:.1f}" for p in points)
    nb_grad = int(round((haut - bas) / 0.5))
    graduations = [{"y": py(bas + k * 0.5), "valeur": f"{bas + k * 0.5:.1f}".replace(".", ",")}
                   for k in range(nb_grad + 1)]
    fin = points[-1]
    return {"vide": False, "largeur": LARGEUR, "hauteur": HAUTEUR, "chemin": chemin, "fin": fin,
            "valeur_fin": f"{points_valides[-1]['note_cumulee']:.2f}".replace(".", ","), "graduations": graduations,
            "cibles": cibles, "axe_x": _etiquettes_x(points), "base": MARGE_H + zone_h,
            "x0": MARGE_G, "x1": LARGEUR - MARGE_D, "haut_zone": MARGE_H, "x_valeur_fin": fin["cx"] + 8,
            **_reperes(MARGE_H + zone_h)}


def barres_etoiles(repartition):
    """Répartition 5★ → 1★ en barres horizontales, valeur au bout de la barre."""
    largeur, hauteur_ligne, gauche, droite = 320, 28, 34, 48
    total = sum(r["nombre"] for r in repartition) or 1
    maximum = max(r["nombre"] for r in repartition) or 1
    zone = largeur - gauche - droite
    lignes = []
    for i, r in enumerate(repartition):
        l = r["nombre"] / maximum * zone
        y = i * hauteur_ligne + 6
        lignes.append({
            "y": y, "texte_y": y + 12, "etoiles": r["etoiles"], "nombre": r["nombre"],
            "part": round(100 * r["nombre"] / total),
            "d": _barre_horizontale(gauche, y, max(l, 0), 16) if l > 0 else "",
            "valeur_x": gauche + l + 6,
        })
    return {"largeur": largeur, "hauteur": len(repartition) * hauteur_ligne + 4, "lignes": lignes, "x0": gauche,
            "x_etiquettes": gauche - 8}


def _reperes(base):
    """Positions des textes d'axes (calculées ici : les gabarits Django ne font pas de calcul)."""
    return {"x_graduations": MARGE_G - 6, "y_axe_x": HAUTEUR - 6, "hauteur_zone": base - MARGE_H}


def _barre_horizontale(x, y, l, h, r=4):
    r = min(r, l, h / 2)
    return (f"M{x:.1f},{y:.1f} H{x + l - r:.1f} Q{x + l:.1f},{y:.1f} {x + l:.1f},{y + r:.1f} "
            f"V{y + h - r:.1f} Q{x + l:.1f},{y + h:.1f} {x + l - r:.1f},{y + h:.1f} H{x:.1f} Z")
