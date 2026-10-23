"""Appelle l'agent RiskPilot publié dans Microsoft Foundry depuis Python.

Prérequis :
    pip install -r agent/requirements.txt
    az login

Le point de terminaison se trouve sur la page d'accueil du projet Foundry. Il a la forme :
https://<ressource>.services.ai.azure.com/api/projects/<projet>
"""
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

POINT_DE_TERMINAISON = "https://VOTRE-RESSOURCE.services.ai.azure.com/api/projects/proj-riskpilot"
NOM_AGENT = "riskpilot-fmm"

projet = AIProjectClient(endpoint=POINT_DE_TERMINAISON, credential=DefaultAzureCredential())

# Client relié à l'agent : instructions, outils, fichiers et garde-fou sont ceux du portail
client = projet.get_openai_client(agent_name=NOM_AGENT)
conversation = client.conversations.create()

reponse = client.responses.create(
    conversation=conversation.id,
    input="Rédige la note de risque du jour du Fonds Mosaïque Moselle.",
)
print(reponse.output_text)

# Question de suivi dans la même conversation : l'agent garde le contexte
suite = client.responses.create(
    conversation=conversation.id,
    input="Quelle position faudrait-il réduire en priorité pour faire baisser la VaR, et pourquoi ?",
)
print(suite.output_text)
