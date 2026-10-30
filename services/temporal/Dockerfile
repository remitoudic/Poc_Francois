# Temporal server (workflow engine) for FOX MLO.
# Schemas are created by the temporal-setup job (admin-tools.Dockerfile) before this starts.
ARG TEMPORAL_VERSION=1.32.1
FROM temporalio/server:${TEMPORAL_VERSION}

COPY dynamicconfig/ /etc/temporal/config/dynamicconfig/
