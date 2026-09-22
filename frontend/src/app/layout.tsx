import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "国际象棋复盘教练",
  description:
    "Stockfish 判断好坏，确定性分析提取证据，AI 只负责把已核实的事实讲成人话。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">
        <header className="border-b" style={{ borderColor: "var(--border)" }}>
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-lg font-semibold">国际象棋复盘教练</span>
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                证据优先 · 可解释
              </span>
            </Link>
            <nav className="flex items-center gap-4 text-sm" style={{ color: "var(--muted)" }}>
              <Link href="/" className="hover:text-white">
                导入对局
              </Link>
              <Link href="/puzzles" className="hover:text-white">
                题目训练
              </Link>
              <Link href="/profile" className="hover:text-white">
                个人档案
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        <footer
          className="mx-auto max-w-7xl px-4 py-8 text-xs"
          style={{ color: "var(--muted)" }}
        >
          引擎证据来自本机 Stockfish；AI 解释仅基于已核实的证据，不会独立评估局面。
        </footer>
      </body>
    </html>
  );
}
