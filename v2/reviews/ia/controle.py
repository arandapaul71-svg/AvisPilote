"""Contrôle qualité des réponses AVANT publication.

Une réponse qui échoue à un contrôle n'est jamais publiée automatiquement :
elle passe en « à valider » avec la liste des problèmes trouvés.
"""
import re
from difflib import SequenceMatcher

from .regles import normaliser

SEUIL_SIMILARITE = 0.85
LONGUEUR_MAX = 1500

# Formulations que l'IA ne doit jamais employer seule (cahier des charges) :
# promesse de remboursement / geste, aveu de faute non vérifiée, problème « résolu ».
INTERDITS_SYSTEME = {
    "promesse": [r"\brembours", r"\bgeste commercial", r"\bavoir\b", r"\boffert", r"\bgratuit",
                 r"\bdedommag", r"\bbon d.achat", r"\bremise\b", r"\breduction\b"],
    "aveu": [r"nous reconnaissons (notre|nos) (erreur|faute|tort)", r"c.est (entierement |totalement )?(de )?notre faute",
             r"nous avons (commis|fait) une (erreur|faute)", r"nous sommes (seuls )?responsables"],
    "resolu": [r"(le )?probleme (est|a ete) (regle|resolu|corrige)", r"c.est (desormais |maintenant )?regle",
               r"nous avons (deja )?(regle|resolu|corrige) (le|ce) probleme", r"cela ne se reproduira plus"],
}
ENTHOUSIASME = [r"ravi", r"super retour", r"quel plaisir", r"merci pour ce (super|joli|beau)", r"vous nous faites notre journee"]
MOTS_VIDES = set("""avec dans pour mais plus tres bien sans cette comme nous vous elle elles ils sont etait etre
avoir fait faire tout tous toute toutes alors aussi encore merci bonjour votre notre leurs leur quand""".split())
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def _mots(texte):
    return {m for m in re.findall(r"[a-z]{5,}", normaliser(texte)) if m not in MOTS_VIDES}


RACINES_THEMES = {
    "accueil": ["accueil", "equipe"], "prix": ["prix", "tarif"], "attente": ["attente", "rapidite", "delai"],
    "qualite": ["produit", "cuisine", "composition", "prestation", "qualite", "sejour", "travail", "pain", "plat"],
    "proprete": ["proprete"], "choix": ["choix"], "cadre": ["cadre", "ambiance"], "livraison": ["livraison"],
}


def controler(reponse, avis, reglages, reponses_precedentes=(), themes=()):
    """Renvoie la liste des problèmes (liste vide = réponse publiable automatiquement).
    `themes` : thèmes repérés dans l'avis ; une réponse qui en parle n'est pas générique."""
    problemes = []
    texte = normaliser(reponse)
    if not reponse.strip():
        return ["Réponse vide."]
    if len(reponse) > LONGUEUR_MAX:
        problemes.append("Réponse trop longue.")

    for categorie, motifs in INTERDITS_SYSTEME.items():
        if any(re.search(m, texte) for m in motifs):
            problemes.append({
                "promesse": "Promet un remboursement, un geste ou une réduction : à décider par toi.",
                "aveu": "Reconnaît une faute qui n'est pas confirmée.",
                "resolu": "Affirme que le problème est réglé sans information vérifiée.",
            }[categorie])

    for expression in filter(None, (e.strip() for e in (reglages.forbidden_phrases or "").splitlines())):
        if normaliser(expression) in texte:
            problemes.append(f"Contient une expression interdite : « {expression} ».")

    if not reglages.emojis and EMOJI_RE.search(reponse):
        problemes.append("Contient des émojis alors qu'ils sont désactivés.")

    if avis.stars <= 2 and any(re.search(m, texte) for m in ENTHOUSIASME):
        problemes.append("Ton trop enthousiaste pour un avis négatif.")

    # Réponse générique : l'avis a du contenu mais la réponse ne reprend ni ses mots ni ses thèmes.
    mots_avis = _mots(avis.comment)
    parle_d_un_theme = any(r in texte for t in themes for r in RACINES_THEMES.get(t, []))
    if len(mots_avis) >= 4 and not (mots_avis & _mots(reponse)) and not parle_d_un_theme:
        problemes.append("Réponse générique : elle ne reprend rien de ce que dit le client.")

    for precedente in reponses_precedentes:
        if SequenceMatcher(None, texte, normaliser(precedente)).ratio() >= SEUIL_SIMILARITE:
            problemes.append("Trop proche d'une réponse déjà publiée.")
            break
    return problemes
