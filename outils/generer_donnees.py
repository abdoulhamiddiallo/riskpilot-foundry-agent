"""Génère les trois fichiers de données du Fonds Mosaïque Moselle (fonds fictif).

Le portefeuille compte 10 positions pour 50 000 000 €. Les cours sont simulés sur
1 000 jours ouvrés avec des corrélations réalistes entre classes d'actifs, des
queues épaisses (loi de Student à 5 degrés de liberté) et deux épisodes de tension,
dont un récent, présent dans la fenêtre de backtesting. La graine est fixée :
chaque exécution reproduit exactement les fichiers du dossier donnees/.

Utilisation, depuis la racine du dépôt :
    python outils/generer_donnees.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

DOSSIER = Path(__file__).resolve().parent.parent / "donnees"
ACTIF_NET = 50_000_000
generateur = np.random.default_rng(16)

# 1. Positions du jour
positions = pd.DataFrame(
    [
        ("ACT_EU", "Actions zone euro (indice large)", "Actions", "EUR", 9_000_000, "actions_dev", 0.0),
        ("ACT_US", "Actions États-Unis (indice large, en euros)", "Actions", "EUR", 8_000_000, "actions_dev", 0.0),
        ("ACT_EM", "Actions marchés émergents", "Actions", "EUR", 3_500_000, "actions_em", 0.0),
        ("OAT_10", "Obligations d'État françaises 7-10 ans", "Taux souverains", "EUR", 7_000_000, "taux", 8.1),
        ("BUND_5", "Obligations d'État allemandes 3-5 ans", "Taux souverains", "EUR", 4_000_000, "taux", 4.2),
        ("CRED_IG", "Crédit entreprises euro Investment Grade", "Crédit", "EUR", 6_000_000, "credit_ig", 4.8),
        ("CRED_HY", "Crédit entreprises euro haut rendement", "Crédit", "EUR", 3_000_000, "credit_hy", 3.2),
        ("OR", "Or physique", "Matières premières", "EUR", 3_500_000, "or", 0.0),
        ("IMMO", "Foncières cotées Europe", "Immobilier", "EUR", 2_500_000, "immo", 0.0),
        ("MONET", "Fonds monétaire euro", "Monétaire", "EUR", 3_500_000, "monetaire", 0.0),
    ],
    columns=["code_actif", "libelle", "classe_actif", "devise", "valeur_marche_eur", "facteur_stress", "duration_modifiee"],
)
positions["poids_pct"] = (positions.valeur_marche_eur / ACTIF_NET * 100).round(2)
assert positions.valeur_marche_eur.sum() == ACTIF_NET
codes = list(positions.code_actif)

# 2. Volatilités annuelles et matrice de corrélation
volatilites = np.array([0.18, 0.17, 0.20, 0.065, 0.035, 0.045, 0.07, 0.15, 0.22, 0.003]) / np.sqrt(252)
correlations = np.array([
    # EU    US    EM    OAT   BUND  IG    HY    OR    IMMO  MON
    [1.00, 0.75, 0.65, -0.20, -0.30, 0.10, 0.55, 0.05, 0.70, 0],
    [0.75, 1.00, 0.60, -0.20, -0.25, 0.05, 0.50, 0.05, 0.55, 0],
    [0.65, 0.60, 1.00, -0.10, -0.15, 0.10, 0.50, 0.20, 0.50, 0],
    [-0.20, -0.20, -0.10, 1.00, 0.80, 0.65, 0.10, 0.15, -0.05, 0],
    [-0.30, -0.25, -0.15, 0.80, 1.00, 0.60, 0.00, 0.20, -0.15, 0],
    [0.10, 0.05, 0.10, 0.65, 0.60, 1.00, 0.45, 0.10, 0.15, 0],
    [0.55, 0.50, 0.50, 0.10, 0.00, 0.45, 1.00, 0.05, 0.50, 0],
    [0.05, 0.05, 0.20, 0.15, 0.20, 0.10, 0.05, 1.00, 0.05, 0],
    [0.70, 0.55, 0.50, -0.05, -0.15, 0.15, 0.50, 0.05, 1.00, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 1.00],
])
cholesky = np.linalg.cholesky(correlations)

# 3. Calendrier et épisodes de tension (volatilité multipliée, dérive baissière des actifs risqués)
dates = pd.bdate_range(end="2026-10-22", periods=1000)
nb_jours = len(dates) - 1
multiplicateur = np.ones(nb_jours)
derive = np.zeros(nb_jours)
for debut, fin, facteur in [(170, 215, 2.6), (800, 835, 3.1)]:
    multiplicateur[debut:fin] = facteur
    derive[debut:fin] = -0.0022

# 4. Rendements corrélés à queues épaisses (Student, 5 degrés de liberté)
degres = 5
gaussiens = generateur.standard_normal((nb_jours, 10)) @ cholesky.T
khi_deux = generateur.chisquare(degres, (nb_jours, 1))
student = gaussiens / np.sqrt(khi_deux / degres) * np.sqrt((degres - 2) / degres)
rendements_moyens = np.array([0.07, 0.08, 0.06, 0.02, 0.015, 0.03, 0.045, 0.05, 0.05, 0.025]) / 252
rendements = rendements_moyens + student * volatilites * multiplicateur[:, None]
actifs_risques = [0, 1, 2, 6, 8]
rendements[:, actifs_risques] += derive[:, None] * np.array([1, 1, 1.1, 0.5, 1.2])
rendements[:, [3, 4]] -= derive[:, None] * 0.15  # effet valeur refuge des emprunts d'État
rendements[:, 9] = 0.025 / 252 + generateur.normal(0, 0.00002, nb_jours)

# 5. Calage des niveaux finaux sur des ordres de grandeur réalistes (base 100)
niveaux_cibles = np.array([128, 141, 112, 96, 98, 106, 114, 178, 104, 110.5])
niveaux_bruts = np.prod(1 + rendements, axis=0) * 100
correction = (niveaux_cibles / niveaux_bruts) ** (1 / nb_jours)
rendements = (1 + rendements) * correction - 1
prix = np.vstack([np.full(10, 100.0), 100.0 * np.cumprod(1 + rendements, axis=0)])

cours = pd.DataFrame(prix.round(4), columns=codes)
cours.insert(0, "date", dates.strftime("%Y-%m-%d"))

# 6. Scénarios de stress (chocs instantanés)
scenarios = pd.DataFrame(
    [
        ("S1", "Krach actions (type 2008)", -35, -40, -100, 150, 600, 10, -40),
        ("S2", "Choc d'inflation et de taux (type 2022)", -20, -22, 250, 80, 250, -5, -30),
        ("S3", "Crise des dettes souveraines euro (type 2011)", -25, -15, 120, 120, 400, 15, -25),
        ("S4", "Pandémie et arrêt économique (type mars 2020)", -33, -30, -50, 180, 550, -3, -38),
        ("S5", "Atterrissage en douceur (scénario favorable)", 12, 10, -75, -30, -100, 4, 10),
    ],
    columns=["code_scenario", "libelle", "choc_actions_dev_pct", "choc_actions_em_pct", "choc_taux_pb",
             "choc_spread_ig_pb", "choc_spread_hy_pb", "choc_or_pct", "choc_immo_pct"],
)

DOSSIER.mkdir(exist_ok=True)
positions.to_csv(DOSSIER / "positions_portefeuille.csv", index=False)
cours.to_csv(DOSSIER / "prix_historiques.csv", index=False)
scenarios.to_csv(DOSSIER / "scenarios_stress.csv", index=False)
print(f"Données générées dans {DOSSIER} : {len(positions)} positions, {len(cours)} jours de cours, {len(scenarios)} scénarios.")
