# ---- Stage 1: install production dependencies only (reproducible via package-lock.json) ----
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# ---- Stage 2: small runtime image, no build tools, runs as the non-root "node" user ----
FROM node:22-alpine
ENV NODE_ENV=production \
    SERVICE_NAME=notification-service \
    PORT=3004 \
    DB_PATH=/data/service.db
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY package.json ./
COPY src ./src

# writable data directory owned by the unprivileged user
RUN mkdir -p /data && chown -R node:node /data /app
USER node
EXPOSE 3004
VOLUME ["/data"]
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:'+process.env.PORT+'/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "src/index.js"]
