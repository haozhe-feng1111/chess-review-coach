import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * 前端组件测试配置。
 *
 * 加这套测试的直接原因：线路演示的入口按钮曾经因为一个「数据没加载就 return null」
 * 的提前退出而**永远渲染不出来**。当时我用「接口能返回数据 + 打包产物里有这段字符串」
 * 来验证，两样都通过了，但用户在界面上根本看不到按钮。
 * 字符串在包里 ≠ 组件会渲染。所以现在至少要对关键组件做真实渲染测试。
 */
export default defineConfig({
  // 让测试也认识 tsconfig 里的 "@/*" 路径别名
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.tsx"],
    setupFiles: ["./vitest.setup.ts"],
    globals: false,
  },
});
