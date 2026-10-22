# The Zolo web app (Next.js). Build-time settings (NEXT_PUBLIC_*) are baked in, so pass them as
# build args; the backend address is read at RUN time (BACKEND_URL).
FROM node:24-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ARG NEXT_PUBLIC_FEATURE_DEMO=true
ARG NEXT_PUBLIC_FEATURE_KITCHEN_SINK=false
ARG NEXT_PUBLIC_TEAM_NAME=
ARG NEXT_PUBLIC_REPO_URL=
ARG NEXT_PUBLIC_DEMO_VIDEO_URL=
ENV NEXT_PUBLIC_FEATURE_DEMO=$NEXT_PUBLIC_FEATURE_DEMO \
    NEXT_PUBLIC_FEATURE_KITCHEN_SINK=$NEXT_PUBLIC_FEATURE_KITCHEN_SINK \
    NEXT_PUBLIC_TEAM_NAME=$NEXT_PUBLIC_TEAM_NAME \
    NEXT_PUBLIC_REPO_URL=$NEXT_PUBLIC_REPO_URL \
    NEXT_PUBLIC_DEMO_VIDEO_URL=$NEXT_PUBLIC_DEMO_VIDEO_URL
RUN pnpm build

FROM build AS run
ENV NODE_ENV=production
# Readable by the unprivileged user; only .next needs writing (the image optimizer's cache).
RUN chmod -R a+rX /app && chown -R node:node /app/.next
USER node
EXPOSE 3000
# `next` directly: no package manager (and no download) at run time.
CMD ["node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
