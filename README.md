# Watchdog

Watchdog est un bot Discord de modération automatique qui utilise MistralAI pour analyser les messages et détecter les contenus inappropriés. Il peut signaler et supprimer les messages contenant des violations telles que le contenu sexuel, la haine et la discrimination, la violence et les menaces, le contenu dangereux et criminel, l'auto-mutilation, et la divulgation d'informations personnelles.

## Fonctionnalités

- Détection automatique des contenus inappropriés dans les messages.
- Suppression des messages violant les règles et notification des modérateurs.

## Prérequis

- Docker
- Un token Discord valide
- Une clé API Mistral

## Installation

1. Clonez ce dépôt :
    ```sh
    git clone https://github.com/Sunrise-Network/Watchdog.git
    cd Watchdog
    ```

2. Créez un fichier [.env](http://_vscodecontentref_/0) à la racine du projet et ajoutez les variables d'environnement suivantes :
    ```env
    DISCORD_TOKEN=<votre_token_discord>
    MISTRAL_API_KEY=<votre_cle_api_mistral>
    MOD_ROLE_ID=<id_du_role_de_moderation_par_defaut>
    MOD_CHANNEL_ID=<id_du_salon_de_moderation_par_defaut>
    BOT_NAME=ModBot
    BOT_VERSION=1.0.0
    ```

## Utilisation avec Docker

1. Construisez l'image Docker :
    ```sh
    docker build -t watchdog .
    ```

2. Lancez le conteneur Docker :
    ```sh
    docker run -d --name watchdog --env-file .env watchdog
    ```

## Commandes du Bot

- `!set_mod_role <@role>` : Configure le rôle de modérateur pour le serveur.
- `!set_mod_channel <#salon>` : Configure le salon de modération pour le serveur.
- `!show_config` : Affiche la configuration actuelle du serveur.
- `!say_safe <message>` : Envoie un message qui ne sera pas modéré par le bot.

## Contribuer

Les contributions sont les bienvenues ! Veuillez soumettre une pull request ou ouvrir une issue pour discuter des changements que vous souhaitez apporter.

## Licence

Ce projet est sous licence CC BY-NC-ND 4.0. Voir le fichier [LICENSE](license.md) pour plus de détails.
