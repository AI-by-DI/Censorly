import { useEffect, useMemo, useRef, useState } from "react";
import { countryOptions as RAW } from "../lib/worldCountries";
import React from "react";
interface Props {
  value?: string | null;               // ISO-2 ("TR")
  onChange: (val: string | null) => void;
  placeholder?: string;
}

// İstersen TR etiketini Türkçe gösterelim:
const countryOptions = RAW.map(o =>
  o.value === "TR" ? { ...o, label: "Türkiye" } : o
);

// Diyakritik normalize (İ/ı, Ç/ç vs. için)
const norm = (s: string) =>
  s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

export default function CountrySelect({
  value,
  onChange,
  placeholder = "Ülke seçiniz",
}: Props) {
  const selectRef = useRef<HTMLSelectElement>(null);

  // type-ahead buffer
  const [buf, setBuf] = useState("");
  const [ts, setTs] = useState<number>(0);

  // 700ms içinde yazılanları birleştir, sonra sıfırla
  useEffect(() => {
    if (!buf) return;
    const id = setTimeout(() => setBuf(""), 700);
    return () => clearTimeout(id);
  }, [buf, ts]);

  // buffer güncellenince ilk eşleşen ülkeye atla
  useEffect(() => {
    if (!buf) return;
    const i = countryOptions.findIndex(o => norm(o.label).startsWith(norm(buf)) || norm(o.value).startsWith(norm(buf)));
    if (i >= 0) {
      onChange(countryOptions[i].value);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buf]);

  // container keydown: her tuş vuruşunda buffer’ı güncelle
  const onKeyDown: React.KeyboardEventHandler<HTMLDivElement> = (e) => {
    // oklar ve enter'ı bırak
    if (["ArrowUp","ArrowDown","Enter","Tab","Escape"].includes(e.key)) return;
    if (e.key.length === 1) {
      // önce select’e odak verelim
      selectRef.current?.focus();
      setBuf(prev => prev + e.key);
      setTs(Date.now());
      e.preventDefault();
    }
  };

  return (
    <div
      style={{ width: "100%" }}
      onKeyDown={onKeyDown}
      onClick={() => selectRef.current?.focus()}
    >
      <select
        ref={selectRef}
        value={value ?? ""}
        onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
          onChange(e.target.value || null)
        }
        style={{
          padding: "10px 14px",
          borderRadius: 8,
          border: "1.5px solid #ccc",
          background: "#fff",
          width: "100%",
          fontSize: 16,
          cursor: "pointer",
        }}
      >
        <option value="">{placeholder}</option>
        {countryOptions.map((o) => (
          <option key={o.value} value={o.value}>
            {o.emoji} {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
