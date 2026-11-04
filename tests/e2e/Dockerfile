FROM node:22.16.0-bookworm-slim@sha256:048ed02c5fd52e86fda6fbd2f6a76cf0d4492fd6c6fee9e2c463ed5108da0e34
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci --ignore-scripts
COPY apps/web/ apps/web/
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build && chown -R node:node /app/apps/web/.next
USER node
CMD ["npm", "run", "start", "--workspace", "apps/web"]
