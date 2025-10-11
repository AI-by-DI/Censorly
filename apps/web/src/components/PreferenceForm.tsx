import React from "react";

type Category = "alcohol"|"blood"|"violence"|"nudity"|"clown"|"snake"|"spider";
const CATS: Category[] = ["alcohol","blood","violence","nudity","clown","snake","spider"];

type Mode = "blur"|"skip";

export type PrefState = {
  name: string;
  allow_map: Record<Category, boolean>; // true=Sansürleme, false=Sansürle
  mode: Mode;                           // global (fallback)
  mode_map: Partial<Record<Category, Mode>>;
};

type Props = {
  value: PrefState;
  onChange: (v: PrefState) => void;
  onSubmit: () => void;
  submitting?: boolean;
};

export default function PreferenceForm({ value, onChange, onSubmit, submitting }: Props) {

  const handleAllowToggle = (cat: Category, v: boolean) => {
    onChange({
      ...value,
      allow_map: { ...value.allow_map, [cat]: v }
    });
  };

  const handleModeChange = (cat: Category, m: Mode) => {
    onChange({
      ...value,
      mode_map: { ...value.mode_map, [cat]: m }
    });
  };

  return (
    <div style={{maxWidth: 760, margin: "0 auto"}}>


      <table style={{width:"100%", borderCollapse:"collapse"}}>
        <thead>
          <tr>
            <th style={th}>Kategori</th>
            <th style={th}>Sansürle?</th>
            <th style={th}>Sansür Tipi</th>
          </tr>
        </thead>
        <tbody>
          {CATS.map(cat => {
            const allow = value.allow_map[cat] ?? true; // default: sansürleme
            const disabled = allow === true;            // sansürlemiyorsak tip seçilmez
            return (
              <tr key={cat}>
                <td style={td}>{labelOf(cat)}</td>
                <td style={td}>
                  {/* Sansürle switch’i: false=sansürle, true=sansürleme */}
                  <select
                    value={allow ? "allow" : "block"}
                    onChange={e => handleAllowToggle(cat, e.target.value === "allow")}
                  >
                    <option value="allow">Sansürleme (oynat)</option>
                    <option value="block">Sansürle</option>
                  </select>
                </td>
                <td style={td}>
                  <select
                    value={value.mode_map[cat] || value.mode}
                    onChange={e => handleModeChange(cat, e.target.value as Mode)}
                    disabled={disabled}
                  >
                    <option value="blur">Bulanıklaştır</option>
                    <option value="skip">Atla</option>
                  </select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div style={{marginTop:16}}>
        <button onClick={onSubmit} disabled={submitting}>
          {submitting ? "Kaydediliyor..." : "Kaydet"}
        </button>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { textAlign:"left", padding:"8px 6px", borderBottom:"1px solid #333" };
const td: React.CSSProperties = { padding:"8px 6px", borderBottom:"1px solid #222" };

function labelOf(cat: Category) {
  switch(cat){
    case "alcohol": return "Alkol";
    case "blood": return "Kan";
    case "violence": return "Şiddet";
    case "nudity": return "Mahremiyet";
    case "clown": return "Palyaço";
    case "snake": return "Yılan";
    case "spider": return "Örümcek";
  }
}
