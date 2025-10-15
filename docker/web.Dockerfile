# docker/web.Dockerfile
# --- Build stage ----------------------------------------------------
    FROM node:20-alpine AS build
    WORKDIR /app
    
    # Sadece web bağımlılıklarını daha erken cache’lemek için önce package*.json
    COPY apps/web/package*.json ./
    RUN npm ci
    
    # Kaynakları kopyala ve production build al
    COPY apps/web/ .
    # (İstersen .env.production dosyan varsa Vite otomatik okur)
    # Build-time API adresi geçirmek için ARG/ENV:
    ARG VITE_API_URL
    ENV VITE_API_URL=${VITE_API_URL}
    RUN npm run build
    
    # --- Runtime stage (Nginx) ------------------------------------------
    FROM nginx:alpine AS runtime
    WORKDIR /usr/share/nginx/html
    
    # Basit SPA nginx conf (history fallback)
    RUN rm -f /etc/nginx/conf.d/default.conf
    COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
    
    # Statik dosyaları kopyala
    COPY --from=build /app/dist ./
    
    EXPOSE 80
    CMD ["nginx", "-g", "daemon off;"]