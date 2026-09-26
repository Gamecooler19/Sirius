# syntax=docker/dockerfile:1
# Runs Vite's own dev server directly -- no build step, no static file
# server, no nginx/Caddy reverse proxy of any kind. `vite.config.ts` already
# sets `server.host = true` (binds 0.0.0.0 inside the container) and a fixed
# `server.port = 5173`, so the plain `npm run dev` below is sufficient; no
# extra CLI flags are needed to make the dev server reachable from outside
# the container's own network namespace.
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
