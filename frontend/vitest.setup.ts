import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// 每个用例之间清空 DOM：不加这行，前一个用例渲染出来的节点会留在 document 里，
// 后面的 getByRole 就会因为"找到多个"而失败（这跟组件本身无关）。
afterEach(cleanup);

// jsdom 没有实现 scrollIntoView。真实浏览器都有，但这里要补一个空实现，
// 否则组件一渲染就抛错，测试拿不到任何有用的结论。
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {
    /* jsdom 里没有滚动，空实现即可 */
  };
}
