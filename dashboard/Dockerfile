# Build dashboard + serve via nginx that also reverse-proxies to the api service.
# Exposes a single public port (80) that serves both the SPA and the API surface.

FROM node:22-alpine AS builder
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
# Ensure empty VITE_API_BASE_URL so built bundle uses same-origin relative paths,
# which nginx below proxies to the api service.
RUN rm -f .env .env.local .env.production .env.development
RUN npm run build


FROM nginx:1.27-alpine
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx/prod.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
