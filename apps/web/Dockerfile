FROM node:22.16.0-bookworm-slim@sha256:048ed02c5fd52e86fda6fbd2f6a76cf0d4492fd6c6fee9e2c463ed5108da0e34 AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci --ignore-scripts
COPY apps/web/ apps/web/
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace apps/web

FROM node:22.16.0-bookworm-slim@sha256:048ed02c5fd52e86fda6fbd2f6a76cf0d4492fd6c6fee9e2c463ed5108da0e34 AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=1000:1000 /app/apps/web/.next/standalone/ ./
COPY --from=build --chown=1000:1000 /app/apps/web/.next/static/ ./apps/web/.next/static/
COPY --from=build --chown=1000:1000 /app/apps/web/public/ ./apps/web/public/
USER 1000:1000
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
