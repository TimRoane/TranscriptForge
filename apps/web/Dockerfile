FROM node:22-alpine AS base

WORKDIR /app
COPY package.json package-lock.json* ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci

FROM base AS development
COPY apps/web ./apps/web
EXPOSE 5173
CMD ["npm", "--workspace", "@transcriptforge/web", "run", "dev", "--", "--host", "0.0.0.0"]

FROM base AS build
COPY apps/web ./apps/web
RUN npm --workspace @transcriptforge/web run build

FROM nginx:1.27-alpine AS production
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
EXPOSE 80
