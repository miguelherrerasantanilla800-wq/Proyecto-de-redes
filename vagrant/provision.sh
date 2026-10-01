#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="${1:?Debe indicarse el servicio de esta VM}"
PROJECT_DIR=/vagrant
DATABASE_IP=192.168.56.20
AUTH_IP=192.168.56.21
BANK_IP=192.168.56.22

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo "Falta $PROJECT_DIR/.env. Crea .env a partir de .env.example y vuelve a provisionar."
  exit 1
fi

set -a
source <(sed 's/\r$//' "$PROJECT_DIR/.env")
set +a

POSTGRES_USER="${POSTGRES_USER:-mnm}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
JWT_SECRET="${JWT_SECRET:-}"
SEED_DEMO_DATA="${SEED_DEMO_DATA:-true}"

if [[ -z "$POSTGRES_PASSWORD" || ${#JWT_SECRET} -lt 32 ]]; then
  echo "Configura POSTGRES_PASSWORD y un JWT_SECRET de al menos 32 caracteres en .env."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io
systemctl enable --now docker

wait_for_database() {
  for attempt in $(seq 1 60); do
    if timeout 2 bash -c "echo > /dev/tcp/$DATABASE_IP/5432" 2>/dev/null; then
      return
    fi
    sleep 2
  done
  echo "PostgreSQL no responde en $DATABASE_IP:5432."
  exit 1
}

case "$SERVICE" in
  database)
    previous_postgres_user=
    if docker inspect database >/dev/null 2>&1; then
      previous_postgres_user=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' database \
        | sed -n 's/^POSTGRES_USER=//p' | head -n 1)
    fi
    docker volume create postgres_data
    docker rm -f database 2>/dev/null || true
    docker run -d \
      --name database \
      --restart unless-stopped \
      --publish "$DATABASE_IP:5432:5432" \
      --env "POSTGRES_USER=$POSTGRES_USER" \
      --env "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
      --env POSTGRES_DB=auth_db \
      --volume postgres_data:/var/lib/postgresql/data \
      --volume "$PROJECT_DIR/database/init:/docker-entrypoint-initdb.d:ro" \
      --health-cmd "pg_isready -U $POSTGRES_USER -d auth_db" \
      --health-interval 5s \
      --health-timeout 5s \
      --health-retries 12 \
      postgres:16-alpine

    database_ready=false
    for attempt in $(seq 1 60); do
      if docker exec database pg_isready -U "$POSTGRES_USER" -d auth_db >/dev/null 2>&1; then
        database_ready=true
        break
      fi
      sleep 2
    done
    if [[ "$database_ready" != true ]]; then
      echo "PostgreSQL no llegó a estar listo."
      exit 1
    fi
    database_admin_user="${previous_postgres_user:-$POSTGRES_USER}"
    if ! docker exec database psql -U "$database_admin_user" -d postgres -tAc 'SELECT 1' >/dev/null 2>&1; then
      database_admin_user="${POSTGRES_USER}"$'\r'
    fi
    if ! docker exec database psql -U "$database_admin_user" -d postgres -tAc 'SELECT 1' >/dev/null 2>&1; then
      echo "No se pudo autenticar con el usuario administrador existente de PostgreSQL."
      exit 1
    fi

    role_exists=$(docker exec -i database psql -U "$database_admin_user" -d postgres \
      --set=username="$POSTGRES_USER" --tuples-only --no-align <<'SQL'
SELECT 1 FROM pg_roles WHERE rolname = :'username';
SQL
    )
    if [[ "$role_exists" == 1 ]]; then
      docker exec -i database psql -U "$database_admin_user" -d postgres \
        --set=username="$POSTGRES_USER" \
        --set=password="$POSTGRES_PASSWORD" \
        --set=ON_ERROR_STOP=1 <<'SQL'
ALTER ROLE :"username" WITH LOGIN SUPERUSER PASSWORD :'password';
SQL
    else
      docker exec -i database psql -U "$database_admin_user" -d postgres \
        --set=username="$POSTGRES_USER" \
        --set=password="$POSTGRES_PASSWORD" \
        --set=ON_ERROR_STOP=1 <<'SQL'
CREATE ROLE :"username" WITH LOGIN SUPERUSER PASSWORD :'password';
SQL
    fi
    docker exec -i database psql -U "$database_admin_user" -d postgres \
      --set=username="$POSTGRES_USER" \
      --set=ON_ERROR_STOP=1 <<'SQL'
ALTER DATABASE auth_db OWNER TO :"username";
SQL
    banco_database_exists=$(docker exec database psql -U "$POSTGRES_USER" -d postgres \
      -tAc "SELECT 1 FROM pg_database WHERE datname = 'banco_db'")
    if [[ "$banco_database_exists" != 1 ]]; then
      docker exec database createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" banco_db
    else
      docker exec -i database psql -U "$POSTGRES_USER" -d postgres \
        --set=username="$POSTGRES_USER" \
        --set=ON_ERROR_STOP=1 <<'SQL'
ALTER DATABASE banco_db OWNER TO :"username";
SQL
    fi
    ;;
  auth|bank)
    wait_for_database
    docker build -t banco-mnm-app:local "$PROJECT_DIR/app"
    docker rm -f "$SERVICE" 2>/dev/null || true

    if [[ "$SERVICE" == "auth" ]]; then
      docker run -d \
        --name auth \
        --restart unless-stopped \
        --publish "$AUTH_IP:8001:8001" \
        --env "POSTGRES_USER=$POSTGRES_USER" \
        --env "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
        --env POSTGRES_HOST="$DATABASE_IP" \
        --env POSTGRES_PORT=5432 \
        --env "JWT_SECRET=$JWT_SECRET" \
        --env "TOKEN_MINUTES=${TOKEN_MINUTES:-60}" \
        --env "SEED_DEMO_DATA=$SEED_DEMO_DATA" \
        --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8001/health')\"" \
        --health-interval 10s \
        --health-timeout 3s \
        --health-retries 10 \
        banco-mnm-app:local \
        uvicorn auth_service.main:app --host 0.0.0.0 --port 8001
    else
      docker run -d \
        --name bank \
        --restart unless-stopped \
        --publish "$BANK_IP:8002:8002" \
        --env "POSTGRES_USER=$POSTGRES_USER" \
        --env "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
        --env POSTGRES_HOST="$DATABASE_IP" \
        --env POSTGRES_PORT=5432 \
        --env "JWT_SECRET=$JWT_SECRET" \
        --env "ALERT_THRESHOLD=${ALERT_THRESHOLD:-100000}" \
        --env "SEED_DEMO_DATA=$SEED_DEMO_DATA" \
        --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8002/health')\"" \
        --health-interval 10s \
        --health-timeout 3s \
        --health-retries 10 \
        banco-mnm-app:local \
        uvicorn bank_service.main:app --host 0.0.0.0 --port 8002
    fi
    ;;
  gateway)
    docker rm -f gateway 2>/dev/null || true
    docker run -d \
      --name gateway \
      --restart unless-stopped \
      --publish 80:80 \
      --volume "$PROJECT_DIR/frontend:/usr/share/nginx/html:ro" \
      --volume "$PROJECT_DIR/vagrant/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
      nginx:1.27-alpine
    ;;
  *)
    echo "Servicio desconocido: $SERVICE"
    exit 2
    ;;
esac