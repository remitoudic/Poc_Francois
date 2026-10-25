FROM postgres:16-alpine

# Copy database initialization scripts
COPY init.sql /docker-entrypoint-initdb.d/01-init.sql

EXPOSE 5432
