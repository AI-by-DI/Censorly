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
          // Backend’in mevcut sürümüne göre: { token: <refresh> }
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

      // Yeniden dene
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

/** ================================================================
 *  USER / AUTH (kullanıcı tabanlı)
 *  ================================================================ */
export const authApi = {
  async register(email: string, password: string, country?: string | null, age?: number | null) {
    const body: Record<string, any> = { email, password };
    if (country) body.country = country;          // ISO-2, örn "TR"
    if (age !== null && age !== undefined) body.age = age;

    const { data } = await api.post("/auth/register", body, {
      headers: { "Content-Type": "application/json" }
    });
    return data;
  },

  async login(email: string, password: string) {
    const { data } = await api.post(
      "/auth/login",
      { email, password },
      { headers: { "Content-Type": "application/json" } }
    );
    tokenStore.set(data?.access_token, data?.refresh_token);
    return data;
  },

  async me() {
    const { data } = await api.get("/auth/me");
    return data;
  },

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

/** ================================================================
 *  PREFERENCES (profil tabanlı)
 *  ================================================================ */

/** --- Tipler --- */
export type Category =
  | "alcohol"
  | "blood"
  | "violence"
  | "nudity"
  | "clown"
  | "snake"
  | "spider";

export const CATEGORIES: Category[] = [
  "alcohol", "blood", "violence", "nudity", "clown", "snake", "spider"
];

export type Mode = "blur" | "skip";
export type EffectiveMode = "blur" | "skip" | "none"; // none = dokunma/oynat

export type PreferencePayload = {
  name?: string;
  // true = sansürleme (oynat), false = sansürle
  allow_map: Partial<Record<Category, boolean>>;
  // global fallback (kategori özel seçilmezse)
  mode: Mode;
  // sadece sansürlenecek kategoriler için tip (blur/skip)
  mode_map: Partial<Record<Category, Mode>>;
};

export type PreferenceOut = PreferencePayload & {
  id: string;
  updated_at?: string;
};

export type EffectiveOut = {
  profile_id: string;
  effective: Record<Category | string, EffectiveMode>;
};

/** --- Helpers --- */
function completeAllowMap(src: Partial<Record<Category, boolean>>) {
  const out: Partial<Record<Category, boolean>> = {};
  for (const c of CATEGORIES) out[c] = src[c] ?? true; // default: sansürleme (oynat)
  return out;
}

/** Form-state → API payload (gereksizleri at, eksikleri tamamla) */
export function sanitizePreferencePayload(s: PreferencePayload): PreferencePayload {
  const allow_full = completeAllowMap(s.allow_map || {});
  const filteredModeMap: Partial<Record<Category, Mode>> = {};
  for (const c of CATEGORIES) {
    if (allow_full[c] === false) {
      filteredModeMap[c] = s.mode_map?.[c] || s.mode || "blur";
    }
  }
  return {
    name: s.name || "default",
    mode: s.mode || "blur",
    allow_map: allow_full,
    mode_map: filteredModeMap,
  };
}

/** --- API'ler --- */
export const prefApi = {
  async list(): Promise<PreferenceOut[]> {
    const { data } = await api.get("/me/preferences");
    return data;
  },

  async create(body: PreferencePayload): Promise<PreferenceOut> {
    const payload = sanitizePreferencePayload(body);
    const { data } = await api.post("/me/preferences", payload, {
      headers: { "Content-Type": "application/json" }
    });
    return data;
    // 409 gelirse aynı isimli profil var demektir
  },

  async update(id: string, body: Partial<PreferencePayload>): Promise<PreferenceOut> {
    // Kısmi güncelleme için minimal payload gönderebilirsin.
    // Eğer mode/allow_map değişiyorsa sanitize edelim:
    const patch =
      body.mode || body.allow_map || body.mode_map
        ? sanitizePreferencePayload({
            name: body.name ?? "default",
            mode: (body.mode as Mode) ?? "blur",
            allow_map: (body.allow_map || {}) as Partial<Record<Category, boolean>>,
            mode_map: (body.mode_map || {}) as Partial<Record<Category, Mode>>,
          })
        : body;

    const { data } = await api.put(`/me/preferences/${id}`, patch, {
      headers: { "Content-Type": "application/json" }
    });
    return data;
  },

  async effective(id: string): Promise<EffectiveOut> {
    const { data } = await api.get(`/me/preferences/${id}/effective`);
    return data;
  },
};

/** --- Aktif profil ID yönetimi (frontend içinde globale gerek yok) --- */
const ACTIVE_PROFILE_KEY = "active_profile_id";
export const ActiveProfile = {
  get(): string | null { return localStorage.getItem(ACTIVE_PROFILE_KEY); },
  set(id: string)      { localStorage.setItem(ACTIVE_PROFILE_KEY, id); },
  clear()              { localStorage.removeItem(ACTIVE_PROFILE_KEY); },
};

/** Kullanışlı default profil (ilk kurulumda) */
export const DEFAULT_PREF: PreferencePayload = {
  name: "default",
  mode: "blur",
  allow_map: {
    alcohol: true,
    blood: true,
    violence: true,
    nudity: true,
    clown: true,
    snake: true,
    spider: true,
  },
  mode_map: {},
};

/** Profil yoksa oluşturup aktif yapar; varsa ilki/aktif olanı döner */
export async function ensureActiveProfile(): Promise<PreferenceOut> {
  const list = await prefApi.list();
  if (list.length === 0) {
    const created = await prefApi.create(DEFAULT_PREF);
    ActiveProfile.set(created.id);
    return created;
  }
  const currentId = ActiveProfile.get() ?? list[0].id;
  ActiveProfile.set(currentId);
  return list.find(p => p.id === currentId) ?? list[0];
}

export default api;
