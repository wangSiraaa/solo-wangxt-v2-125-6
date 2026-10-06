# 前端构建阶段（构建产物为纯静态文件，可完全离线部署）
FROM node:20-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY . .
# 离线瓦片（可选）：把 {z}/{x}/{y} 瓦片地址通过构建参数传入
# 例如 http://host:port/{z}/{x}/{y}.png；留空则使用无注记浅灰底
ARG VITE_TILE_URL=""
ENV VITE_TILE_URL=$VITE_TILE_URL
RUN npm run build

FROM nginx:1.27-bookworm AS serve
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
