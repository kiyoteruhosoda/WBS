FROM node:26-alpine@sha256:8996bb5821d62a8fd9bb27c1cb07462f3fdce6e47d640c6a881ead0b064ce216 AS build
WORKDIR /web
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build
FROM nginx:1.31-alpine@sha256:713fc2ebfd92e8217db451477182ee91944b123d2b1ee9fd5a8c6e91ca6c3a11
COPY --from=build /web/dist /usr/share/nginx/html
# Expanded by envsubst at startup (mechanism of the official nginx image).
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# Defaults. Behavior is the same as before, so setting them in compose is optional.
# Where service names collide, pass a unique name in WBS_API_HOST.
ENV WBS_API_HOST=api \
    WBS_API_PORT=8000 \
    WBS_RESOLVER=127.0.0.11
