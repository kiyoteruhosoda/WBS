FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS build
WORKDIR /web
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build
FROM nginx:1.31-alpine@sha256:a3554c0d0b48177b1413c26e01f695334428020d9df01243fbae3e11cfd17417
COPY --from=build /web/dist /usr/share/nginx/html
# 起動時に envsubst で展開される (nginx 公式イメージの機構)。
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# 既定値。従来と同じ挙動になるので、compose 側の指定は任意。
# サービス名が衝突する環境では WBS_API_HOST を固有名に変えて渡す。
ENV WBS_API_HOST=api \
    WBS_API_PORT=8000 \
    WBS_RESOLVER=127.0.0.11
