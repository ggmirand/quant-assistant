FROM node:20-alpine
WORKDIR /ui
COPY package.json vite.config.ts ./
COPY src ./src
RUN npm install
EXPOSE 5173
CMD ["npm","run","dev","--","--host","0.0.0.0"]
