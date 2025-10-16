// apps/web/src/lib/api.ts
import axios, { AxiosHeaders, AxiosRequestConfig, InternalAxiosRequestConfig } from "axios";

/** --------- Base URL --------- */
const BASE_URL =
  (import.meta as any).env?.VITE_API_URL ||
  (import.meta as any).env?.VITE_APP_API_URL ||
  "/api";

/** --------- Token Store --------- */
export const tokenStore = {
  get access()  { return localStorage.getItem("access"); },
  get refresh() { return localStorage.getItem("refresh"); },
  set(a?: string, r?: string) {
    if (a) localStorage.setItem("access", a);
    if (r) localStorage.setItem("refresh", r);
  },
  clear() {
    localStorage.removeItem("access");
    localStorage.removeItem("refresh");
  }
};

/** ================================================================
 *  Axios instance + Interceptors
 *  ================================================================ */
const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: false,
});

function ensureAxiosHeaders(h: InternalAxiosRequestConfig["headers"]) {
  return (h instanceof AxiosHeaders) ? h : new AxiosHeaders(h);
}

/** Bearer ekleme */
api.interceptors.request.use((config) => {
  const t = tokenStore.access;
  if (t) {
    const h = ensureAxiosHeaders(config.headers);
    h.set("Authorization", `Bearer ${t}`);
    config.headers = h;
  }
  return config;
});

/** 401 → refresh denemesi (tek uçlu, kuyruklu) */
let refreshing = false;
let waiters: Array<() => void> = [];

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const status = err?.response?.status;
    const original: AxiosRequestConfig & { _retried?: boolean } = err?.config ?? {};
    const hasRefresh = !!tokenStore.refresh;

    if (status === 401 && !original._retried && hasRefresh) {
      original._retried = true;

      if (!refreshing) {
        refreshing = true;
        try {
          const { data } = await axios.post(
            `${BASE_URL}/auth/refresh`,
            { token: tokenStore.refresh },
            { headers: { "Content-Type": "application/json" } }
          );
          tokenStore.set(data?.access_token, data?.refresh_token);
        } catch (e) {
          tokenStore.clear();
          refreshing = false;
          waiters.forEach((w) => w());
          waiters = [];
          return Promise.reject(err);
        }
        refreshing = false;
        waiters.forEach((w) => w());
        waiters = [];
      } else {
        await new Promise<void>((res) => waiters.push(res));
      }

      const at = tokenStore.access;
      const retryCfg: AxiosRequestConfig = {
        ...(original as AxiosRequestConfig),
        headers: {
          ...(original?.headers as any),
          ...(at ? { Authorization: `Bearer ${at}` } : {}),
        },
      };
      return api(retryCfg);
    }

    return Promise.reject(err);
  }
);

/* ... alttaki prefApi vs. aynı kalsın ... */

export default api;