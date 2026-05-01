"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, Booster, Carta, Pedido, StatusPedido, TipoPedido } from "../../lib/api";
import { SearchableSelect } from "../../components/searchable-select";

export default function PedidosPage() {
  const [pedidos, setPedidos] = useState<Pedido[]>([]);
  const [cartas, setCartas] = useState<Carta[]>([]);
  const [boosters, setBoosters] = useState<Booster[]>([]);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editMap, setEditMap] = useState<Record<number, { status: StatusPedido; cliente: string }>>({});

  const [form, setForm] = useState({
    tipo_item: "booster" as TipoPedido,
    carta_id: 0,
    booster_id: 0,
    quantidade: 1,
    cliente: "",
    status: "separado" as StatusPedido
  });

  function formatCartaOption(carta: Carta): string {
    return `${carta.id} - ${carta.nome_carta} (${carta.codigo_carta})`;
  }

  const cartaOptions = useMemo(
    () =>
      cartas.map((carta) => ({
        value: carta.id,
        label: formatCartaOption(carta)
      })),
    [cartas]
  );

  async function load() {
    try {
      setError("");
      const [p, c, b] = await Promise.all([api<Pedido[]>("/pedidos"), api<Carta[]>("/cartas"), api<Booster[]>("/boosters")]);
      setPedidos(p);
      setCartas(c);
      setBoosters(b);

      const nextEditMap: Record<number, { status: StatusPedido; cliente: string }> = {};
      p.forEach((pedido) => {
        nextEditMap[pedido.id] = { status: pedido.status, cliente: pedido.cliente };
      });
      setEditMap(nextEditMap);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar pedidos.");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (form.tipo_item === "carta") {
      if (form.carta_id && cartas.some((c) => c.id === form.carta_id)) return;
      const firstCarta = cartas[0]?.id ?? 0;
      setForm((prev) => ({ ...prev, carta_id: firstCarta, quantidade: 1 }));
      return;
    }
    if (form.booster_id && boosters.some((b) => b.id === form.booster_id)) return;
    const firstBooster = boosters[0]?.id ?? 0;
    setForm((prev) => ({ ...prev, booster_id: firstBooster }));
  }, [boosters, cartas, form.booster_id, form.carta_id, form.tipo_item]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    try {
      setError("");
      const payload =
        form.tipo_item === "carta"
          ? {
              tipo_item: "carta" as const,
              carta_id: form.carta_id,
              quantidade: 1,
              cliente: form.cliente,
              status: form.status
            }
          : {
              tipo_item: "booster" as const,
              booster_id: form.booster_id,
              quantidade: form.quantidade,
              cliente: form.cliente,
              status: form.status
            };
      await api<Pedido>("/pedidos", { method: "POST", body: JSON.stringify(payload) });
      setForm((prev) => ({ ...prev, quantidade: 1, cliente: "", status: "separado" }));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao criar pedido.");
    }
  }

  async function onSavePedido(pedido: Pedido) {
    const edit = editMap[pedido.id];
    if (!edit || savingId === pedido.id) return;
    try {
      setSavingId(pedido.id);
      setError("");
      await api<Pedido>(`/pedidos/${pedido.id}`, {
        method: "PUT",
        body: JSON.stringify({
          tipo_item: pedido.tipo_item,
          carta_id: pedido.carta_id,
          booster_id: pedido.booster_id,
          quantidade: pedido.quantidade,
          cliente: edit.cliente,
          status: edit.status
        })
      });
      setEditingId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao atualizar pedido.");
    } finally {
      setSavingId(null);
    }
  }

  async function onDeletePedido(pedido: Pedido) {
    if (!confirm(`Tem certeza que deseja excluir o pedido #${pedido.id}?`)) return;
    try {
      setError("");
      await api<void>(`/pedidos/${pedido.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao excluir pedido.");
    }
  }

  return (
    <main>
      <h1>Pedidos</h1>

      {error && (
        <section>
          <strong>Erro:</strong> {error}
        </section>
      )}

      <section>
        <h2>Novo pedido</h2>
        <form onSubmit={onSubmit} className="grid cols-2">
          <div>
            <label>Tipo de item</label>
            <select
              value={form.tipo_item}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  tipo_item: e.target.value as TipoPedido,
                  quantidade: e.target.value === "carta" ? 1 : prev.quantidade
                }))
              }
            >
              <option value="booster">Booster</option>
              <option value="carta">Carta</option>
            </select>
          </div>

          {form.tipo_item === "carta" ? (
            <div>
              <label>Carta</label>
              <SearchableSelect
                value={form.carta_id}
                options={cartaOptions}
                placeholder="Pesquise por ID, nome ou codigo"
                disabled={cartas.length === 0}
                onChange={(selectedCartaId) => {
                  setForm((prev) => ({ ...prev, carta_id: selectedCartaId, quantidade: 1 }));
                }}
              />
            </div>
          ) : (
            <div>
              <label>Booster</label>
              <select value={form.booster_id} onChange={(e) => setForm((prev) => ({ ...prev, booster_id: Number(e.target.value) }))}>
                {boosters.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.id} - {b.nome_colecao} (disp: {b.quantidade_booster})
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label>Quantidade</label>
            <input
              type="number"
              min={1}
              value={form.tipo_item === "carta" ? 1 : form.quantidade}
              onChange={(e) => setForm((prev) => ({ ...prev, quantidade: Number(e.target.value) }))}
              disabled={form.tipo_item === "carta"}
            />
          </div>
          <div>
            <label>Status</label>
            <select value={form.status} onChange={(e) => setForm((prev) => ({ ...prev, status: e.target.value as StatusPedido }))}>
              <option value="vendido">vendido</option>
              <option value="separado">separado</option>
              <option value="enviado">enviado</option>
              <option value="entregue">entregue</option>
            </select>
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <label>Cliente</label>
            <textarea value={form.cliente} onChange={(e) => setForm((prev) => ({ ...prev, cliente: e.target.value }))} required />
          </div>
          <button
            type="submit"
            disabled={form.tipo_item === "carta" ? cartas.length === 0 || form.carta_id === 0 : boosters.length === 0}
          >
            Adicionar pedido
          </button>
        </form>
      </section>

      <section>
        <h2>Lista de pedidos</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Tipo</th>
              <th>Item</th>
              <th>Quantidade</th>
              <th>Cliente</th>
              <th>Status</th>
              <th>Criado em</th>
              <th>Acoes</th>
            </tr>
          </thead>
          <tbody>
            {pedidos.map((p) => {
              const isEditing = editingId === p.id;
              return (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>{p.tipo_item}</td>
                  <td>{p.tipo_item === "carta" ? `${p.nome_carta ?? "-"} (${p.codigo_carta ?? "-"})` : p.nome_colecao ?? "-"}</td>
                  <td>{p.quantidade}</td>
                  <td>
                    <textarea
                      value={editMap[p.id]?.cliente ?? p.cliente}
                      onChange={(e) =>
                        setEditMap((prev) => ({
                          ...prev,
                          [p.id]: {
                            status: prev[p.id]?.status ?? p.status,
                            cliente: e.target.value
                          }
                        }))
                      }
                      disabled={!isEditing}
                      readOnly={!isEditing}
                    />
                  </td>
                  <td>
                    <select
                      value={editMap[p.id]?.status ?? p.status}
                      onChange={(e) =>
                        setEditMap((prev) => ({
                          ...prev,
                          [p.id]: {
                            status: e.target.value as StatusPedido,
                            cliente: prev[p.id]?.cliente ?? p.cliente
                          }
                        }))
                      }
                      disabled={!isEditing}
                    >
                      <option value="vendido">vendido</option>
                      <option value="separado">separado</option>
                      <option value="enviado">enviado</option>
                      <option value="entregue">entregue</option>
                    </select>
                  </td>
                  <td>{p.criado_em}</td>
                  <td>
                    {isEditing ? (
                      <div className="table-actions">
                        <button
                          className="icon-btn"
                          type="button"
                          onClick={() => void onSavePedido(p)}
                          title="Salvar"
                          aria-label="Salvar pedido"
                          disabled={savingId === p.id}
                        >
                          {savingId === p.id ? "…" : "💾"}
                        </button>
                        <button
                          className="icon-btn"
                          type="button"
                          onClick={() => {
                            setEditingId(null);
                            setEditMap((prev) => ({
                              ...prev,
                              [p.id]: { status: p.status, cliente: p.cliente }
                            }));
                          }}
                          title="Cancelar"
                          aria-label="Cancelar edicao"
                          disabled={savingId === p.id}
                        >
                          ✕
                        </button>
                      </div>
                    ) : (
                      <div className="table-actions">
                        <button
                          className="icon-btn"
                          type="button"
                          onClick={() => setEditingId(p.id)}
                          title="Editar"
                          aria-label="Editar pedido"
                        >
                          ✏️
                        </button>
                        <button
                          className="icon-btn icon-btn-danger"
                          type="button"
                          onClick={() => void onDeletePedido(p)}
                          title="Excluir"
                          aria-label="Excluir pedido"
                        >
                          🗑️
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </main>
  );
}
