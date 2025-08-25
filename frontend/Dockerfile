FROM node:20-alpine

WORKDIR /ui
RUN apk add --no-cache curl

# Copy minimal manifest first for better caching
COPY package.json vite.config.ts index.html ./
# If you DO add a lockfile later, uncomment the next line:
# COPY package-lock.json ./

# App source
COPY src ./src

# Install deps (no npm ci since lockfile is absent)
RUN npm install

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
