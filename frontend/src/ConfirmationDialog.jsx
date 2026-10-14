import { useEffect, useState } from "react";

export function useConfirmationDialog() {
  const [dialog, setDialog] = useState(null);

  function confirm(options) {
    return new Promise((resolve) => {
      setDialog({ ...options, resolve });
    });
  }

  function resolveDialog(value) {
    if (!dialog) return;
    dialog.resolve(value);
    setDialog(null);
  }

  return { confirm, dialog, resolveDialog };
}

export default function ConfirmationDialog({ dialog, onResolve }) {
  const [inputValue, setInputValue] = useState("");

  useEffect(() => {
    setInputValue(dialog?.inputValue || "");
  }, [dialog]);

  useEffect(() => {
    if (!dialog) return undefined;
    function handleKeyDown(event) {
      if (event.key === "Escape") onResolve(dialog.inputLabel ? null : false);
      if (event.key === "Enter" && dialog.inputLabel) {
        event.preventDefault();
        onResolve(inputValue.trim() || null);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [dialog, inputValue, onResolve]);

  if (!dialog) return null;

  return (
    <div
      className="confirm-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onResolve(dialog.inputLabel ? null : false);
        }
      }}
    >
      <section
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
      >
        <span className="confirm-dialog-mark" aria-hidden="true">!</span>
        <h2 id="confirm-dialog-title">{dialog.title || "Confirma la acción"}</h2>
        <p id="confirm-dialog-message">{dialog.message}</p>
        {dialog.inputLabel && (
          <label className="confirm-dialog-input">
            {dialog.inputLabel}
            <input
              autoFocus
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              maxLength={dialog.maxLength || 80}
            />
          </label>
        )}
        <div className="confirm-dialog-actions">
          <button
            className="confirm-cancel"
            type="button"
            onClick={() => onResolve(dialog.inputLabel ? null : false)}
          >
            {dialog.cancelLabel || "Volver"}
          </button>
          <button
            className={`confirm-accept${dialog.danger ? " danger" : ""}`}
            type="button"
            disabled={Boolean(dialog.inputLabel && !inputValue.trim())}
            onClick={() => onResolve(dialog.inputLabel ? inputValue.trim() : true)}
          >
            {dialog.confirmLabel || "Confirmar"}
          </button>
        </div>
      </section>
    </div>
  );
}
