# EnergiQ AI web UI image. Build from the repository root:  docker build -f docker/frontend.Dockerfile -t energiq-web .
FROM node:22-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Same-origin API calls; nginx proxies /api to the backend (see docker/nginx.conf).
ENV VITE_API_BASE=""
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=4s --retries=3 CMD wget -qO- http://127.0.0.1:8080/nginx-health || exit 1
