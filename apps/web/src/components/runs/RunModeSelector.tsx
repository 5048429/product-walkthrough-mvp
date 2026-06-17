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
        <span>Mode</span>
        <div className="button-row" role="radiogroup" aria-label="Run mode">
          <button
            type="button"
            className={mode === "mock" ? "selected" : ""}
            role="radio"
            aria-checked={mode === "mock"}
            onClick={() => onModeChange("mock")}
          >
            mock
          </button>
          <button
            type="button"
            className={mode === "browser-use" ? "selected" : ""}
            role="radio"
            aria-checked={mode === "browser-use"}
            onClick={() => onModeChange("browser-use")}
          >
            browser-use
          </button>
        </div>
      </div>

      {mode === "browser-use" ? (
        <div className="browser-use-options">
          <div className="browser-run-note">
            <strong>Local browser run</strong>
            <span>Headless/visible mode is controlled by the server environment (`BROWSER_USE_HEADLESS`). Manual verification may open a local Chrome/Edge window.</span>
          </div>

          <div className="form-grid browser-basic-grid">
            <label className="field">
              <span>Browser max steps</span>
              <input
                type="number"
                min="1"
                max="200"
                value={browserMaxSteps}
                onChange={(event) => onBrowserMaxStepsChange(Number(event.target.value))}
              />
            </label>
            <label className="field">
              <span>Timeout seconds</span>
              <input
                type="number"
                min="0"
                max="7200"
                value={browserTimeoutSec}
                onChange={(event) => onBrowserTimeoutSecChange(Number(event.target.value))}
              />
            </label>
            <label className="field">
              <span>Verification mode</span>
              <select
                value={verificationMode}
                onChange={(event) => onVerificationModeChange(event.target.value as VerificationMode)}
              >
                <option value="auto">auto</option>
                <option value="off">off</option>
              </select>
            </label>
          </div>

          <details className="debug-details browser-advanced-details">
            <summary>Advanced browser-use parameters</summary>
            <div className="form-grid">
              <label className="field">
                <span>User data dir</span>
                <input
                  value={browserUserDataDir}
                  placeholder=".prodwalk/browser-profiles/default"
                  onChange={(event) => onBrowserUserDataDirChange(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Storage state</span>
                <input
                  value={browserStorageState}
                  placeholder=".prodwalk/browser-profiles/default/prodwalk_storage_state.json"
                  onChange={(event) => onBrowserStorageStateChange(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Verification timeout</span>
                <input
                  type="number"
                  min="1"
                  max="3600"
                  value={verificationTimeoutSec}
                  onChange={(event) => onVerificationTimeoutSecChange(Number(event.target.value))}
                />
              </label>
              <label className="field">
                <span>Success URL contains</span>
                <input
                  value={verificationSuccessUrlContains}
                  placeholder="/dashboard, /projects"
                  onChange={(event) => onVerificationSuccessUrlContainsChange(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Login URL contains</span>
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
