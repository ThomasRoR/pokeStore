"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, Booster, Carta, Remessa } from "../../lib/api";

export default function BoostersPage() {
  const [boosters, setBoosters] = useState<Booster[]>([]);
  const [cartas, setCartas] = useState<Carta[]>([]);
  const [remessas, setRemessas] = useState<Remessa[]>([]);
  const [error, setError] = useState("");
  const [submittingBooster, setSubmittingBooster] = useState(false);

  const [boosterForm, setBoosterForm] = useState({
    nome_colecao: "",
    quantidade_booster: 1,
    custo_total: 0,
    remessa_id: 0,
    custo_minimo: 0
  });

  async function load() {
    try {
      setError("");
      const [r, b, c] = await Promise.all([api<Remessa[]>("/remessas"), api<Booster[]>("/boosters"), api<Carta[]>("/cartas")]);
      setRemessas(r);
      setBoosters(b);
      setCartas(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar boosters.");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!remessas.length) return;
    setBoosterForm((prev) => {
      const stillExists = remessas.some((r) => r.id === prev.remessa_id);
      return stillExists ? prev : { ...prev, remessa_id: remessas[0].id };
    });
  }, [remessas]);

  const custoUnitarioCalculado = useMemo(() => {
    if (boosterForm.quantidade_booster <= 0) return 0;
    return boosterForm.custo_total / boosterForm.quantidade_booster;
  }, [boosterForm.custo_total, boosterForm.quantidade_booster]);

  const custoUnitarioFinalPreCalculo = useMemo(() => {
    const remessa = remessas.find((r) => r.id === boosterForm.remessa_id);
    if (!remessa || boosterForm.quantidade_booster <= 0) return custoUnitarioCalculado;

    const rateio = remessa.valor_impostos + remessa.valor_frete;
    const baseCartas = cartas
      .filter((c) => c.remessa_id === remessa.id)
      .reduce((acc, c) => acc + c.preco_custo, 0);
    const baseBoosters = boosters
      .filter((b) => b.remessa_id === remessa.id)
      .reduce((acc, b) => acc + b.preco_custo * b.quantidade_booster, 0);

    const baseNovoBooster = boosterForm.custo_total;
    const baseTotal = baseCartas + baseBoosters + baseNovoBooster;
    if (baseTotal <= 0) return custoUnitarioCalculado;

    const parcelaRateioTotal = rateio * (baseNovoBooster / baseTotal);
    return custoUnitarioCalculado + parcelaRateioTotal / boosterForm.quantidade_booster;
  }, [boosterForm.custo_total, boosterForm.quantidade_booster, boosterForm.remessa_id, boosters, cartas, custoUnitarioCalculado, remessas]);

  async function onCreateBooster(e: FormEvent) {
    e.preventDefault();
    if (submittingBooster) return;
    try {
      setSubmittingBooster(true);
      setError("");
      await api<Booster>("/boosters", {
        method: "POST",
        body: JSON.stringify({
          nome_colecao: boosterForm.nome_colecao,
          quantidade_booster: boosterForm.quantidade_booster,
          preco_custo: custoUnitarioCalculado,
          remessa_id: boosterForm.remessa_id,
          custo_minimo: boosterForm.custo_minimo
        })
      });
      setBoosterForm((prev) => ({ ...prev, nome_colecao: "", quantidade_booster: 1, custo_total: 0, custo_minimo: 0 }));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao criar booster.");
    } finally {
      setSubmittingBooster(false);
    }
  }

  async function onDeleteBooster(boosterId: number) {
    if (!confirm(`Tem certeza que deseja excluir o booster #${boosterId}?`)) return;
    try {
      setError("");
      await api<void>(`/boosters/${boosterId}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao excluir booster.");
    }
  }

  return (
    <main>
      <h1>Boosters</h1>

      {error && (
        <section>
          <strong>Erro:</strong> {error}
        </section>
      )}

      <section>
        <h2>Novo booster</h2>
        <form onSubmit={onCreateBooster} className="grid cols-2">
          <div>
            <label>Nome da colecao</label>
            <input
              value={boosterForm.nome_colecao}
              onChange={(e) => setBoosterForm((p) => ({ ...p, nome_colecao: e.target.value }))}
              required
            />
          </div>
          <div>
            <label>Quantidade de booster</label>
            <input
              type="number"
              min={1}
              value={boosterForm.quantidade_booster}
              onChange={(e) => setBoosterForm((p) => ({ ...p, quantidade_booster: Number(e.target.value) }))}
            />
          </div>
          <div>
            <label>Custo total (adicionar)</label>
            <input
              type="number"
              min={0}
              step="0.01"
              value={boosterForm.custo_total}
              onChange={(e) => setBoosterForm((p) => ({ ...p, custo_total: Number(e.target.value) }))}
            />
          </div>
          <div>
            <label>Remessa</label>
            <select value={boosterForm.remessa_id} onChange={(e) => setBoosterForm((p) => ({ ...p, remessa_id: Number(e.target.value) }))}>
              {remessas.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id} - {r.nome}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>Custo unitario</label>
            <input className="readonly-field" value={custoUnitarioCalculado.toFixed(2)} readOnly />
          </div>
          <div>
            <label>Custo unitario final</label>
            <input className="readonly-field" value={custoUnitarioFinalPreCalculo.toFixed(2)} readOnly />
          </div>
          <div>
            <label>Custo minimo</label>
            <input
              type="number"
              min={0}
              step="0.01"
              value={boosterForm.custo_minimo}
              onChange={(e) => setBoosterForm((p) => ({ ...p, custo_minimo: Number(e.target.value) }))}
            />
          </div>
          <button type="submit" disabled={remessas.length === 0 || submittingBooster}>
            {submittingBooster ? "Enviando..." : "Adicionar booster"}
          </button>
        </form>
      </section>

      <section>
        <h2>Lista de boosters</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Colecao</th>
              <th>Qtd disponivel</th>
              <th>Remessa</th>
              <th>Valor total produto</th>
              <th>Custo unitario</th>
              <th>Custo unitario final</th>
              <th>Custo final total</th>
              <th>Custo minimo</th>
              <th>Acoes</th>
            </tr>
          </thead>
          <tbody>
            {boosters.map((b) => (
              <tr key={b.id}>
                <td>{b.id}</td>
                <td>{b.nome_colecao}</td>
                <td>{b.quantidade_booster}</td>
                <td>{b.remessa_nome ?? b.remessa_id}</td>
                <td>{(b.preco_custo * b.quantidade_booster).toFixed(2)}</td>
                <td>{b.preco_custo.toFixed(2)}</td>
                <td>{(b.custo_final / Math.max(b.quantidade_booster, 1)).toFixed(2)}</td>
                <td>{b.custo_final.toFixed(2)}</td>
                <td>{b.custo_minimo.toFixed(2)}</td>
                <td>
                  <div className="table-actions">
                    <button
                      className="icon-btn icon-btn-danger"
                      type="button"
                      onClick={() => void onDeleteBooster(b.id)}
                      title="Excluir"
                      aria-label="Excluir booster"
                    >
                      🗑️
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
