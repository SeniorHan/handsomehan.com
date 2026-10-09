// 主题核心逻辑：初始主题解析、切换、持久化。
// 与 DOM 解耦的纯逻辑，供 ThemeToggle 与防闪烁内联脚本共享同一套规则。
export type Theme = 'light' | 'dark';
export type ThemeChoice = Theme | 'system';

export const STORAGE_KEY = 'theme';

/** 从 localStorage 值解析用户显式选择，非法值视为未选择 */
export function parseStoredTheme(raw: string | null | undefined): ThemeChoice | null {
  if (raw === 'light' || raw === 'dark' || raw === 'system') return raw;
  return null;
}

/** 无用户显式选择时，按系统偏好解析初始主题 */
export function resolveInitialTheme(
  stored: string | null | undefined,
  prefersDark: boolean,
): Theme {
  const choice = parseStoredTheme(stored);
  if (choice === 'light') return 'light';
  if (choice === 'dark') return 'dark';
  return prefersDark ? 'dark' : 'light';
}

/** 'system' 表示跟随系统 → 不落盘（删除键）；显式主题才写入 */
export function persistTheme(choice: ThemeChoice): { op: 'set'; value: string } | { op: 'remove' } {
  if (choice === 'system') return { op: 'remove' };
  return { op: 'set', value: choice };
}

/** 循环切换顺序：light → dark → system → light */
export function nextThemeChoice(current: ThemeChoice): ThemeChoice {
  const order: ThemeChoice[] = ['light', 'dark', 'system'];
  return order[(order.indexOf(current) + 1) % order.length];
}

/** 某个选择在当前系统偏好下实际呈现的主题 */
export function effectiveTheme(choice: ThemeChoice, prefersDark: boolean): Theme {
  return resolveInitialTheme(choice === 'system' ? null : choice, prefersDark);
}
