import React from "react";
import { LucideIcon } from "lucide-react";

export type FilterMode = "none" | "blur" | "skip";

interface FilterToggleProps {
  /** Filtre kategorisinin görünen ismi */
  name: string;
  /** Lucide ikonu (ör. Flame, Droplet, Skull, vb.) */
  icon: LucideIcon;
  /** Kategori rengi (ör. "#ef4444") */
  color: string;
  /** Şu anda seçili mod ("none" | "blur" | "skip") */
  mode: FilterMode;
  /** Mod değiştiğinde tetiklenecek fonksiyon */
  onChange: (mode: FilterMode) => void;
}

const MODES: FilterMode[] = ["none", "blur", "skip"];
const LABELS: Record<FilterMode, string> = {
  none: "No Filter",
  blur: "Blur",
  skip: "Skip",
};

const FilterToggle = ({
  name,
  icon: Icon,
  color,
  mode,
  onChange,
}: FilterToggleProps) => {
  return (
    <div
      className="flex flex-col sm:flex-row sm:items-center sm:justify-between 
                 p-4 rounded-xl bg-card border border-border hover:border-muted 
                 transition-colors"
    >
      <div className="flex items-center gap-3 mb-3 sm:mb-0">
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center"
          style={{
            backgroundColor: `${color}20`,
            color: color,
          }}
        >
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <p className="font-medium">{name}</p>
          <p className="text-sm text-muted-foreground">
            {LABELS[mode]} mode selected
          </p>
        </div>
      </div>

      {/* 3 modlu kontrol */}
      <div className="flex gap-2 bg-muted p-1 rounded-lg w-full sm:w-auto">
        {MODES.map((m) => (
          <button
            key={m}
            onClick={() => onChange(m)}
            className={`flex-1 sm:px-4 sm:py-1 text-sm rounded-md transition-colors
              ${mode === m
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
              }`}
          >
            {LABELS[m]}
          </button>
        ))}
      </div>
    </div>
  );
};

export default FilterToggle;
