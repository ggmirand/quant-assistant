FROM node:20-alpine

WORKDIR /ui

# Copy minimal manifest first for better caching
COPY package.json vite.config.ts index.html ./

# App source
COPY src ./src

# Install deps
RUN npm ci || npm install

EXPOSE 5173

# Run the Vite dev server so port 5173 actually serves content
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

