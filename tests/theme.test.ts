import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  parseStoredTheme,
  resolveInitialTheme,
  persistTheme,
  nextThemeChoice,
  effectiveTheme,
  STORAGE_KEY,
} from '../src/scripts/theme';

describe('初始主题解析', () => {
  it('无存储且系统偏好暗色 → dark', () => {
    expect(resolveInitialTheme(null, true)).toBe('dark');
  });
  it('无存储且系统偏好浅色 → light', () => {
    expect(resolveInitialTheme(null, false)).toBe('light');
  });
  it('存储 light 优先于系统偏好', () => {
    expect(resolveInitialTheme('light', true)).toBe('light');
  });
  it('存储 dark 优先于系统偏好', () => {
    expect(resolveInitialTheme('dark', false)).toBe('dark');
  });
  it('存储 system → 跟随系统偏好', () => {
    expect(resolveInitialTheme('system', true)).toBe('dark');
    expect(resolveInitialTheme('system', false)).toBe('light');
  });
  it('非法存储值视为未选择', () => {
    expect(resolveInitialTheme('blue', true)).toBe('dark');
    expect(parseStoredTheme('blue')).toBeNull();
    expect(parseStoredTheme(undefined)).toBeNull();
  });
});

describe('持久化', () => {
  it('显式主题写入', () => {
    expect(persistTheme('dark')).toEqual({ op: 'set', value: 'dark' });
    expect(persistTheme('light')).toEqual({ op: 'set', value: 'light' });
  });
  it('system 删除存储键（回到跟随系统）', () => {
    expect(persistTheme('system')).toEqual({ op: 'remove' });
  });
});

describe('循环切换', () => {
  it('light → dark → system → light', () => {
    expect(nextThemeChoice('light')).toBe('dark');
    expect(nextThemeChoice('dark')).toBe('system');
    expect(nextThemeChoice('system')).toBe('light');
  });
});

describe('effectiveTheme', () => {
  it('system 在暗色系统下呈现 dark', () => {
    expect(effectiveTheme('system', true)).toBe('dark');
    expect(effectiveTheme('system', false)).toBe('light');
    expect(effectiveTheme('dark', false)).toBe('dark');
  });
});

describe('DOM 集成：ThemeToggle 行为', () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = '';
    document.documentElement.removeAttribute('data-theme');
    vi.stubGlobal('matchMedia', (q: string) => ({
      matches: q.includes('dark'),
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
  });

  it('点击后 data-theme 与 localStorage 同步更新', async () => {
    const { initThemeToggle } = await import('../src/scripts/theme-toggle');
    document.body.insertAdjacentHTML(
      'beforeend',
      '<button id="theme-toggle" aria-label="切换主题"><span class="theme-icon-light">☀️</span><span class="theme-icon-dark">🌙</span><span class="theme-icon-system">💻</span></button>',
    );
    initThemeToggle();
    const btn = document.getElementById('theme-toggle');
    expect(btn).toBeTruthy();

    // 初始：无存储（= system 态）+ 偏好暗色 → 呈现 dark（与 head 内联脚本一致）
    document.documentElement.dataset.theme = resolveInitialTheme(null, true);

    btn!.click(); // system → light
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(localStorage.getItem(STORAGE_KEY)).toBe('light');

    btn!.click(); // light → dark
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(localStorage.getItem(STORAGE_KEY)).toBe('dark');
  });

  it('aria-label 反映当前选择', async () => {
    const { initThemeToggle } = await import('../src/scripts/theme-toggle');
    localStorage.setItem(STORAGE_KEY, 'light');
    document.body.insertAdjacentHTML(
      'beforeend',
      '<button id="theme-toggle" aria-label="切换主题"><span class="theme-icon-light">☀️</span><span class="theme-icon-dark">🌙</span><span class="theme-icon-system">💻</span></button>',
    );
    initThemeToggle();
    const btn = document.getElementById('theme-toggle')!;
    expect(btn.getAttribute('aria-label')).toContain('浅色'); // 存储为 light
    btn.click(); // light → dark
    expect(btn.getAttribute('aria-label')).toContain('深色');
  });
});

describe('内联防闪烁脚本生成', () => {
  it('生成的脚本是合法 JS 且行为与 applyStoredTheme 一致', async () => {
    const { inlineFoucScript } = await import('../src/scripts/theme-fouc');
    const src = inlineFoucScript();
    new Function(src); // 语法检查：抛错即失败

    // 沙箱执行：mock document/localStorage/matchMedia，验证 data-theme 结果
    for (const [stored, prefersDark, expected] of [
      ['light', true, 'light'],
      [null, true, 'dark'],
      [null, false, 'light'],
      ['dark', false, 'dark'],
      ['system', false, 'light'],
      ['bogus', true, 'dark'],
    ] as const) {
      const el: any = { dataset: {} };
      const fn = new Function('document', 'localStorage', 'window', src);
      fn(
        { documentElement: el },
        { getItem: () => stored },
        { matchMedia: () => ({ matches: prefersDark }) },
      );
      expect(el.dataset.theme).toBe(expected);
    }
  });
});

describe('DOM 集成：防闪烁内联脚本 applyStoredTheme', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('matchMedia', (q: string) => ({
      matches: q.includes('dark'),
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
  });

  it('首帧前按存储/系统偏好设置 data-theme', async () => {
    localStorage.setItem(STORAGE_KEY, 'light');
    const { applyStoredTheme } = await import('../src/scripts/theme-fouc');
    applyStoredTheme();
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('无存储时跟随 prefers-color-scheme', async () => {
    const { applyStoredTheme } = await import('../src/scripts/theme-fouc');
    applyStoredTheme();
    expect(document.documentElement.dataset.theme).toBe('dark'); // stub 匹配 dark
  });
});
