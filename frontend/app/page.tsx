"use client";

import { useEffect, useState } from "react";
import { api, Dashboard } from "../lib/api";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Dashboard>("/dashboard")
      .then(setData)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Erro ao carregar dashboard."));
  }, []);

  return (
    <main>
      <h1>Dashboard</h1>

      {error && (
        <section>
          <strong>Erro:</strong> {error}
        </section>
      )}

      <section>
        <div className="grid cols-4">
          <div className="metric">
            <span className="muted">Remessas</span>
            <strong>{data?.totais.remessas ?? 0}</strong>
          </div>
          <div className="metric">
            <span className="muted">Cartas</span>
            <strong>{data?.totais.cartas ?? 0}</strong>
          </div>
          <div className="metric">
            <span className="muted">Boosters</span>
            <strong>{data?.totais.boosters ?? 0}</strong>
          </div>
          <div className="metric">
            <span className="muted">Pedidos</span>
            <strong>{data?.totais.pedidos_booster ?? 0}</strong>
          </div>
        </div>
      </section>

      <section>
        <h2>Cartas por status</h2>
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Quantidade</th>
            </tr>
          </thead>
          <tbody>
            {(data?.cartas_por_status ?? []).map((row) => (
              <tr key={row.status}>
                <td>{row.status}</td>
                <td>{row.quantidade}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
