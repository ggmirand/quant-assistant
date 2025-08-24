FROM node:20-alpine
WORKDIR /ui
ENV NODE_OPTIONS=--max_old_space_size=512
COPY package.json vite.config.ts index.html ./
COPY src ./src
RUN npm install && npm run build
EXPOSE 5173
CMD ["npm","run","preview","--","--host","0.0.0.0","--port","5173"]

