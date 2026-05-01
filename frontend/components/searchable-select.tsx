"use client";

import { useEffect, useMemo, useState } from "react";

type SearchableOption = {
  value: number;
  label: string;
};

type SearchableSelectProps = {
  value: number;
  options: SearchableOption[];
  placeholder?: string;
  disabled?: boolean;
  onChange: (value: number) => void;
};

export function SearchableSelect({ value, options, placeholder, disabled, onChange }: SearchableSelectProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const selected = useMemo(() => options.find((option) => option.value === value), [options, value]);

  useEffect(() => {
    setQuery(selected?.label ?? "");
  }, [selected]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return options;
    return options.filter((option) => option.label.toLowerCase().includes(term));
  }, [options, query]);

  return (
    <div className="searchable-select">
      <input
        type="text"
        value={query}
        placeholder={placeholder}
        disabled={disabled}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
      />
      {open && !disabled && (
        <div className="searchable-select-menu">
          {filtered.length > 0 ? (
            filtered.slice(0, 40).map((option) => (
              <button
                key={option.value}
                className="searchable-select-option"
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange(option.value);
                  setQuery(option.label);
                  setOpen(false);
                }}
              >
                {option.label}
              </button>
            ))
          ) : (
            <div className="searchable-select-empty">Nenhuma carta encontrada</div>
          )}
        </div>
      )}
    </div>
  );
}
