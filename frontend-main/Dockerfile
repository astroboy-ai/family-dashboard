# syntax=docker/dockerfile:1

# ---- Build stage ----
FROM node:20-alpine AS builder
WORKDIR /app

# Build-time env for Next.js rewrites (next.config.ts reads process.env.BACKEND_URL at build time)
ARG BACKEND_URL=http://familyos-backend:8000
ENV BACKEND_URL=${BACKEND_URL}

# Copy dependency manifests first for better layer caching
COPY package.json package-lock.json ./
RUN npm ci

# Copy source
COPY . .

# Build Next.js app
RUN npm run build

# ---- Production stage ----
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Copy built app from builder
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts
# Static assets. This must be a plain COPY: a COPY cannot be nested inside a RUN,
# and the previous `RUN mkdir -p public && COPY ...` was invalid — the manifest,
# service worker and icons would never reach the image.
COPY --from=builder /app/public ./public
COPY --from=builder /app/src ./src

# Install production dependencies (next start needs node_modules)
RUN npm install --production

# Set ownership
RUN chown -R nextjs:nodejs /app
USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["npm", "start"]
