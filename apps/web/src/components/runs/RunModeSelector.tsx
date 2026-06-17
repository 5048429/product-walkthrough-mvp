import type { RunMode, VerificationMode } from "../../types/contracts";

interface RunModeSelectorProps {
  mode: RunMode;
  browserMaxSteps: number;
  browserTimeoutSec: number;
  browserUserDataDir: string;
  browserStorageState: string;
  verificationMode: VerificationMode;
  verificationTimeoutSec: number;
  verificationSuccessUrlContains: string;
  verificationLoginUrlContains: string;
  onModeChange: (mode: RunMode) => void;
  onBrowserMaxStepsChange: (steps: number) => void;
  onBrowserTimeoutSecChange: (seconds: number) => void;
  onBrowserUserDataDirChange: (path: string) => void;
  onBrowserStorageStateChange: (path: string) => void;
  onVerificationModeChange: (mode: VerificationMode) => void;
  onVerificationTimeoutSecChange: (seconds: number) => void;
  onVerificationSuccessUrlContainsChange: (value: string) => void;
  onVerificationLoginUrlContainsChange: (value: string) => void;
}

export function RunModeSelector({
  mode,
  browserMaxSteps,
  browserTimeoutSec,
  browserUserDataDir,
  browserStorageState,
  verificationMode,
  verificationTimeoutSec,
  verificationSuccessUrlContains,
  verificationLoginUrlContains,
  onModeChange,
  onBrowserMaxStepsChange,
  onBrowserTimeoutSecChange,
  onBrowserUserDataDirChange,
  onBrowserStorageStateChange,
  onVerificationModeChange,
  onVerificationTimeoutSecChange,
  onVerificationSuccessUrlContainsChange,
  onVerificationLoginUrlContainsChange,
}: RunModeSelectorProps) {
  return (
    <>
      <div className="field">
        <span>运行模式</span>
        <div className="button-row" role="radiogroup" aria-label="运行模式">
          <button
            type="button"
            className={mode === "mock" ? "selected" : ""}
            role="radio"
            aria-checked={mode === "mock"}
            onClick={() => onModeChange("mock")}
          >
            模拟走查
          </button>
          <button
            type="button"
            className={mode === "browser-use" ? "selected" : ""}
            role="radio"
            aria-checked={mode === "browser-use"}
            onClick={() => onModeChange("browser-use")}
          >
            真实浏览器
          </button>
        </div>
      </div>

      {mode === "browser-use" ? (
        <div className="browser-use-options">
          <div className="browser-run-note">
            <strong>真实页面测试</strong>
            <span>后端会调用本地 Chrome/Edge 和 browser-use。公开 smoke 默认关闭人工验证；登录态或 UAT 场景可切到自动检测。</span>
          </div>

          <div className="form-grid browser-basic-grid">
            <label className="field">
              <span>人工验证</span>
              <select
                value={verificationMode}
                onChange={(event) => onVerificationModeChange(event.target.value as VerificationMode)}
              >
                <option value="off">关闭（公开页面推荐）</option>
                <option value="auto">自动检测登录/验证码</option>
              </select>
            </label>
            <div className="browser-mode-summary">
              <strong>{verificationMode === "off" ? "公开 smoke 模式" : "登录态 / UAT 模式"}</strong>
              <span>
                {verificationMode === "off"
                  ? "将以 verification_mode=off 提交，不会因为普通登录入口误判为等待验证。"
                  : "将以 verification_mode=auto 提交，建议同时配置可复用 profile 或 storage state。"}
              </span>
            </div>
          </div>

          <details className="debug-details browser-advanced-details">
            <summary>高级 browser-use 参数</summary>
            <div className="form-grid">
              <label className="field">
                <span>最大浏览步骤</span>
                <input
                  type="number"
                  min="1"
                  max="200"
                  value={browserMaxSteps}
                  onChange={(event) => onBrowserMaxStepsChange(Number(event.target.value))}
                />
              </label>
              <label className="field">
                <span>超时时间（秒）</span>
                <input
                  type="number"
                  min="0"
                  max="7200"
                  value={browserTimeoutSec}
                  onChange={(event) => onBrowserTimeoutSecChange(Number(event.target.value))}
                />
              </label>
              <label className="field">
                <span>浏览器 Profile 目录</span>
                <input
                  value={browserUserDataDir}
                  placeholder=".prodwalk/browser-profiles/default"
                  onChange={(event) => onBrowserUserDataDirChange(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Storage state 文件</span>
                <input
                  value={browserStorageState}
                  placeholder=".prodwalk/browser-profiles/default/prodwalk_storage_state.json"
                  onChange={(event) => onBrowserStorageStateChange(event.target.value)}
                />
              </label>
              <label className="field">
                <span>验证等待时间</span>
                <input
                  type="number"
                  min="1"
                  max="3600"
                  value={verificationTimeoutSec}
                  onChange={(event) => onVerificationTimeoutSecChange(Number(event.target.value))}
                />
              </label>
              <label className="field">
                <span>成功 URL 包含</span>
                <input
                  value={verificationSuccessUrlContains}
                  placeholder="/dashboard, /projects"
                  onChange={(event) => onVerificationSuccessUrlContainsChange(event.target.value)}
                />
              </label>
              <label className="field">
                <span>登录 URL 包含</span>
                <input
                  value={verificationLoginUrlContains}
                  placeholder="/auth/login"
                  onChange={(event) => onVerificationLoginUrlContainsChange(event.target.value)}
                />
              </label>
            </div>
          </details>
        </div>
      ) : null}
    </>
  );
}
