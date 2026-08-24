FROM node:22-alpine AS build
WORKDIR /web
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build
FROM nginx:1.27-alpine
COPY --from=build /web/dist /usr/share/nginx/html
# 起動時に envsubst で展開される (nginx 公式イメージの機構)。
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# 既定値。従来と同じ挙動になるので、compose 側の指定は任意。
# サービス名が衝突する環境では WBS_API_HOST を固有名に変えて渡す。
ENV WBS_API_HOST=api \
    WBS_API_PORT=8000 \
    WBS_RESOLVER=127.0.0.11
