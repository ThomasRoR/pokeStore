import "./globals.css";
import type { Metadata } from "next";
import React from "react";
import { TopMenu } from "../components/top-menu";

export const metadata: Metadata = {
  title: "Controle de Estoque Pokemon",
  description: "Frontend Next.js para FastAPI"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <TopMenu />
        {children}
      </body>
    </html>
  );
}
