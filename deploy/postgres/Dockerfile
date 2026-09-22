# Bakes the app-role bootstrap script into the image so nothing at runtime
# depends on a bind-mounted host path. It reads the app role's password from
# UNIVADMISSIONS_DB_PASSWORD at container start, not baked into this image.
FROM postgres:17-alpine
COPY 01-create-app-role.sh /docker-entrypoint-initdb.d/01-create-app-role.sh
RUN chmod +x /docker-entrypoint-initdb.d/01-create-app-role.sh
