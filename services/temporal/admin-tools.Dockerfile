# One-shot jobs for Temporal: schema setup/upgrade and namespace registration.
ARG TEMPORAL_VERSION=1.32.1
FROM temporalio/admin-tools:${TEMPORAL_VERSION}

COPY --chmod=755 scripts/ /scripts/

ENTRYPOINT ["/bin/sh"]
