# Multi-stage build for the React dashboard: build static assets, then serve
# them with a lightweight static file server.
FROM node:20-alpine AS build

WORKDIR /app

COPY src/dashboard/package.json ./
RUN npm install --legacy-peer-deps

COPY src/dashboard/ ./
RUN npm run build

FROM node:20-alpine AS serve
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /app/build ./build

EXPOSE 3000
CMD ["serve", "-s", "build", "-l", "3000"]
