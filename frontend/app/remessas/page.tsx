"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, Remessa } from "../../lib/api";

export default function RemessasPage() {
  const [list, setList] = useState<Remessa[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    nome: "",
    valor_remessa: 0,
    valor_impostos: 0,
    valor_frete: 0
  });

  async function load() {
    try {
      setError("");
      const data = await api<Remessa[]>("/remessas");
      setList(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar remessas.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    try {
      await api<Remessa>("/remessas", { method: "POST", body: JSON.stringify(form) });
      setForm({ nome: "", valor_remessa: 0, valor_impostos: 0, valor_frete: 0 });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao criar remessa.");
    }
  }

  return (
    <main>
      <h1>Remessas</h1>

      {error && (
        <section>
          <strong>Erro:</strong> {error}
        </section>
      )}

      <section>
        <h2>Nova remessa</h2>
        <form onSubmit={onSubmit} className="grid cols-2">
          <div>
            <label>Nome da remessa</label>
            <input value={form.nome} onChange={(e) => setForm((p) => ({ ...p, nome: e.target.value }))} required />
          </div>
          <div>
            <label>Valor da remessa</label>
            <input
              type="number"
              min={0}
              step="0.01"
              value={form.valor_remessa}
              onChange={(e) => setForm((p) => ({ ...p, valor_remessa: Number(e.target.value) }))}
            />
          </div>
          <div>
            <label>Valor em impostos</label>
            <input
              type="number"
              min={0}
              step="0.01"
              value={form.valor_impostos}
              onChange={(e) => setForm((p) => ({ ...p, valor_impostos: Number(e.target.value) }))}
            />
          </div>
          <div>
            <label>Valor em frete</label>
            <input
              type="number"
              min={0}
              step="0.01"
              value={form.valor_frete}
              onChange={(e) => setForm((p) => ({ ...p, valor_frete: Number(e.target.value) }))}
            />
          </div>
          <button type="submit">Adicionar remessa</button>
        </form>
      </section>

      <section>
        <h2>Lista</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Nome</th>
              <th>Valor</th>
              <th>Impostos</th>
              <th>Frete</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.nome}</td>
                <td>{r.valor_remessa.toFixed(2)}</td>
                <td>{r.valor_impostos.toFixed(2)}</td>
                <td>{r.valor_frete.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
