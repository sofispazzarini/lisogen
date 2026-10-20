FROM node:22.23.3-alpine

WORKDIR /app/frontend
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
EXPOSE 5173
# Servidor de desarrollo de Vite (la demo local); para producción: `npm run build` y servir dist/.
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
