FROM node:26-alpine@sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5 AS build
WORKDIR /web
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build
FROM nginx:1.31-alpine@sha256:fed7e14be83cbd2661a75cdc5b872d936cf155d46c327084d30b8df19ae88d72
COPY --from=build /web/dist /usr/share/nginx/html
# Expanded by envsubst at startup (mechanism of the official nginx image).
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# Defaults. Behavior is the same as before, so setting them in compose is optional.
# Where service names collide, pass a unique name in WBS_API_HOST.
ENV WBS_API_HOST=api \
    WBS_API_PORT=8000 \
    WBS_RESOLVER=127.0.0.11
