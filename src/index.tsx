import {
  ConfirmModal,
  Field,
  PanelSection,
  PanelSectionRow,
  ShowModalResult,
  ToggleField,
  showModal,
  staticClasses
} from "@decky/ui";
import { addEventListener, callable, definePlugin, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaDesktop } from "react-icons/fa";

type Connector = { name: string; status: string };
type State = {
  externalEnabled: boolean;
  confirmExternal: boolean;
  pendingConfirm: boolean;
  confirmTimeout: number;
  connectors: Connector[];
};

const getState = callable<[], State>("get_state");
const setExternalEnabled = callable<[enabled: boolean], State>("set_external_enabled");
const confirmExternal = callable<[], State>("confirm_external");
const setConfirmExternal = callable<[confirm: boolean], State>("set_confirm_external");

const ru = navigator.language.toLowerCase().startsWith("ru");
const t = ru
  ? {
      toggle: "Выводить на внешний монитор",
      toggleOn: "Изображение переключается на монитор, когда он подключён",
      toggleOff: "Изображение всегда на экране Steam Deck, док работает как зарядка",
      switching: "Переключаю на монитор… Это займёт несколько секунд",
      confirm: "Подтверждать переключение",
      confirmDesc: "Если не подтвердить, изображение вернётся на Steam Deck",
      monitor: "Монитор",
      connected: "подключён",
      notConnected: "не подключён",
      error: "Не удалось переключить вывод",
      dialogTitle: "Оставить изображение на мониторе?",
      dialogBody: (s: number) => `Изображение вернётся на Steam Deck через ${s} с.`,
      keep: "Оставить",
      revert: "Вернуть на Steam Deck",
    }
  : {
      toggle: "Use external display",
      toggleOn: "Picture moves to the external display when it is connected",
      toggleOff: "Picture always stays on the Steam Deck screen, the dock only charges",
      switching: "Switching to the external display… This takes a few seconds",
      confirm: "Confirm switching",
      confirmDesc: "If not confirmed, the picture returns to the Steam Deck",
      monitor: "Display",
      connected: "connected",
      notConnected: "not connected",
      error: "Failed to switch output",
      dialogTitle: "Keep the picture on this display?",
      dialogBody: (s: number) => `Returning to the Steam Deck screen in ${s} s.`,
      keep: "Keep",
      revert: "Back to Steam Deck",
    };

// The confirmation dialog outlives the quick access panel, so state changes made from it
// are pushed to whichever panel instance is currently mounted.
let confirmDialog: ShowModalResult | undefined;
let onStateChange: ((state: State) => void) | undefined;
const publish = (state: State) => onStateChange?.(state);

function ConfirmDialog({ timeout, closeModal }: { timeout: number; closeModal?: () => void }) {
  const [left, setLeft] = useState(timeout);

  useEffect(() => {
    const id = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <ConfirmModal
      strTitle={t.dialogTitle}
      strDescription={t.dialogBody(left)}
      strOKButtonText={t.keep}
      strCancelButtonText={t.revert}
      onOK={() => confirmExternal().then(publish)}
      // The backend reverts on its own when the timer runs out; cancelling just does it sooner.
      onCancel={() => setExternalEnabled(false).then(publish)}
      closeModal={() => {
        confirmDialog = undefined;
        closeModal?.();
      }}
    />
  );
}

function Content() {
  const [state, setState] = useState<State | undefined>();
  const [busy, setBusy] = useState(false);
  const [switchingOn, setSwitchingOn] = useState(false);

  useEffect(() => {
    onStateChange = setState;
    getState().then(setState);
    return () => {
      if (onStateChange === setState) onStateChange = undefined;
    };
  }, []);

  const onToggle = async (enabled: boolean) => {
    setBusy(true);
    setSwitchingOn(enabled);
    try {
      const next = await setExternalEnabled(enabled);
      setState(next);
      if (next.pendingConfirm) {
        confirmDialog?.Close();
        confirmDialog = showModal(<ConfirmDialog timeout={next.confirmTimeout} />);
      }
    } catch (e) {
      toaster.toast({ title: "Dock Display", body: `${t.error}: ${e}` });
    } finally {
      setBusy(false);
      setSwitchingOn(false);
    }
  };

  if (!state) return null;

  // While the output is forced off the kernel reports it as disconnected,
  // so the real connection state is only meaningful when enabled.
  const connected = state.connectors.filter((c) => c.status === "connected");

  return (
    <PanelSection>
      <PanelSectionRow>
        <ToggleField
          label={t.toggle}
          description={switchingOn ? t.switching : state.externalEnabled ? t.toggleOn : t.toggleOff}
          checked={switchingOn || state.externalEnabled}
          disabled={busy}
          onChange={onToggle}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label={t.confirm}
          description={t.confirmDesc}
          checked={state.confirmExternal}
          onChange={async (confirm) => setState(await setConfirmExternal(confirm))}
        />
      </PanelSectionRow>
      {state.externalEnabled && (
        <PanelSectionRow>
          <Field label={t.monitor} focusable={false}>
            {connected.length ? `${connected.map((c) => c.name).join(", ")} — ${t.connected}` : t.notConnected}
          </Field>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

export default definePlugin(() => {
  const reverted = addEventListener("external_reverted", () => {
    confirmDialog?.Close();
    confirmDialog = undefined;
    getState().then(publish);
  });

  return {
    name: "Dock Display",
    titleView: <div className={staticClasses.Title}>Dock Display</div>,
    content: <Content />,
    icon: <FaDesktop />,
    onDismount() {
      removeEventListener("external_reverted", reverted);
      confirmDialog?.Close();
    },
  };
});
