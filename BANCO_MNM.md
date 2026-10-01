# Banco MNM API

La API se separa en dos servicios FastAPI: AUTH administra usuarios, contraseñas con hash Argon2 y tokens JWT; BANCO valida esos tokens localmente y consulta cuentas/transacciones. PostgreSQL usa las bases `auth_db` y `banco_db`, y Nginx enruta `/api/auth/*` a AUTH y el resto de `/api/*` a BANCO.

## Inicio local con Docker

Desde este directorio:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edita `.env` y sustituye `POSTGRES_PASSWORD` y `JWT_SECRET` por valores propios. Después:

```powershell
docker compose up --build -d
```

La aplicación web queda en `http://localhost:8080` y la API responde bajo ese mismo origen en `/api`. Nginx sirve la interfaz estática y enruta las llamadas a AUTH y BANCO. La documentación OpenAPI de cada servicio está disponible en `/docs` dentro de sus contenedores, no se publica directamente por Nginx. La base inicial y los usuarios de demostración se crean automáticamente. Las credenciales de demostración son `cliente1@bancomnm.xyz` / `Cliente123!` y `analista1@bancomnm.xyz` / `Analista123!`; desactiva `SEED_DEMO_DATA` y reemplázalas antes de cualquier despliegue real.

La interfaz presenta un dashboard distinto según el rol. El **cliente** ve saldo, ingresos/egresos, gráficos por mes y categoría, filtra sus movimientos y puede transferir fondos a otro usuario mediante su alias (la parte anterior a `@` en el correo). El **analista** ve totales globales, actividad mensual y alertas ordenadas por monto; es un rol de consulta y no puede transferir ni acceder a operaciones de cliente. El token se conserva en el almacenamiento local del navegador hasta cerrar sesión o expirar.

En desarrollo se crean cinco clientes (`cliente1` a `cliente5`, contraseña `Cliente123!`) y dos analistas (`analista1` y `analista2`, contraseña `Analista123!`). No uses estas cuentas en un despliegue real.

## Rutas

| Método | Ruta                                                                   | Acceso                                   |
| ------- | ---------------------------------------------------------------------- | ---------------------------------------- |
| POST    | `/api/auth/login`                                                    | Público; recibe`email` y `password` |
| GET     | `/api/auth/me`                                                       | Usuario autenticado                      |
| GET     | `/api/cliente/resumen`                                               | Cliente                                  |
| GET     | `/api/cliente/mensual`                                               | Cliente                                  |
| GET     | `/api/cliente/categorias`                                            | Cliente                                  |
| GET     | `/api/cliente/transacciones?desde=&hasta=&tipo=&pagina=&por_pagina=` | Cliente                                  |
| GET     | `/api/cliente/destinatarios`                                         | Cliente                                  |
| POST    | `/api/cliente/transferencias`                                        | Cliente                                  |
| GET     | `/api/global/resumen`                                                | Analista                                 |
| GET     | `/api/global/mensual`                                                | Analista                                 |
| GET     | `/api/global/alertas?pagina=&por_pagina=`                            | Analista                                 |

Las rutas privadas usan `Authorization: Bearer <token>`. Las transacciones del cliente se limitan a la cuenta incluida en el token; no se acepta un identificador de cuenta enviado por el navegador. Los importes se devuelven como números y los listados paginados como `{ pagina, por_pagina, total, items }`. El umbral de alertas se configura con `ALERT_THRESHOLD`.

Para transferir, envía `POST /api/cliente/transferencias` con `{"destinatario":"cliente2","monto":"1250.00"}`. BANCO comprueba destinatario, cuenta de origen y saldo; registra el débito y el crédito en una única transacción de base de datos. No se puede transferir a la propia cuenta ni enviar un importe superior al saldo disponible. `GET /api/cliente/destinatarios` devuelve los alias válidos salvo el del usuario autenticado.

## Dataset Berka

Coloca `account.asc` y `trans.asc` del dataset en el host y ejecuta el importador dentro del contenedor BANCO:

```powershell
docker compose cp C:\ruta\account.asc bank:/tmp/account.asc
docker compose cp C:\ruta\trans.asc bank:/tmp/trans.asc
docker compose exec bank python scripts/import_berka.py --accounts /tmp/account.asc --transactions /tmp/trans.asc --account-limit 100
```

El importador conserva los identificadores originales, convierte los tipos a `credito`/`debito`, traduce los símbolos de categoría conocidos y omite transacciones ya existentes. Revisa la licencia del dataset antes de redistribuirlo.

## Validación

```powershell
pip install -r app/requirements-dev.txt
$env:PYTHONPATH = (Resolve-Path app).Path
python -m pytest app/tests -q
```

Para detener los servicios: `docker compose down`. Los datos persisten en el volumen `postgres_data`.
