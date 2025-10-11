// worldCountries.ts — world-countries verisini UI için normalize eder
import all from "world-countries";

// Bazı tarayıcılarda <option> içerisinde <img> destekli değil;
// bu yüzden güvenli emoji kullanıyoruz. (İstersen svg url de var.)
export type CountryOption = {
  value: string;      // ISO-2 kod (cca2) — "TR"
  label: string;      // "Turkey"
  emoji: string;      // 🇹🇷
  flagSvg: string;    // https://flagcdn.com/tr.svg (istersen kullanırsın)
};

// ISO-2 → 🇹🇷
export const codeToEmoji = (code: string) =>
  code.toUpperCase().replace(/./g, c => String.fromCodePoint(127397 + c.charCodeAt(0)));

export const countryOptions: CountryOption[] = (all as any[]).map((c: any) => ({
  value: c.cca2,                     // ISO-2
  label: c?.name?.common ?? c.cca2,  // Ülke adı (EN)
  emoji: codeToEmoji(c.cca2),
  flagSvg: c?.flags?.svg ?? "",
}))
// alfabetik sırala
.sort((a, b) => a.label.localeCompare(b.label, "en"));
