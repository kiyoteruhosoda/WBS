FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build
WORKDIR /web
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build
FROM nginx:1.31-alpine@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2
COPY --from=build /web/dist /usr/share/nginx/html
# 起動時に envsubst で展開される (nginx 公式イメージの機構)。
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# 既定値。従来と同じ挙動になるので、compose 側の指定は任意。
# サービス名が衝突する環境では WBS_API_HOST を固有名に変えて渡す。
ENV WBS_API_HOST=api \
    WBS_API_PORT=8000 \
    WBS_RESOLVER=127.0.0.11
