"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, API_URL, Booster, Carta, Remessa } from "../../lib/api";

type TcgSet = { id: string; name: string };
type TcgLanguage = "en" | "ja";
type PokeWalletSetsResponse = { sets?: TcgSet[] };

export default function CartasPage() {
  const [cartas, setCartas] = useState<Carta[]>([]);
  const [remessas, setRemessas] = useState<Remessa[]>([]);
  const [boosters, setBoosters] = useState<Booster[]>([]);
  const [colecoes, setColecoes] = useState<TcgSet[]>([]);
  const [tcgIdioma, setTcgIdioma] = useState<TcgLanguage>("en");
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    nome_carta: "",
    codigo_carta: "",
    colecao_id: "",
    preco_custo: 0,
    remessa_id: 0,
    preco_venda_minimo: 0
  });

  function mascaraCodigoCarta(valor: string): string {
    return valor.toUpperCase().replace(/[^A-Z0-9]/g, "");
  }

  function montarUrlImagem(urlBaseOuCompleta: string): string {
    if (!urlBaseOuCompleta) return "";
    if (urlBaseOuCompleta.startsWith("pokewallet:")) {
      const cardId = urlBaseOuCompleta.slice("pokewallet:".length);
      return `${API_URL}/integracoes/pokewallet/images/${encodeURIComponent(cardId)}?size=low`;
    }
    if (urlBaseOuCompleta.endsWith(".webp") || urlBaseOuCompleta.endsWith(".png") || urlBaseOuCompleta.endsWith(".jpg")) {
      return urlBaseOuCompleta;
    }
    return `${urlBaseOuCompleta}/low.webp`;
  }

  async function load() {
    try {
      setError("");
      const [r, c, b] = await Promise.all([api<Remessa[]>("/remessas"), api<Carta[]>("/cartas"), api<Booster[]>("/boosters")]);
      setRemessas(r);
      setCartas(c);
      setBoosters(b);
      if (r.length && form.remessa_id === 0) {
        setForm((prev) => ({ ...prev, remessa_id: r[0].id }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar cartas.");
    }
  }

  async function loadColecoes(lang: TcgLanguage) {
    try {
      let data: TcgSet[] = [];

      if (lang === "ja") {
        try {
          const resPokeWallet = await fetch(`${API_URL}/integracoes/pokewallet/sets?language=jap`);
          if (resPokeWallet.ok) {
            const payload = (await resPokeWallet.json()) as PokeWalletSetsResponse;
            if (Array.isArray(payload.sets) && payload.sets.length > 0) {
              data = payload.sets;
            }
          }
        } catch {
          // fallback para TCGdex abaixo
        }
      }

      if (data.length === 0) {
        const res = await fetch(`https://api.tcgdex.net/v2/${lang}/sets`);
        if (!res.ok) throw new Error("Falha ao carregar colecoes.");
        data = (await res.json()) as TcgSet[];
      }

      const dedupMap = new Map<string, TcgSet>();
      data.forEach((setItem) => {
        if (!dedupMap.has(setItem.id)) dedupMap.set(setItem.id, setItem);
      });
      const uniqueSets = Array.from(dedupMap.values());
      setColecoes(uniqueSets);
      setForm((prev) => {
        if (prev.colecao_id) return prev;
        const first = uniqueSets[0]?.id ?? "";
        return { ...prev, colecao_id: first };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar colecoes.");
    }
  }

  async function buscarImagemCarta(colecaoId: string, codigoCarta: string): Promise<string> {
    const cleanCodigo = codigoCarta.trim();
    if (!colecaoId || !cleanCodigo) return "";
    const resSet = await fetch(`https://api.tcgdex.net/v2/${tcgIdioma}/sets/${encodeURIComponent(colecaoId)}`);
    if (resSet.ok) {
      const dataSet = (await resSet.json()) as { cards?: Array<{ localId: string; image?: string }> };
      const cleanNoZero = cleanCodigo.replace(/^0+/, "") || "0";
      const found = (dataSet.cards ?? []).find((c) => {
        const local = (c.localId || "").toUpperCase();
        const localNoZero = local.replace(/^0+/, "") || "0";
        return local === cleanCodigo || localNoZero === cleanNoZero;
      });
      if (found?.image) return `${found.image}/low.webp`;
    }

    const candidates: string[] = [];
    if (/^\d+$/.test(cleanCodigo)) {
      if (tcgIdioma === "ja") {
        candidates.push(cleanCodigo.padStart(3, "0"));
      } else {
        candidates.push(cleanCodigo, String(Number(cleanCodigo)));
      }
    } else {
      candidates.push(cleanCodigo);
    }
    for (const localId of Array.from(new Set(candidates))) {
      const cardId = `${colecaoId}-${localId}`;
      const resCard = await fetch(`https://api.tcgdex.net/v2/${tcgIdioma}/cards/${encodeURIComponent(cardId)}`);
      if (!resCard.ok) continue;
      const cardData = (await resCard.json()) as { image?: string };
      if (cardData.image) return `${cardData.image}/low.webp`;
    }

    try {
      const params = new URLSearchParams({
        colecao_id: colecaoId,
        codigo_carta: cleanCodigo,
        nome_carta: form.nome_carta || ""
      });
      const resPokeWallet = await fetch(`${API_URL}/integracoes/pokewallet/resolver?${params.toString()}`);
      if (resPokeWallet.ok) {
        const data = (await resPokeWallet.json()) as { found?: boolean; card_id?: string };
        if (data.found && data.card_id) {
          return `pokewallet:${data.card_id}`;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao consultar Pokewallet.");
    }

    return "";
  }

  useEffect(() => {
    void load();
    void loadColecoes(tcgIdioma);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadColecoes(tcgIdioma);
    setForm((prev) => ({ ...prev, colecao_id: "" }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tcgIdioma]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    try {
      const codigoLimpo = mascaraCodigoCarta(form.codigo_carta);
      const imagemFinal = await buscarImagemCarta(form.colecao_id, codigoLimpo);
      await api<Carta>("/cartas", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          codigo_carta: codigoLimpo,
          imagem_url: imagemFinal
        })
      });
      setForm((prev) => ({
        ...prev,
        nome_carta: "",
        codigo_carta: "",
        preco_custo: 0,
        preco_venda_minimo: 0
      }));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao criar carta.");
    }
  }

  async function onDeleteCarta(cartaId: number) {
    if (!confirm(`Tem certeza que deseja excluir a carta #${cartaId}?`)) return;
    try {
      setError("");
      await api<void>(`/cartas/${cartaId}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao excluir carta.");
    }
  }

  const custoFinalSimulado = useMemo(() => {
    const remessa = remessas.find((r) => r.id === form.remessa_id);
    if (!remessa) return form.preco_custo;

    const rateio = remessa.valor_impostos + remessa.valor_frete;
    const baseCartas = cartas
      .filter((c) => c.remessa_id === remessa.id)
      .reduce((acc, c) => acc + c.preco_custo, 0);
    const baseBoosters = boosters
      .filter((b) => b.remessa_id === remessa.id)
      .reduce((acc, b) => acc + b.preco_custo * b.quantidade_booster, 0);

    const baseNovaCarta = form.preco_custo;
    const baseTotal = baseCartas + baseBoosters + baseNovaCarta;
    if (baseTotal <= 0) return form.preco_custo;

    const parcelaSimulada = rateio * (baseNovaCarta / baseTotal);
    return form.preco_custo + parcelaSimulada;
  }, [boosters, cartas, form.preco_custo, form.remessa_id, remessas]);

  return (
    <main>
      <h1>Cartas</h1>

      {error && (
        <section>
          <strong>Erro:</strong> {error}
        </section>
      )}

      <section>
        <h2>Nova carta</h2>
        <form onSubmit={onSubmit} className="grid cols-2">
          <div>
            <label>Nome da carta</label>
            <input value={form.nome_carta} onChange={(e) => setForm((p) => ({ ...p, nome_carta: e.target.value }))} required />
          </div>
          <div>
            <label>Codigo da carta</label>
            <input
              value={form.codigo_carta}
              inputMode="text"
              pattern="[A-Za-z0-9]*"
              placeholder="Ex: 1, 2, 3, XY99"
              onChange={(e) => setForm((p) => ({ ...p, codigo_carta: mascaraCodigoCarta(e.target.value) }))}
              required
            />
          </div>
          <div>
            <label>Idioma TCGdex</label>
            <select value={tcgIdioma} onChange={(e) => setTcgIdioma(e.target.value as TcgLanguage)}>
              <option value="en">Ingles</option>
              <option value="ja">Japones</option>
            </select>
          </div>
          <div>
            <label>Colecao</label>
            <select value={form.colecao_id} onChange={(e) => setForm((p) => ({ ...p, colecao_id: e.target.value }))}>
              {colecoes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id} - {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>Preco de custo</label>
            <input
              type="number"
              min={0}
              step="0.01"
              value={form.preco_custo}
              onChange={(e) => setForm((p) => ({ ...p, preco_custo: Number(e.target.value) }))}
            />
          </div>
          <div>
            <label>Remessa</label>
            <select value={form.remessa_id} onChange={(e) => setForm((p) => ({ ...p, remessa_id: Number(e.target.value) }))}>
              {remessas.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id} - {r.nome}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>Preco de venda minimo</label>
            <input
              type="number"
              min={0}
              step="0.01"
              value={form.preco_venda_minimo}
              onChange={(e) => setForm((p) => ({ ...p, preco_venda_minimo: Number(e.target.value) }))}
            />
          </div>
          <div>
            <label>Custo final simulado</label>
            <input className="readonly-field" value={custoFinalSimulado.toFixed(2)} readOnly />
          </div>
          <button type="submit" disabled={remessas.length === 0}>
            Adicionar carta
          </button>
        </form>
      </section>

      <section>
        <h2>Lista</h2>
        <table>
          <thead>
            <tr>
              <th>ID registro</th>
              <th>Imagem</th>
              <th>Nome</th>
              <th>Codigo da carta</th>
              <th>Remessa</th>
              <th>Custo</th>
              <th>Preco remessa</th>
              <th>Custo final</th>
              <th>Venda minima</th>
              <th>Status</th>
              <th>Cliente</th>
              <th>Acoes</th>
            </tr>
          </thead>
          <tbody>
            {cartas.map((c) => (
              <tr key={c.id}>
                <td>{c.id}</td>
                <td>{c.imagem_url ? <img src={montarUrlImagem(c.imagem_url)} alt={c.nome_carta} style={{ width: 52, borderRadius: 6 }} /> : "-"}</td>
                <td>{c.nome_carta}</td>
                <td>{c.codigo_carta}</td>
                <td>{c.remessa_nome ?? c.remessa_id}</td>
                <td>{c.preco_custo.toFixed(2)}</td>
                <td>{c.preco_remessa.toFixed(2)}</td>
                <td>{c.custo_final.toFixed(2)}</td>
                <td>{c.preco_venda_minimo.toFixed(2)}</td>
                <td>{c.status}</td>
                <td>{c.cliente || "-"}</td>
                <td>
                  <div className="table-actions">
                    <button
                      className="icon-btn icon-btn-danger"
                      type="button"
                      onClick={() => void onDeleteCarta(c.id)}
                      title="Excluir"
                      aria-label="Excluir carta"
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
