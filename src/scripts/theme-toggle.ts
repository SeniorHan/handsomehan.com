// 主题切换按钮逻辑：三态循环（light → dark → system），写/删 localStorage，
// 监听系统偏好变化（仅当用户处于 system 态时跟随）。
import {
  effectiveTheme,
  nextThemeChoice,
  parseStoredTheme,
  persistTheme,
  STORAGE_KEY,
  type ThemeChoice,
} from './theme';

const LABELS: Record<ThemeChoice, string> = {
  light: '浅色主题',
  dark: '深色主题',
  system: '跟随系统',
};

export function currentChoice(): ThemeChoice {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    /* 忽略 */
  }
  return parseStoredTheme(raw) ?? 'system';
}

export function setTheme(choice: ThemeChoice): void {
  const op = persistTheme(choice);
  try {
    if (op.op === 'set') localStorage.setItem(STORAGE_KEY, op.value);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* 忽略 */
  }
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = effectiveTheme(choice, prefersDark);
  updateButton(choice);
}

function updateButton(choice: ThemeChoice): void {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.setAttribute('aria-label', `当前：${LABELS[choice]}，点击切换`);
  btn.dataset.choice = choice;
}

export function initThemeToggle(): void {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  if (btn.dataset.themeToggleInit === '1') return; // 幂等：防止重复绑定
  btn.dataset.themeToggleInit = '1';
  updateButton(currentChoice());
  btn.addEventListener('click', () => setTheme(nextThemeChoice(currentChoice())));

  // 用户未显式选择时，系统偏好变化实时跟随
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  mq.addEventListener('change', (e) => {
    if (currentChoice() === 'system') {
      document.documentElement.dataset.theme = e.matches ? 'dark' : 'light';
    }
  });
}
