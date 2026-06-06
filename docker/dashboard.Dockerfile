# Multi-stage build for the React dashboard: build static assets, then serve
# them with a lightweight static file server.
FROM node:18-alpine AS build

# Build-time variable so CRA bakes the correct API URL into the JS bundle.
# Pass via docker-compose build.args or `docker build --build-arg ...`.
ARG REACT_APP_API_BASE_URL=http://localhost:8080
ENV REACT_APP_API_BASE_URL=$REACT_APP_API_BASE_URL

WORKDIR /app

COPY src/dashboard/package.json ./
# react-scripts 5 pulls ajv-keywords@5 which requires ajv@8, but react-scripts
# itself ships ajv@6. Installing ajv@8 explicitly hoists it into the top-level
# node_modules so ajv-keywords can resolve `ajv/dist/compile/codegen`.
RUN npm install --legacy-peer-deps && \
    npm install ajv@^8.0.0 --legacy-peer-deps

COPY src/dashboard/ ./
RUN npm run build

FROM node:20-alpine AS serve
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /app/build ./build

EXPOSE 3000
CMD ["serve", "-s", "build", "-l", "3000"]
