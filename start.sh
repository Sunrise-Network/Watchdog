#!/bin/bash

set -euo pipefail  # Arrête le script en cas d'erreur et si des variables non définies sont utilisées

# Configuration
CONTAINER_NAME="le69iste"
IMAGE_NAME="le69iste"
ENV_FILE=".env"
DOCKER_NETWORK="le69iste_network"
HEALTHCHECK_TIMEOUT=30  # Timeout en secondes pour le healthcheck
BACKUP_DIR="./backups"
LOG_FILE="deployment.log"

# Fonction pour afficher et logger les messages
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "${timestamp} - $1" | tee -a "${LOG_FILE}"
}

# Fonction de nettoyage en cas d'erreur
cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log "❌ Une erreur est survenue (code: ${exit_code}). Nettoyage en cours..."
        if [ "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
            docker stop "$CONTAINER_NAME" 2>/dev/null || true
            docker rm "$CONTAINER_NAME" 2>/dev/null || true
        fi
    fi
    exit $exit_code
}

trap cleanup EXIT

# Vérification des prérequis
check_prerequisites() {
    local prerequisites=("docker" "git" "curl")
    
    for cmd in "${prerequisites[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log "❌ $cmd n'est pas détecté sur votre système. Veuillez l'installer et réessayer."
            exit 1
        fi
    done
    
    if [ ! -f "$ENV_FILE" ]; then
        log "❌ Le fichier $ENV_FILE n'existe pas."
        exit 1
    fi
}

# Création du réseau Docker s'il n'existe pas
create_network() {
    if ! docker network inspect "$DOCKER_NETWORK" &>/dev/null; then
        log "🌐 Création du réseau Docker $DOCKER_NETWORK"
        docker network create "$DOCKER_NETWORK" || { log "❌ Échec de la création du réseau"; exit 1; }
    fi
}

# Sauvegarde des données si nécessaire
backup_data() {
    if [ "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
        mkdir -p "$BACKUP_DIR"
        local backup_file="${BACKUP_DIR}/backup_$(date +%Y%m%d_%H%M%S).tar"
        log "💾 Création d'une sauvegarde dans $backup_file"
        docker exec "$CONTAINER_NAME" tar czf - /app/data > "$backup_file" || true
    fi
}

# Mise à jour du code
update_code() {
    log "📥 Mise à jour du code depuis GitHub"
    git fetch --all || { log "❌ Échec du fetch Git"; exit 1; }
    
    local current_branch=$(git branch --show-current)
    git pull origin "$current_branch" || { log "❌ Échec du pull Git"; exit 1; }
}

# Gestion du conteneur existant
handle_existing_container() {
    if [ "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
        log "🛑 Arrêt du conteneur $CONTAINER_NAME"
        docker stop "$CONTAINER_NAME" || { log "❌ Échec de l'arrêt du conteneur"; exit 1; }
    fi
    
    if [ "$(docker ps -aq -f name=$CONTAINER_NAME)" ]; then
        log "🗑️ Suppression du conteneur $CONTAINER_NAME"
        docker rm "$CONTAINER_NAME" || { log "❌ Échec de la suppression du conteneur"; exit 1; }
    fi
}

# Construction et démarrage du nouveau conteneur
deploy_container() {
    log "🏗️ Construction de l'image Docker $IMAGE_NAME"
    docker build \
        --pull \
        --no-cache \
        -t "$IMAGE_NAME" . || { log "❌ Échec de la construction"; exit 1; }

    log "🚀 Démarrage du conteneur $CONTAINER_NAME"
    docker run -d \
        --name "$CONTAINER_NAME" \
        --env-file "$ENV_FILE" \
        --network "$DOCKER_NETWORK" \
        --restart unless-stopped \
        -v "${PWD}/data:/app/data" \
        --health-cmd="curl -f http://localhost:3000/health || exit 1" \
        --health-interval=30s \
        --health-timeout=10s \
        --health-retries=3 \
        "$IMAGE_NAME" || { log "❌ Échec du démarrage"; exit 1; }
}

# Vérification de la santé du conteneur
check_container_health() {
    log "🏥 Vérification de la santé du conteneur"
    local timeout_counter=0
    while [ $timeout_counter -lt $HEALTHCHECK_TIMEOUT ]; do
        if [ "$(docker inspect --format='{{.State.Health.Status}}' $CONTAINER_NAME)" = "healthy" ]; then
            log "✅ Le conteneur est en bonne santé"
            return 0
        fi
        sleep 1
        ((timeout_counter++))
    done
    log "❌ Le conteneur n'a pas passé le healthcheck dans le délai imparti"
    return 1
}

# Exécution principale
main() {
    log "🚀 Début du déploiement"
    
    check_prerequisites
    create_network
    backup_data
    update_code
    handle_existing_container
    deploy_container
    
    log "✅ Déploiement terminé avec succès"
}

main