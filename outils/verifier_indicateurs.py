"""Recalcule tous les indicateurs de risque du Fonds Mosaïque Moselle, sans IA.

Ce script applique exactement les méthodes de l'article 2 de la politique de risque.
Il produit les résultats de référence auxquels l'agent RiskPilot est comparé :
VaR historique et paramétrique, Expected Shortfall, VaR 10 jours, contributions
d'Euler, stress tests, backtesting avec test de Kupiec, et simulation de réduction.

Utilisation, depuis la racine du dépôt :
    pip install numpy pandas scipy
    python outils/verifier_indicateurs.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

DOSSIER = Path(__file__).resolve().parent.parent / "donnees"
Z_99 = 2.3263          # quantile de la loi normale à 99 %
FENETRE = 500          # jours de P&L utilisés (article 2)
BACKTEST = 250         # jours testés (article 5)


def euros(x: float) -> str:
    """Format français : espace pour les milliers, arrondi à l'euro."""
    return f"{x:,.0f} €".replace(",", " ")


def pct(x: float) -> str:
    return f"{x:.2f} %".replace(".", ",")


def statut(valeur: float, alerte: float, limite: float) -> str:
    """Statuts de l'article 3 : CONFORME, ALERTE ou DÉPASSEMENT."""
    if valeur > limite:
        return "DÉPASSEMENT"
    if valeur >= alerte:
        return "ALERTE"
    return "CONFORME"


def var_historique(pnl: np.ndarray) -> float:
    """5e plus forte perte sur 500 jours (statistique d'ordre, sans interpolation)."""
    return np.sort(-pnl)[::-1][4]


positions = pd.read_csv(DOSSIER / "positions_portefeuille.csv")
cours = pd.read_csv(DOSSIER / "prix_historiques.csv")
scenarios = pd.read_csv(DOSSIER / "scenarios_stress.csv")

codes = list(positions.code_actif)
valeurs = positions.valeur_marche_eur.to_numpy(dtype=float)
actif_net = valeurs.sum()

# P&L hypothétique : portefeuille du jour appliqué aux rendements arithmétiques passés
rendements = cours[codes].pct_change().dropna().to_numpy()
pnl = rendements @ valeurs
fenetre = pnl[-FENETRE:]
pertes_triees = np.sort(-fenetre)[::-1]

var_h = var_historique(fenetre)
es = pertes_triees[:12].mean()
ecart_type = fenetre.std(ddof=1)
var_p = Z_99 * ecart_type
var_10 = var_h * np.sqrt(10)

print("=" * 72)
print(f"FONDS MOSAÏQUE MOSELLE · actif net {euros(actif_net)} · données au {cours.date.iloc[-1]}")
print("=" * 72)
print("\nINDICATEURS (article 2) ET STATUTS (article 3)")
print(f"  VaR historique 99 % 1 jour   {euros(var_h):>14}  {pct(var_h / actif_net * 100):>8}  {statut(var_h / actif_net * 100, 1.8, 2.0)}")
print(f"  Expected Shortfall 97,5 %    {euros(es):>14}  {pct(es / actif_net * 100):>8}  {statut(es / actif_net * 100, 2.25, 2.5)}")
print(f"  VaR paramétrique 99 %        {euros(var_p):>14}  {pct(var_p / actif_net * 100):>8}  contrôle")
print(f"  VaR historique 10 jours      {euros(var_10):>14}  {pct(var_10 / actif_net * 100):>8}  information")
print(f"  Écart historique / paramétrique : +{(var_h / var_p - 1) * 100:.1f} % (queues épaisses)".replace(".", ","))

# Contributions d'Euler sur la VaR paramétrique
covariance = np.cov(rendements[-FENETRE:].T, ddof=1)
sigma_portefeuille = np.sqrt(valeurs @ covariance @ valeurs)
contributions = Z_99 * valeurs * (covariance @ valeurs) / sigma_portefeuille
print("\nCONTRIBUTIONS D'EULER À LA VaR PARAMÉTRIQUE")
for code, c in sorted(zip(codes, contributions), key=lambda x: -x[1]):
    print(f"  {code:<8} {euros(c):>12}  {c / contributions.sum() * 100:>6.1f} %".replace(".", ","))
print(f"  Somme    {euros(contributions.sum()):>12}  (égale à la VaR paramétrique)")

# Stress tests (article 4)
print("\nSTRESS TESTS (article 4, limite 16 %, alerte 14 %)")
for _, s in scenarios.iterrows():
    total = 0.0
    for _, p in positions.iterrows():
        v, d, f = p.valeur_marche_eur, p.duration_modifiee, p.facteur_stress
        if f == "actions_dev":
            total += v * s.choc_actions_dev_pct / 100
        elif f == "actions_em":
            total += v * s.choc_actions_em_pct / 100
        elif f == "taux":
            total += -d * v * s.choc_taux_pb / 10_000
        elif f == "credit_ig":
            total += -d * v * (s.choc_taux_pb + s.choc_spread_ig_pb) / 10_000
        elif f == "credit_hy":
            total += -d * v * (s.choc_taux_pb + s.choc_spread_hy_pb) / 10_000
        elif f == "or":
            total += v * s.choc_or_pct / 100
        elif f == "immo":
            total += v * s.choc_immo_pct / 100
    perte_pct = max(-total, 0) / actif_net * 100
    print(f"  {s.code_scenario} {s.libelle:<48} {euros(total):>14}  {pct(total / actif_net * 100):>9}  {statut(perte_pct, 14, 16)}")

# Backtesting (article 5) et test de Kupiec
exceptions = []
for t in range(len(pnl) - BACKTEST, len(pnl)):
    seuil = var_historique(pnl[t - FENETRE:t])
    if -pnl[t] > seuil:
        exceptions.append((cours.date.iloc[t + 1], -pnl[t], seuil))
x, n, p = len(exceptions), BACKTEST, 0.01
taux = x / n
lr = -2 * ((n - x) * np.log(1 - p) + x * np.log(p) - ((n - x) * np.log(1 - taux) + x * np.log(taux)))
zone = "verte" if x <= 4 else ("orange" if x <= 9 else "rouge")
print(f"\nBACKTESTING (article 5) : {x} exceptions sur {n} jours, {n * p:.1f} attendues, zone {zone}".replace(".", ","))
for date, perte, seuil in exceptions:
    print(f"  {date}  perte {euros(perte):>12}  VaR de la veille {euros(seuil):>12}")
print(f"  Test de Kupiec : statistique {lr:.2f}, p-valeur {1 - chi2.cdf(lr, 1):.3f}".replace(".", ","))

# Simulation : montant à transférer vers le monétaire pour passer sous le seuil d'alerte
print("\nSIMULATION : TRANSFERT VERS MONET POUR RAMENER LA VaR SOUS 1,8 %")
for source in ["ACT_EU", "ACT_US"]:
    i, j = codes.index(source), codes.index("MONET")
    for montant in range(0, int(valeurs[i]) + 1, 250_000):
        v = valeurs.copy()
        v[i] -= montant
        v[j] += montant
        nouvelle = var_historique(rendements[-FENETRE:] @ v)
        if nouvelle < 0.018 * actif_net:
            print(f"  {source} vers MONET : {euros(montant)} suffisent, VaR {pct(nouvelle / actif_net * 100)}")
            break
