FROM node:22.23.4-alpine AS build
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.28.3-alpine
# Origin(s) recordings may play from (Content-Security-Policy media-src); Wasabi by default.
ENV MEDIA_ORIGINS="https://*.wasabisys.com"
# Where the backend answers, host:port (the compose service by default; on Render the private
# service address, render.yaml).
ENV BACKEND_HOSTPORT="backend:8000"
# Who may tell nginx the visitor's address, and in which header (render.yaml sets both for Render).
ENV REAL_IP_FROM="127.0.0.1/32" REAL_IP_HEADER="X-Real-IP"
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
