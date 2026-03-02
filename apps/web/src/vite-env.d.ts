/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  // burada başka .env değişkenlerin varsa onları da tanımla
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
