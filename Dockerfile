FROM node:24-bookworm-slim AS web-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ENV NEXT_TELEMETRY_DISABLED=1
ENV OPPORTUNITYOS_API_PORT=8000
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEXT_TELEMETRY_DISABLED=1 \
    OPPORTUNITYOS_API_PORT=8000 \
    OPPORTUNITYOS_FORCE_SECURE_COOKIES=1
WORKDIR /app
COPY --from=web-build /usr/local/bin/node /usr/local/bin/node
COPY --from=web-build /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
COPY pyproject.toml alembic.ini ./
COPY docs/STATE.md docs/SOURCE_REGISTRY.yaml docs/
COPY api api
COPY core core
COPY feedback feedback
COPY inbox inbox
COPY matching matching
COPY opportunity opportunity
COPY outbound outbound
COPY recon recon
COPY security security
COPY storage storage
COPY truth truth
COPY worker worker
COPY scripts scripts
RUN pip install --no-cache-dir .
COPY --from=web-build /app/web/package.json /app/web/package.json
COPY --from=web-build /app/web/package-lock.json /app/web/package-lock.json
COPY --from=web-build /app/web/node_modules /app/web/node_modules
COPY --from=web-build /app/web/.next /app/web/.next
COPY --from=web-build /app/web/public /app/web/public
EXPOSE 10000
CMD ["python", "scripts/production_start.py"]
