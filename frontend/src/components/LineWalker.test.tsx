/**
 * LineWalker 的渲染测试。
 *
 * 这里守住的是一个真实发生过的 bug：入口按钮「▶ 演示后续走法」位于"还没开始演示"
 * 的状态里，而组件当时在 `lines === null` 时直接 `return null`。线路数据是**点了按钮
 * 才去取**的，所以那个条件永远成立，按钮永远渲染不出来——接口正常、打包产物里也有
 * 这段字符串，但界面上什么都没有。
 *
 * 因此这里最重要的一组断言是：**没有线路数据时，入口按钮也必须出现。**
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import LineWalker from "./LineWalker";
import type { MomentLines } from "@/lib/types";

function makeLines(): MomentLines {
  return {
    ply: 37,
    move_number: 19,
    played_move_san: "Rad1",
    best_move_san: "Rdd1",
    evaluation_before: -0.33,
    expected_score_before: 0.48,
    best: {
      kind: "best",
      label_zh: "引擎推荐线路",
      start_fen: "start",
      final_fen: "end",
      complete: true,
      truncated: false,
      ends_in_mate: false,
      steps: [
        { uci: "d3d1", san: "Rdd1", fen_after: "f1", mover: "white" },
        { uci: "g8f8", san: "Kf8", fen_after: "f2", mover: "black" },
        { uci: "d1e1", san: "Re1", fen_after: "f3", mover: "white" },
      ],
    },
    played: {
      kind: "played",
      label_zh: "实战线路（你实际走出来的）",
      start_fen: "start",
      final_fen: "end2",
      complete: true,
      truncated: false,
      ends_in_mate: false,
      steps: [{ uci: "a1d1", san: "Rad1", fen_after: "p1", mover: "white" }],
    },
  };
}

function noop() {
  /* 测试里不关心回调 */
}

describe("LineWalker", () => {
  it("没有线路数据时也要显示入口按钮（这正是之前的 bug）", () => {
    render(
      <LineWalker
        lines={null}
        loading={false}
        active={false}
        kind="best"
        index={0}
        playing={false}
        onStart={noop}
        onExit={noop}
        onKindChange={noop}
        onIndexChange={noop}
        onTogglePlaying={noop}
      />,
    );

    expect(screen.getByRole("button", { name: /演示后续走法/ })).toBeTruthy();
    // 并说明这个功能是干什么的
    expect(screen.getByText(/一步步走完引擎推荐的后续/)).toBeTruthy();
  });

  it("点了入口按钮会通知外面去取线路数据", () => {
    const onStart = vi.fn();
    render(
      <LineWalker
        lines={null}
        loading={false}
        active={false}
        kind="best"
        index={0}
        playing={false}
        onStart={onStart}
        onExit={noop}
        onKindChange={noop}
        onIndexChange={noop}
        onTogglePlaying={noop}
      />,
    );

    screen.getByRole("button", { name: /演示后续走法/ }).click();
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it("正在取数据时显示加载提示", () => {
    render(
      <LineWalker
        lines={null}
        loading
        active
        kind="best"
        index={0}
        playing={false}
        onStart={noop}
        onExit={noop}
        onKindChange={noop}
        onIndexChange={noop}
        onTogglePlaying={noop}
      />,
    );
    expect(screen.getByText(/正在展开引擎线路/)).toBeTruthy();
  });

  it("取数失败时给出重试，而不是静默消失", () => {
    render(
      <LineWalker
        lines={null}
        loading={false}
        active
        kind="best"
        index={0}
        playing={false}
        onStart={noop}
        onExit={noop}
        onKindChange={noop}
        onIndexChange={noop}
        onTogglePlaying={noop}
      />,
    );
    expect(screen.getByText(/没能取到这个局面的线路数据/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "重试" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /返回实战对局/ })).toBeTruthy();
  });

  it("演示中显示两条线路的切换、步进控制与着法列表", () => {
    render(
      <LineWalker
        lines={makeLines()}
        loading={false}
        active
        kind="best"
        index={2}
        playing={false}
        onStart={noop}
        onExit={noop}
        onKindChange={noop}
        onIndexChange={noop}
        onTogglePlaying={noop}
      />,
    );

    expect(screen.getByRole("button", { name: "引擎推荐线路" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "实战线路" })).toBeTruthy();
    expect(screen.getByText("2/3")).toBeTruthy();
    // 线路里的每一步都渲染成可点击的着法
    for (const san of ["Rdd1", "Kf8", "Re1"]) {
      expect(screen.getByRole("button", { name: san })).toBeTruthy();
    }
    // 当前步与下一步的说明
    expect(screen.getByText(/刚走：黑方 Kf8/)).toBeTruthy();
    expect(screen.getByText(/接下来：Re1/)).toBeTruthy();
  });

  it("切到实战线路会通知外面换线路", () => {
    const onKindChange = vi.fn();
    render(
      <LineWalker
        lines={makeLines()}
        loading={false}
        active
        kind="best"
        index={0}
        playing={false}
        onStart={noop}
        onExit={noop}
        onKindChange={onKindChange}
        onIndexChange={noop}
        onTogglePlaying={noop}
      />,
    );

    screen.getByRole("button", { name: "实战线路" }).click();
    expect(onKindChange).toHaveBeenCalledWith("played");
  });
});
