FROM node:18-alpine
WORKDIR /app

COPY ./apps/web/package*.json ./
RUN [ -f package.json ] && npm install || true

COPY ./apps/web .

EXPOSE 5173
CMD ["npm", "run", "dev"]
