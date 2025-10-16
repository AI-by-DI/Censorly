export function authHeaders(token?: string): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}