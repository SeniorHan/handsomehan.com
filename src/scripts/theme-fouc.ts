// head 内联防闪烁脚本：首帧渲染前同步设置 data-theme。
// 通过 <script is:inline set:html> 内联进 Base.astro 的 <head>。
// 注意：脚本体是自包含字符串（内联场景无法打包 import），
// 解析规则必须与 src/scripts/theme.ts 的 resolveInitialTheme 保持一致——
// theme.test.ts 中有编译性测试 + 规则一致性用例守护。
import { STORAGE_KEY } from './theme';

/** 生成可内联的同步脚本源码（IIFE，无依赖） */
export function inlineFoucScript(): string {
  return `(function(){var k=${JSON.stringify(STORAGE_KEY)};var prefersDark=window.matchMedia('(prefers-color-scheme: dark)').matches;var raw=null;try{raw=localStorage.getItem(k)}catch(e){}var t;if(raw==='light')t='light';else if(raw==='dark')t='dark';else if(raw==='system')t=prefersDark?'dark':'light';else if(raw===null||raw===undefined)t=prefersDark?'dark':'light';else t=prefersDark?'dark':'light';document.documentElement.dataset.theme=t;})();`;
}

/** jsdom 环境下直接执行等价逻辑（供测试验证行为） */
export function applyStoredTheme(): void {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    /* 忽略存储不可用 */
  }
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const t =
    raw === 'light' ? 'light'
    : raw === 'dark' ? 'dark'
    : prefersDark ? 'dark'
    : 'light';
  document.documentElement.dataset.theme = t;
}
