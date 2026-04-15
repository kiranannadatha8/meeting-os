# Multi-stage Next.js 14 build. Standalone output keeps the runtime image
# tight (~200 MB vs. ~1 GB with a full node_modules copy).

FROM node:20-alpine AS builder
RUN apk add --no-cache libc6-compat
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
WORKDIR /repo

# Install all workspace deps in a single invocation using the committed
# lockfile. Copy manifests first so edits to source don't bust this layer.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY web/package.json web/
RUN pnpm install --frozen-lockfile

# Copy source and build. NEXTAUTH_SECRET placates the build-time check;
# the real value is injected at runtime.
COPY web ./web
ENV NEXTAUTH_SECRET=docker-build-placeholder
RUN pnpm --filter @meeting-os/web build

FROM node:20-alpine AS runtime
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN apk add --no-cache curl
WORKDIR /app

# Next.js standalone output ships only the subset of node_modules it needs,
# plus a preconfigured server.js entrypoint.
COPY --from=builder /repo/web/.next/standalone ./
COPY --from=builder /repo/web/.next/static ./web/.next/static
# web/public is optional — skipped if the app has no static assets yet.

EXPOSE 3000
CMD ["node", "web/server.js"]
