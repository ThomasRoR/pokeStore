"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "Dashboard" },
  { href: "/remessas", label: "Remessas" },
  { href: "/cartas", label: "Cartas" },
  { href: "/boosters", label: "Boosters" },
  { href: "/pedidos", label: "Pedidos" }
];

export function TopMenu() {
  const pathname = usePathname();

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <strong>Controle de Estoque Pokemon</strong>
        <nav className="menu">
          {items.map((item) => (
            <Link key={item.href} href={item.href} className={pathname === item.href ? "active" : ""}>
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
