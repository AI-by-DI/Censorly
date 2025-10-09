// apps/web/src/lib/api.ts
import axios, { AxiosHeaders, AxiosRequestConfig, InternalAxiosRequestConfig } from "axios";

/** --------- Base URL --------- */
const BASE_URL =
  (import.meta as any).env?.VITE_API_URL ??
  (import.meta as any).env?.VITE_APP_API_URL ??
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

/** --------- Axios instance --------- */
const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: false,
  // timeout: 15000, // istersen ekleyebilirsin
});

/** Header yardımcıları */
function ensureAxiosHeaders(h: InternalAxiosRequestConfig["headers"]) {
  return (h instanceof AxiosHeaders) ? h : new AxiosHeaders(h);
}

/** --------- Request Interceptor (Bearer) --------- */
api.interceptors.request.use((config) => {
  const t = tokenStore.access;
  if (t) {
    const h = ensureAxiosHeaders(config.headers);
    h.set("Authorization", `Bearer ${t}`);
    config.headers = h;
  }
  return config;
});

/** --------- Response Interceptor (401 -> refresh) --------- */
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

      // Tek seferde refresh
      if (!refreshing) {
        refreshing = true;
        try {
          // Refresh endpoint — backend’in şu anki sürümüne göre JSON body { token: <refresh> }
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
        // Devam eden refresh tamamlanana kadar bekle
        await new Promise<void>((res) => waiters.push(res));
      }

      // Refresh sonrası isteği yeniden dene (TIP-SAFE)
      const at = tokenStore.access;

      const retryCfg: AxiosRequestConfig = {
        // orijinali kopyala
        ...(original as AxiosRequestConfig),
        // header'ları normalize et (undefined ise boş obje ver)
        headers: {
          ...(original?.headers as any),
          ...(at ? { Authorization: `Bearer ${at}` } : {}),
        },
      };

      // Axios, düz obje header'ı kabul eder (AxiosHeaders olmasına gerek yok)
      return api(retryCfg);


    }

    return Promise.reject(err);
  }
);

/** --------- Convenience Auth API'leri --------- */
export const authApi = {
  /** Register — backend JSON bekliyorsa bu sürüm; form istiyorsan alt yorumdaki sürümü kullan */
  async register(email: string, password: string, country?: string | null, age?: number | null) {
    const body: Record<string, any> = { email, password };
    if (country) body.country = country;          // ISO-2, örn "TR"
    if (age !== null && age !== undefined) body.age = age;

    const { data } = await api.post("/auth/register", body, {
      headers: { "Content-Type": "application/json" }
    });
    return data;

    /*  Eğer backend application/x-www-form-urlencoded bekliyorsa bunu kullan:
    const form = new URLSearchParams();
    form.set("email", email);
    form.set("password", password);
    if (country) form.set("country", country);
    if (age !== null && age !== undefined) form.set("age", String(age));
    const { data } = await api.post("/auth/register", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" }
    });
    return data;
    */
  },

  /** Login — backend JSON kabul ediyor (Swagger’da kullandığınla uyumlu) */
  async login(email: string, password: string) {
    const { data } = await api.post(
      "/auth/login",
      { email, password },
      { headers: { "Content-Type": "application/json" } }
    );
    tokenStore.set(data?.access_token, data?.refresh_token);
    return data;
  },

  /** Kimlik bilgisi */
  async me() {
    const { data } = await api.get("/auth/me");
    return data;
  },

  /** Logout — Authorization header + body’de refresh_token (backend’in güncel sürümüne uygun) */
  async logout() {
    const at = tokenStore.access;
    const rt = tokenStore.refresh;

    await api.post(
      "/auth/logout",
      { refresh_token: rt ?? null },
      { headers: at ? { Authorization: `Bearer ${at}` } : {} }
    );

    tokenStore.clear();
  }
};

export default api;
